"""Orchestration core. One function the HTTP layer calls: generate().

New pipeline (create mode):
    Brief -> Design -> Content -> Engineer -> QA + Critic -> (re-Engineer) -> persist

Patch mode (project_id provided):
    Engineer(patch with previous files + user instruction) -> QA + Critic -> persist

Each agent reads JSON, writes JSON. The Critic loop runs up to
MAX_CRITIC_ITERS regeneration cycles after the first Engineer pass.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Type, TypeVar

from crewai import Crew, Process, Task
from json_repair import repair_json
from pydantic import BaseModel, ValidationError

import db
from .agents import (
    build_brief_agent,
    build_content_writer,
    build_critic,
    build_design_director,
    build_engineer,
)
from services.brand_library import pick_brand

from .app_mode import build_app_project, classify_app_kind
from .app_types import APP_TYPE_REGISTRY, app_type_classifier_catalog, get_app_type
from .archetypes import archetypes_catalog_text, get_archetype
from .catalogs import lucide_catalog_text, shadcn_catalog_text
from .design_modes import design_mode_for_app_type, design_modes_catalog_text, get_design_mode
from .intent import classify_intent, evaluate_math, extract_image_subject
from .scaffold import scaffold_project
from .scaffold_multi import scaffold_for_plan
from .reference_intelligence import classify_and_plan as _classify_and_plan
from services.image_gen import generate_image_url

import litellm
from .schemas import (
    AgentStep,
    ColorScale,
    ContentPack,
    CritiqueReport,
    DesignSystem,
    FileSet,
    GeneratedFile,
    GenerateResponse,
    NavItem,
    ProductBrief,
    TemplatePlan,
)

MAX_CRITIC_ITERS = int(os.getenv("MAX_CRITIC_ITERS", "1"))


# ---------------------------------------------------------------------------
# Strip CrewAI's Anthropic-style `cache_breakpoint` / `cache_control` fields
# from outgoing messages. Groq (and most other providers) reject unknown
# message-level properties with HTTP 400, killing the brief/design/engineer
# pipeline before it can produce a landing page. We patch litellm.completion
# once, at module import, so every CrewAI call goes through the sanitizer.
# litellm.drop_params handles top-level params; this handles message bodies.
# ---------------------------------------------------------------------------
_UNSUPPORTED_MESSAGE_KEYS = ("cache_breakpoint", "cache_control")


def _scrub_messages(messages: list[dict]) -> list[dict]:
    if not isinstance(messages, list):
        return messages
    cleaned: list[dict] = []
    for msg in messages:
        if isinstance(msg, dict) and any(k in msg for k in _UNSUPPORTED_MESSAGE_KEYS):
            msg = {k: v for k, v in msg.items() if k not in _UNSUPPORTED_MESSAGE_KEYS}
        cleaned.append(msg)
    return cleaned


_original_litellm_completion = litellm.completion


def _safe_completion(*args, **kwargs):
    if "messages" in kwargs:
        kwargs["messages"] = _scrub_messages(kwargs["messages"])
    elif args:
        # litellm.completion(model, messages, ...) positional form
        new_args = list(args)
        if len(new_args) >= 2 and isinstance(new_args[1], list):
            new_args[1] = _scrub_messages(new_args[1])
        args = tuple(new_args)
    return _original_litellm_completion(*args, **kwargs)


litellm.completion = _safe_completion
litellm.drop_params = True


# ===========================================================================
# Parsing helpers
# ===========================================================================

M = TypeVar("M", bound=BaseModel)


def _strip_fences(text: str) -> str:
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


def _extract_json(text: str) -> str:
    """Pull the first top-level JSON object/array out of *text*,
    ignoring any commentary the LLM may have added around it."""
    # Replace backticks with double quotes (LLM uses JS template literals).
    text = text.replace("`", '"')
    # Find the first '{' or '[' and match to the last '}' or ']'.
    start = None
    opener = None
    for i, ch in enumerate(text):
        if ch in "{[":
            start = i
            opener = ch
            break
    if start is None:
        return text
    closer = "}" if opener == "{" else "]"
    # Walk backwards from the end to find the matching close.
    end = text.rfind(closer)
    if end is not None and end > start:
        return text[start : end + 1]
    return text[start:]


def _normalize_data(data: Any) -> Any:
    """Unwrap list→dict and clean up arrays with stray non-dict items."""
    # Unwrap single-element list.
    if isinstance(data, list):
        # Pick the first dict that looks like a model.
        for item in data:
            if isinstance(item, dict):
                data = item
                break
        else:
            return data
    # Clean up list-valued fields that have stray strings mixed in.
    if isinstance(data, dict):
        for key, val in data.items():
            if isinstance(val, list):
                cleaned = [item for item in val if isinstance(item, dict)]
                if cleaned and len(cleaned) != len(val):
                    data[key] = cleaned
    return data


def _parse_into(text: str, model_cls: Type[M]) -> M:
    raw = _strip_fences(text)
    raw = _extract_json(raw)
    data: Any
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        repaired = repair_json(raw, return_objects=True)
        if isinstance(repaired, str):
            raise RuntimeError(f"unparseable LLM output: {raw[:300]!r}")
        data = repaired
    data = _normalize_data(data)
    try:
        return model_cls.model_validate(data)
    except ValidationError as e:
        raise RuntimeError(
            f"{model_cls.__name__} validation failed: {e}\n---\nRaw: {raw[:600]}"
        )


_RATE_LIMIT_PAT = re.compile(r"try again in\s+([\d.]+)\s*s", re.IGNORECASE)
_MAX_RATE_LIMIT_RETRIES = 4


def _is_rate_limit_error(err: BaseException) -> bool:
    msg = str(err).lower()
    return (
        "ratelimiterror" in msg
        or "rate_limit_exceeded" in msg
        or "rate limit reached" in msg
        or "429" in msg
    )


def _extract_retry_seconds(err: BaseException) -> float:
    m = _RATE_LIMIT_PAT.search(str(err))
    if m:
        try:
            return float(m.group(1)) + 1.0
        except ValueError:
            pass
    return 12.0  # safe fallback for Groq TPM windows


def _run_task(agent, description: str, expected_output: str) -> str:
    task = Task(description=description, expected_output=expected_output, agent=agent)
    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
    last_err: BaseException | None = None
    for attempt in range(_MAX_RATE_LIMIT_RETRIES):
        try:
            return str(crew.kickoff().raw or "")
        except Exception as e:  # noqa: BLE001
            last_err = e
            if not _is_rate_limit_error(e):
                raise
            wait = _extract_retry_seconds(e)
            print(
                f"[rate-limit] attempt {attempt + 1}/{_MAX_RATE_LIMIT_RETRIES} "
                f"sleeping {wait:.1f}s for agent {agent.role!r}",
                flush=True,
            )
            time.sleep(wait)
    assert last_err is not None
    raise last_err


def _merge_fixes(
    original: list[GeneratedFile],
    fixes: list[GeneratedFile],
) -> list[GeneratedFile]:
    by_path = {f.path: f for f in original}
    for fix in fixes:
        by_path[fix.path] = fix
    return list(by_path.values())


def _files_text(files: list[GeneratedFile], limit_per_file: int = 4000) -> str:
    blocks: list[str] = []
    for f in files:
        c = f.content
        if len(c) > limit_per_file:
            c = c[:limit_per_file] + f"\n... [truncated, file is {len(f.content)} chars]"
        blocks.append(f"=== {f.path} ===\n{c}")
    return "\n\n".join(blocks)


# ===========================================================================
# Per-stage runners
# ===========================================================================

def _run_brief(prompt: str) -> ProductBrief:
    agent = build_brief_agent()
    description = (
        f"USER PROMPT:\n\"\"\"\n{prompt}\n\"\"\"\n\n"
        "STEP 1 — CLASSIFY the app_type. Pick ONE key from this catalog:\n\n"
        f"{app_type_classifier_catalog()}\n\n"
        "CLASSIFICATION RULES (non-negotiable):\n"
        "  - 'calculator', 'unit converter', 'color picker' → app_type=tool\n"
        "  - 'snake', 'tic tac toe', 'pong', 'flappy bird' → app_type=game\n"
        "  - 'todo', 'pomodoro', 'notes', 'habit tracker' → app_type=productivity\n"
        "  - 'sales dashboard', 'analytics for X' → app_type=dashboard\n"
        "  - 'coffee shop website', 'agency landing' → app_type=landing\n"
        "  - When ambiguous, prefer the FUNCTIONAL category over 'landing'.\n\n"
        "STEP 2 — produce a ProductBrief JSON with these fields:\n"
        "  name             (kebab-case)\n"
        "  app_type         (one of the catalog keys above — REQUIRED)\n"
        "  product_type     (kept for back-compat; can mirror app_type)\n"
        "  audience         (one sentence)\n"
        "  mood             (3-5 adjectives: 'confident', 'playful', 'minimal'...)\n"
        "  differentiator   (one sentence on what's distinctive)\n"
        "  pages            (list of {name, route, sections, purpose}, >= 1)\n"
        "  interactions     (list of {element, location, behavior}, >= 3)\n"
        "  must_not         (constraints, optional)\n\n"
        "SECTIONS VOCABULARY — use ONLY these names for page.sections:\n"
        "  hero, features-grid, feature-spotlight, testimonials, logo-cloud,\n"
        "  pricing-table, faq, cta-band, footer, stats-band, how-it-works,\n"
        "  blog-grid, contact-form, team-grid, gallery-grid, comparison-table,\n"
        "  newsletter, dashboard-shell, sidebar-nav, topbar, stat-cards,\n"
        "  data-table, chart-panel, game-canvas, chat-window, editor-pane.\n\n"
        "INTERACTION EXAMPLES (each must be CONCRETE):\n"
        "  - element 'nav.cta', location 'header right', behavior 'route to /signup'\n"
        "  - element 'pricing.upgrade', location 'pricing card 2', behavior 'open UpgradeDialog'\n"
        "  - element 'game.start', location 'canvas overlay', behavior 'start the game loop'\n\n"
        "If the prompt is vague, INFER aggressively — pick a confident direction. "
        "Output ONLY a JSON object. No commentary. No markdown fences."
    )
    raw = _run_task(agent, description, "A JSON object matching ProductBrief.")
    return _parse_into(raw, ProductBrief)


def _run_design(brief: ProductBrief) -> DesignSystem:
    agent = build_design_director()
    default_mode = design_mode_for_app_type(brief.app_type)
    description = (
        f"PRODUCT BRIEF:\n{brief.model_dump_json(indent=2)}\n\n"
        f"ARCHETYPE CATALOG (pick exactly ONE archetype key):\n"
        f"{archetypes_catalog_text()}\n\n"
        f"DESIGN MODE CATALOG (pick exactly ONE design_mode key):\n"
        f"  Default for app_type='{brief.app_type}': {default_mode}\n\n"
        f"{design_modes_catalog_text()}\n\n"
        "Produce a DesignSystem JSON:\n"
        "  archetype         (one of the archetype keys above)\n"
        "  design_mode       (REQUIRED — one of the design_mode keys above)\n"
        "  palette           (list of {name, base hex, description}; "
        "at least 'primary', 'neutral', 'accent')\n"
        "  fonts             ({display, body, mono} font-family strings)\n"
        "  radius            ('sharp' | 'subtle' | 'soft' | 'pill')\n"
        "  density           ('tight' | 'comfortable' | 'spacious')\n"
        "  motion            ('none' | 'subtle' | 'expressive')\n"
        "  signature_moves   (3-5 specific moves you will execute)\n\n"
        "Commit to ONE archetype + ONE design_mode. Do NOT blend. "
        "Output ONLY JSON, no fences."
    )
    raw = _run_task(agent, description, "A JSON object matching DesignSystem.")
    return _parse_into(raw, DesignSystem)


def _run_content(brief: ProductBrief, design: DesignSystem) -> ContentPack:
    agent = build_content_writer()
    description = (
        f"BRIEF:\n{brief.model_dump_json(indent=2)}\n\n"
        f"DESIGN (for tone alignment):\n{design.model_dump_json(indent=2)}\n\n"
        "Produce a ContentPack JSON:\n"
        "  brand_name, tagline, hero_headline (<8 words), hero_subhead (<25 words)\n"
        "  primary_cta, secondary_cta (optional)\n"
        "  nav_items: 4-6 {label, route}\n"
        "  features: 3-6 {title, description, icon} — icon = lucide name like 'Zap'\n"
        "  testimonials: 2-4 {quote, author, role, company} — believable names\n"
        "  pricing_tiers: 0 or 3 {name, price, period, description,\n"
        "                         features (4-7 concrete items), cta_label, highlighted}\n"
        "  faqs: 4-6 {question, answer}\n"
        "  footer_links: dict like {'Product': [{label,route}], 'Company': [...], 'Resources': [...]}\n\n"
        "RULES:\n"
        "  - Every line specific to THIS product domain (no generic SaaS-mush).\n"
        "  - No 'lorem ipsum', no 'Welcome to our amazing platform'.\n"
        "  - Testimonial names sound real: 'Maya Patel, Lead Engineer at Stripe',\n"
        "    not 'John Doe, CEO'.\n"
        "  - Pricing features are concrete: 'Up to 50 projects',\n"
        "    not 'Unlimited everything'.\n"
        "  - Output ONLY a JSON object. No fences."
    )
    raw = _run_task(agent, description, "A JSON object matching ContentPack.")
    return _parse_into(raw, ContentPack)


# ===========================================================================
# Template-intelligence seeded helpers (additive — only used on matched path)
# ===========================================================================

def _brief_from_plan(prompt: str, plan: TemplatePlan) -> ProductBrief:
    """Deterministic ProductBrief built from a TemplatePlan.

    Bypasses the Brief LLM when we already know the niche from a template
    match — faster and removes the misclassification risk that caused
    'Chinese restaurant' to be labeled `app_type=landing`.
    """
    sub = plan.sub_niche or ""
    name_seed = f"{sub}-{plan.category}" if sub else plan.category
    return ProductBrief(
        name=name_seed.strip("-") or "site",
        app_type="landing",
        product_type=plan.category + (f"/{sub}" if sub else ""),
        audience=f"guests of a {sub} {plan.category}".strip() if sub else f"visitors to a {plan.category}",
        mood=list(plan.mood)[:5] or ["warm", "intentional"],
        differentiator=f"{plan.template_label} — pulled from prompt: {prompt[:80]}",
        pages=list(plan.pages),
        interactions=list(plan.interactions),
        must_not=[
            "no SaaS hero+features+pricing layout",
            "no testimonials carousel",
            "no generic 'Welcome to our platform' copy",
        ],
    )


def _design_from_plan(plan: TemplatePlan) -> DesignSystem:
    """Deterministic DesignSystem from the template manifest's design_mode_hint.

    Falls back to a sensible niche default when the hint is missing.
    """
    fallback_mode_by_category = {
        "restaurant": "warm_luxury_red",
        "cafe":       "warm_editorial",
        "bakery":     "warm_editorial",
        "ecommerce":  "premium_modern",
        "dashboard":  "zinc_emerald",
        "portfolio":  "warm_editorial",
        "saas":       "premium_modern",
    }
    mode = plan.design_mode_hint or fallback_mode_by_category.get(plan.category, "premium_modern")
    fonts = dict(plan.fonts) if plan.fonts else {
        "display": "Playfair Display",
        "body":    "Inter",
        "mono":    "JetBrains Mono",
    }
    return DesignSystem(
        archetype="linear-minimal",
        design_mode=mode,
        palette=[],
        fonts=fonts,
        radius="subtle",
        density="comfortable",
        motion="subtle",
        signature_moves=[
            f"{plan.template_label} editorial layout",
            "niche-appropriate imagery from Pollinations",
            "real menu data sourced from the niche pack",
        ],
    )


def _content_from_plan(plan: TemplatePlan) -> ContentPack:
    """Deterministic ContentPack fallback when the niche-seeded LLM call fails or is skipped.

    Brand name, hero copy, and nav are derived from the template plan so the
    output is still 'real' (not lorem ipsum) without any LLM dependency.
    """
    label = plan.template_label or plan.category.capitalize()
    brand = label
    sub = plan.sub_niche
    if sub:
        descriptors = {
            "chinese":  "Chinese Kitchen",
            "japanese": "Japanese Counter",
            "italian":  "Italian Table",
            "mexican":  "Mexican Comedor",
            "indian":   "Indian Kitchen",
            "thai":     "Thai Kitchen",
            "french":   "French Maison",
            "steakhouse":"Steakhouse",
            "cafe":     "Café",
            "specialty":"Specialty Café",
            "bakery":   "Bakery",
            "fashion":  "Atelier",
        }
        brand = descriptors.get(sub, label)

    hero_by_category = {
        "restaurant": "A table for the senses",
        "cafe":       "All-day coffee and a plate to match",
        "bakery":     "Fresh from the oven, every morning",
        "ecommerce":  "Pieces made to be lived in",
    }
    hero_headline = hero_by_category.get(plan.category, label)

    nav_items = [
        NavItem(label=str(item.get("label") or "").strip(), route=str(item.get("route") or "/").strip())
        for item in (plan.navigation.get("header") or [])
        if item.get("label") and item.get("route")
    ]
    footer_links: dict[str, list[NavItem]] = {}
    for col, items in (plan.navigation.get("footer") or {}).items():
        footer_links[col] = [
            NavItem(label=str(it.get("label") or "").strip(), route=str(it.get("route") or "/").strip())
            for it in items
            if it.get("label") and it.get("route")
        ]

    return ContentPack(
        brand_name=brand,
        tagline=", ".join(plan.mood[:3]) or "",
        hero_headline=hero_headline,
        hero_subhead="A small kitchen with a long story. Real ingredients, real hands.",
        primary_cta="Reserve a table" if plan.category == "restaurant" else "Visit us",
        secondary_cta="View menu",
        nav_items=nav_items,
        features=[],
        testimonials=[],
        pricing_tiers=[],
        faqs=[],
        footer_links=footer_links,
    )


def _run_content_seeded(
    brief: ProductBrief,
    design: DesignSystem,
    plan: TemplatePlan,
) -> ContentPack | None:
    """Run the existing Content Writer with strong niche guardrails.

    Returns None if the call fails — the caller should fall back to
    `_content_from_plan(plan)` so the path remains robust.
    """
    if not plan.data_pack:
        return None
    try:
        agent = build_content_writer()
        niche_block = (
            f"NICHE: {plan.category}"
            + (f" / {plan.sub_niche}" if plan.sub_niche else "")
            + f"\nMOOD: {', '.join(plan.mood) or 'warm, intentional'}\n"
        )
        pack_block = json.dumps(plan.data_pack[:12], ensure_ascii=False, indent=2)
        description = (
            f"BRIEF:\n{brief.model_dump_json(indent=2)}\n\n"
            f"DESIGN (for tone alignment):\n{design.model_dump_json(indent=2)}\n\n"
            f"{niche_block}\n"
            "NICHE INSPIRATION DATA (real items from the kitchen — keep tone consistent;\n"
            "you are writing brand copy that lives ALONGSIDE this real menu):\n"
            f"{pack_block}\n\n"
            "Produce a ContentPack JSON with these fields:\n"
            "  brand_name (real-sounding brand for this niche — NEVER 'platform', 'app', 'studio')\n"
            "  tagline (one short sentence specific to the niche)\n"
            "  hero_headline (<8 words, evocative; restaurants use sensory or warmth words)\n"
            "  hero_subhead (<25 words, about food / place / hospitality if restaurant)\n"
            "  primary_cta ('Reserve a table' / 'Order now' style — fit the niche)\n"
            "  secondary_cta ('View menu' / 'See the room')\n"
            "  nav_items: 4-6 {label, route} — use ONLY these routes that exist on this site\n"
            f"    valid routes: {[p.route for p in brief.pages]}\n"
            "  features: [] (LEAVE EMPTY — this is a website, not a SaaS landing)\n"
            "  testimonials: [] (LEAVE EMPTY)\n"
            "  pricing_tiers: [] (LEAVE EMPTY)\n"
            "  faqs: 3-5 {question, answer} — niche-appropriate (dietary, parking, dress code, etc.)\n"
            "  footer_links: {} or simple {Visit: [...]} columns\n\n"
            "ABSOLUTE RULES:\n"
            "  - NO SaaS language. No 'platform', 'streamline', 'workflow', 'AI-powered'.\n"
            "  - Brand name must fit the niche. For a Chinese restaurant, names like\n"
            "    'Red Lantern', 'Silk & Spice', 'House of Cranes' — never 'CoffeeCo'.\n"
            "  - Output ONLY a JSON object. No fences."
        )
        raw = _run_task(agent, description, "A JSON object matching ContentPack.")
        return _parse_into(raw, ContentPack)
    except Exception as e:  # noqa: BLE001
        print(f"[template-path] content writer failed, using deterministic fallback: {e}", flush=True)
        return None


def _merge_seeded_content(seeded: ContentPack, fallback: ContentPack) -> ContentPack:
    """Fill any empty seeded fields from the deterministic fallback so we never emit blanks."""
    return ContentPack(
        brand_name=seeded.brand_name or fallback.brand_name,
        tagline=seeded.tagline or fallback.tagline,
        hero_headline=seeded.hero_headline or fallback.hero_headline,
        hero_subhead=seeded.hero_subhead or fallback.hero_subhead,
        primary_cta=seeded.primary_cta or fallback.primary_cta,
        secondary_cta=seeded.secondary_cta or fallback.secondary_cta,
        nav_items=seeded.nav_items or fallback.nav_items,
        features=seeded.features,  # intentionally do not import landing-page bloat
        testimonials=seeded.testimonials,
        pricing_tiers=seeded.pricing_tiers,
        faqs=seeded.faqs,
        footer_links=seeded.footer_links or fallback.footer_links,
    )


def _run_engineer(
    brief: ProductBrief,
    design: DesignSystem,
    content: ContentPack,
    previous_files: list[GeneratedFile] | None = None,
    critique_must_fix: list[str] | None = None,
) -> FileSet:
    agent = build_engineer()
    archetype_block = json.dumps(get_archetype(design.archetype), indent=2)

    parts: list[str] = [
        f"BRIEF:\n{brief.model_dump_json(indent=2)}",
        f"DESIGN SYSTEM:\n{design.model_dump_json(indent=2)}",
        f"ARCHETYPE DETAILS:\n{archetype_block}",
        f"CONTENT PACK (use VERBATIM — do NOT rewrite the copy):\n"
        f"{content.model_dump_json(indent=2)}",
        shadcn_catalog_text(),
        lucide_catalog_text(),
    ]

    if previous_files and critique_must_fix:
        parts.append(
            "ITERATION — this is a fix pass on the previous output. "
            "Re-emit the FULL FileSet (all files) with the must-fix items applied. "
            "Keep working code untouched.\n\n"
            f"PREVIOUS FILES:\n{_files_text(previous_files)}\n\n"
            "MUST-FIX:\n" + "\n".join(f"  - {x}" for x in critique_must_fix)
        )

    parts.append(
        "PROJECT TEMPLATE — output a FileSet with EXACTLY these files (minimum):\n"
        "  package.json        deps: react, react-dom, react-router-dom,\n"
        "                            lucide-react, framer-motion, sonner,\n"
        "                            clsx, tailwind-merge, class-variance-authority,\n"
        "                            and one @radix-ui/* dep per shadcn primitive used\n"
        "                            (e.g. @radix-ui/react-dialog, @radix-ui/react-tabs).\n"
        "                      devDeps: vite, @vitejs/plugin-react, typescript,\n"
        "                            @types/react, @types/react-dom,\n"
        "                            tailwindcss, postcss, autoprefixer.\n"
        "                      scripts: { dev, build, preview, typecheck }.\n"
        "  vite.config.ts      @vitejs/plugin-react + resolve alias '@' -> 'src'.\n"
        "  tailwind.config.ts  extend theme.colors with the palette (as CSS vars\n"
        "                      under hsl() or hex), theme.fontFamily with the\n"
        "                      design.fonts, theme.borderRadius mapped from\n"
        "                      design.radius.\n"
        "  postcss.config.js   tailwindcss + autoprefixer.\n"
        "  tsconfig.json       strict, jsx: 'react-jsx',\n"
        "                      paths: { '@/*': ['src/*'] }.\n"
        "  index.html          <div id='root'></div> + script /src/main.tsx.\n"
        "  src/main.tsx        ReactDOM.createRoot, <BrowserRouter><App /></BrowserRouter>,\n"
        "                      mount <Toaster> from sonner.\n"
        "  src/App.tsx         <Routes> for every page in brief.pages, plus the\n"
        "                      <Header>, <Footer>, and <TooltipProvider> wrap.\n"
        "  src/index.css       @tailwind base/components/utilities + :root CSS\n"
        "                      vars for the palette (--primary, --background, etc.).\n"
        "  src/lib/utils.ts    cn() helper using clsx + tailwind-merge.\n"
        "  src/components/ui/* every shadcn primitive you import — written out IN FULL\n"
        "                      (use Radix + cva, mirror the official shadcn source).\n"
        "  src/components/layout/Header.tsx, Footer.tsx (+ MobileNav if responsive nav).\n"
        "  src/components/sections/*.tsx — one component per section ID used in\n"
        "                      brief.pages[].sections (Hero.tsx, FeatureGrid.tsx,\n"
        "                      PricingTable.tsx, Testimonials.tsx, Faq.tsx, ...).\n"
        "  src/pages/*.tsx     one file per brief.pages, composing sections in order.\n\n"
        "ENGINEERING RULES — non-negotiable:\n"
        " 1. Use ONLY shadcn imports listed in the catalog. Use ONLY lucide icons\n"
        "    in the whitelist. NEVER invent paths or icon names.\n"
        " 2. Write every shadcn primitive in src/components/ui/ in FULL (Radix + cva).\n"
        "    Do NOT 'import from shadcn-ui' as if it were an npm package — it is not.\n"
        " 3. Every <Button>, <Link>, form, modal, tab, accordion, dropdown MUST have\n"
        "    a working handler. If you cannot make it work, do not render it.\n"
        "\n"
        "NAVIGATION — CRITICAL (broken nav = broken app):\n"
        " 4. The HEADER nav links are the SINGLE SOURCE OF TRUTH for routing.\n"
        "    Step A: Read content.nav_items — each has {label, route}.\n"
        "    Step B: In App.tsx, add a <Route path={route} element={<PageComponent />} />\n"
        "            for EVERY nav_item route. Also add <Route path='/' ... /> for home.\n"
        "    Step C: In Header.tsx, render <Link to={route}>{label}</Link> for each.\n"
        "    Step D: Create a src/pages/*.tsx file for EVERY route.\n"
        "    RESULT: Every nav link clicks → route matches → page renders. Zero dead links.\n"
        " 5. NEVER use <a href='#section'>. Use <Link to='/route'> for page nav.\n"
        "    For same-page scroll, use onClick={() => document.getElementById('id')?.scrollIntoView({behavior:'smooth'})}.\n"
        " 6. If brief.pages is empty, create at LEAST: Home ('/'), About ('/about'),\n"
        "    Contact ('/contact'). Each page MUST have real content — not just a heading.\n"
        "\n"
        "PAGE CONTENT — every page must feel complete:\n"
        " 7. Every page MUST have at least 2 distinct content sections with real content.\n"
        "    Example: a Features page needs a grid of feature cards (minimum 2 cards),\n"
        "    PLUS a CTA or description section. NEVER render a page with just a title.\n"
        " 8. Cards, grids, lists: always render at least 2 real items with real text.\n"
        "    NEVER render empty arrays or single placeholder items.\n"
        " 9. Use the ContentPack copy VERBATIM. Never invent your own marketing copy.\n"
        "    Never use 'lorem ipsum'. If ContentPack is sparse, write realistic copy\n"
        "    that fits the brand.\n"
        "\n"
        "STYLING & QUALITY:\n"
        "10. Use the design palette via CSS variables / Tailwind tokens.\n"
        "    Do NOT hardcode hex colors in JSX.\n"
        "11. Mobile-first responsive: every section must work at 375px, 768px, 1280px.\n"
        "12. framer-motion only on purposeful motion (hero entry, modal, section\n"
        "    reveal). Never animate every element.\n"
        "13. Forms: react-hook-form + zod. Inline error messages + sonner toast on submit.\n"
        "14. Render sections in the order listed in brief.pages[].sections.\n"
        "15. No '...' placeholders. No TODOs. No commented-out code. Complete content.\n"
        "16. NEVER invent npm package names. Use ONLY the exact packages listed above.\n"
        "    The package is 'class-variance-authority' — NOT '@class-variance-authority/*'.\n"
        "\n"
        "JSON OUTPUT — STRICT:\n"
        "17. Top-level keys: 'files' (list of {path, content}), 'entry', 'summary'.\n"
        "18. Inside string values, escape special chars: \\n for newlines,\n"
        "    \\\" for double-quotes, \\\\ for backslashes. NEVER use literal newlines\n"
        "    inside JSON string values.\n"
        "19. 'entry' must be 'index.html'.\n"
        "20. No markdown fences. No commentary. Just the JSON object.\n"
    )

    description = "\n\n".join(parts)

    # Try primary model (Groq 70B), retry with backup key if it fails.
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            raw = _run_task(agent, description, "A JSON object matching FileSet.")
            print(f"[engineer:attempt-{attempt + 1}] raw output length: {len(raw)} chars", flush=True)
            fs = _parse_into(raw, FileSet)
            _validate_fileset(fs)
            return _sanitize_fileset(fs)
        except Exception as e:
            last_err = e
            print(f"[engineer:attempt-{attempt + 1}] failed: {e}", flush=True)
            # Swap to backup Groq key for next attempt
            backup_key = os.environ.get("GROQ_API_KEY_BACKUP")
            if backup_key:
                os.environ["GROQ_API_KEY"] = backup_key

    raise RuntimeError(f"Engineer failed after retries: {last_err}")


_REQUIRED_FILES = {"package.json", "index.html", "src/main.tsx", "src/App.tsx"}


def _validate_fileset(fs: FileSet) -> None:
    """Raise if the FileSet is clearly truncated (missing critical files)."""
    paths = {f.path for f in fs.files}
    missing = _REQUIRED_FILES - paths
    if missing:
        raise RuntimeError(
            f"Engineer output is truncated — only {len(fs.files)} file(s) generated "
            f"({', '.join(f.path for f in fs.files[:5])}). "
            f"Missing required: {', '.join(sorted(missing))}. "
            f"This usually means the LLM hit its output token limit. "
            f"Set ENGINEER_MODEL to a model with higher output capacity "
            f"(e.g. gemini/gemini-2.0-flash or groq/llama-3.3-70b-versatile)."
        )


# Allowed npm dependency prefixes — anything not matching gets stripped.
_ALLOWED_DEPS = {
    "react", "react-dom", "react-router-dom", "lucide-react",
    "framer-motion", "sonner", "clsx", "tailwind-merge",
    "class-variance-authority", "@radix-ui/", "@vitejs/plugin-react",
    "vite", "typescript", "@types/react", "@types/react-dom",
    "tailwindcss", "postcss", "autoprefixer", "react-hook-form", "zod",
}


def _is_allowed_dep(name: str) -> bool:
    for allowed in _ALLOWED_DEPS:
        if allowed.endswith("/"):
            if name.startswith(allowed):
                return True
        elif name == allowed:
            return True
    return False


def _sanitize_fileset(fs: FileSet) -> FileSet:
    """Strip hallucinated npm packages from package.json."""
    for f in fs.files:
        if f.path.endswith("package.json"):
            try:
                pkg = json.loads(f.content)
            except (json.JSONDecodeError, TypeError):
                continue
            changed = False
            for key in ("dependencies", "devDependencies"):
                if key in pkg and isinstance(pkg[key], dict):
                    cleaned = {
                        k: v for k, v in pkg[key].items() if _is_allowed_dep(k)
                    }
                    if len(cleaned) != len(pkg[key]):
                        pkg[key] = cleaned
                        changed = True
            if changed:
                f.content = json.dumps(pkg, indent=2)
    return fs


def _run_critic(
    brief: ProductBrief,
    design: DesignSystem,
    file_set: FileSet,
    qa_errors: list[str],
    qa_warnings: list[str],
) -> CritiqueReport:
    agent = build_critic()
    description = (
        f"BRIEF:\n{brief.model_dump_json(indent=2)}\n\n"
        f"DESIGN:\n{design.model_dump_json(indent=2)}\n\n"
        f"GENERATED FILES (truncated for readability):\n"
        f"{_files_text(file_set.files, limit_per_file=2500)}\n\n"
        f"DETERMINISTIC QA ERRORS — every one MUST appear in must_fix:\n"
        + ("\n".join(f"  - {e}" for e in qa_errors) or "  (none)")
        + "\n\nDETERMINISTIC QA WARNINGS:\n"
        + ("\n".join(f"  - {w}" for w in qa_warnings) or "  (none)")
        + "\n\nScore the work 1-10 on each dimension: 'hierarchy', 'spacing', "
          "'typography', 'color', 'density', 'feels_real'. Provide:\n"
          "  overall_score      (1-10)\n"
          "  scores             (list of {dimension, score, note})\n"
          "  must_fix           (specific changes required; every QA error included)\n"
          "  nice_to_fix        (lower-priority polish items)\n"
          "  fixes              (REPLACEMENT file contents for any file that needs\n"
          "                      editing — full file content, not diff)\n"
          "  ok                 (true ONLY if overall_score >= 8 AND no qa errors)\n\n"
          "Be harsh but SPECIFIC. 'Make hero better' is not acceptable feedback — "
          "say 'Hero needs an asymmetric 7/5 grid with a stat callout on the right'. "
          "9-10 is reserved for top-tier; you never give 10.\n\n"
          "Output ONLY a JSON object matching CritiqueReport. No markdown fences."
    )
    raw = _run_task(agent, description, "A JSON object matching CritiqueReport.")
    try:
        return _parse_into(raw, CritiqueReport)
    except RuntimeError:
        # If the critic itself failed to produce parseable output, don't block.
        # Fail closed: if QA had errors, treat as not-ok. Otherwise treat as ok.
        return CritiqueReport(
            ok=not qa_errors,
            overall_score=4 if qa_errors else 6,
            must_fix=list(qa_errors),
            nice_to_fix=[],
            fixes=[],
        )


# ===========================================================================
# Public entry point
# ===========================================================================

def _stub_brief_for_patch(name: str) -> ProductBrief:
    return ProductBrief(
        name=name,
        product_type="patch",
        audience="existing users",
        mood=["consistent"],
        differentiator="patch operation",
        pages=[],
        interactions=[],
    )


def _stub_design_for_patch() -> DesignSystem:
    return DesignSystem(
        archetype="linear-minimal",
        palette=[],
        fonts={"display": "Inter", "body": "Inter", "mono": "JetBrains Mono"},
        radius="subtle",
        density="comfortable",
        motion="subtle",
        signature_moves=[],
    )


def _stub_content_for_patch() -> ContentPack:
    return ContentPack(
        brand_name="(existing)",
        tagline="",
        hero_headline="(existing)",
        hero_subhead="",
        primary_cta="",
        nav_items=[NavItem(label="Home", route="/")],
        features=[],
    )


def generate(prompt: str, project_id: str | None = None) -> GenerateResponse:
    db.init_db()
    trail: list[AgentStep] = []
    is_patch = project_id is not None

    # -------- top-level intent routing --------
    # Chat / math / image requests don't need the build pipeline at all.
    # If the user is in an existing project (is_patch=True), we always run
    # the build pipeline — they want changes to their app, not chitchat.
    if not is_patch:
        intent = classify_intent(prompt)
        if intent == "math":
            return _math_response(prompt)
        if intent == "image":
            return _image_response(prompt)
        if intent == "chat":
            return _chat_response(prompt)

    # Pick a brand-inspired design system once, before any branching, so both
    # the app-mode and the landing-mode pipelines color their output with the
    # same palette (no more black-and-white-only generations).
    brand = pick_brand(prompt)
    trail.append(AgentStep(
        agent="BrandPicker",
        summary=f"{brand.name} ({brand.key}) · primary {brand.primary_hex()}",
    ))

    # -------- app mode --------
    # Calculator / todo / timer / notes etc. bypass the marketing-page pipeline
    # entirely. The landing-page brief/design/content agents always emit a hero
    # + features + pricing layout, which is wrong for functional apps.
    deterministic_apps = {
        "calculator",
        "todo",
        "timer",
        "notes",
        "snake",
        "tictactoe",
        "pong",
        "sudoku",
    }

    app_kind = classify_app_kind(prompt)

    # For the catch-all "functional" kind (matched only because the prompt
    # has the word "app" / "tool" / etc.), let the template intelligence
    # engine override if it has a confident multi-page match — so "Build a
    # SaaS landing for AI note-taking app" goes to the open-lovable-saas
    # scaffolder, not the AI functional engineer. Deterministic kinds
    # (calculator / snake / ...) stay bound to their templates regardless.
    if app_kind == "functional" and not is_patch:
        try:
            _early_decision = _classify_and_plan(prompt)
        except Exception:
            _early_decision = None  # any classifier error -> stay on functional path
        if (
            _early_decision is not None
            and _early_decision.fired
            and _early_decision.plan is not None
            and _early_decision.plan.category in {"restaurant", "saas", "portfolio", "ecommerce", "healthcare"}
        ):
            app_kind = None  # fall through to template-intelligence block below

    if app_kind is not None:
        if app_kind in deterministic_apps:
            file_set = build_app_project(prompt, app_kind, brand=brand)
            trail.append(
                AgentStep(
                    agent="AppBuilder",
                    summary=f"{app_kind} · deterministic functional app · {brand.name} palette",
                )
            )
        else:
            # AI-generated functional app pipeline
            brief = ProductBrief(
                name="functional-app",
                app_type="tool",
                product_type="functional-app",
                audience="general users",
                mood=["modern", "interactive"],
                differentiator="real interactive functionality",
                pages=[],
                interactions=[],
            )
            design = DesignSystem(
                archetype="linear-minimal",
                design_mode="xai-dark",
                palette=[],
                fonts={
                    "display": "Inter",
                    "body": "Inter",
                    "mono": "JetBrains Mono",
                },
                radius="soft",
                density="comfortable",
                motion="subtle",
                signature_moves=[
                    "interactive UI",
                    "responsive layout",
                    "functional state",
                ],
            )
            content = ContentPack(
                brand_name="Functional App",
                tagline="",
                hero_headline="",
                hero_subhead="",
                primary_cta="",
                secondary_cta="",
                nav_items=[],
                features=[],
                testimonials=[],
                pricing_tiers=[],
                faqs=[],
                footer_links={},
            )
            file_set = _run_engineer(
                brief=brief,
                design=design,
                content=content,
            )
            trail.append(
                AgentStep(
                    agent="FunctionalEngineer",
                    summary="AI-generated functional application",
                )
            )

        name = f"{app_kind}-app"

        if is_patch:
            db.touch_project(project_id, entry=file_set.entry)
            return _persist_and_respond(
                project_id,
                file_set,
                prompt,
                trail,
                name_override=name,
            )

        new_id = db.create_project(name, file_set.entry)
        return _persist_and_respond(
            new_id,
            file_set,
            prompt,
            trail,
            name_override=name,
        )

    # -------- template intelligence (niche-aware multi-page websites) --------
    # Runs BEFORE the landing pipeline. Fires only when the prompt confidently
    # matches a known niche template ('chinese restaurant', 'japanese sushi',
    # etc.). When it fires we skip the brief LLM (we already know the structure
    # from the manifest), pick the design mode deterministically from the
    # manifest's hint, and run the existing Content Writer with strong niche
    # guardrails. If the Content Writer fails, the deterministic fallback
    # keeps the path robust. Non-matching prompts fall straight through to the
    # original landing pipeline below — zero behavior change there.
    # Categories the multi-page scaffold is verified to render well. The
    # dispatcher in scaffold_for_plan picks the right archetype per category;
    # anything outside this set falls through to the existing single-file
    # landing pipeline so we never regress what already works.
    MULTI_PAGE_CATEGORIES = {"restaurant", "saas", "portfolio", "ecommerce", "healthcare"}

    if not is_patch:
        try:
            decision = _classify_and_plan(prompt)
        except Exception as _ti_err:
            # Any failure in the template/reference-intelligence layer must
            # NEVER block generation — fall through to the regular landing
            # pipeline below. Surface the reason in the trail for debugging.
            trail.append(AgentStep(
                agent="TemplateIntelligence",
                summary=f"skipped (error: {type(_ti_err).__name__}); using landing pipeline",
            ))
            decision = None
        if (
            decision is not None
            and decision.fired
            and decision.plan is not None
            and decision.plan.category in MULTI_PAGE_CATEGORIES
        ):
            plan = decision.plan
            trail.append(AgentStep(
                agent="TemplateIntelligence",
                summary=decision.reason,
            ))

            seeded_brief = _brief_from_plan(prompt, plan)
            trail.append(AgentStep(
                agent="Brief",
                summary=f"seeded from {plan.template_key} · {len(seeded_brief.pages)} pages",
            ))

            seeded_design = _design_from_plan(plan)
            trail.append(AgentStep(
                agent="Design",
                summary=f"design_mode: {seeded_design.design_mode} (niche-default)",
            ))

            fallback_content = _content_from_plan(plan)
            seeded_content = _run_content_seeded(seeded_brief, seeded_design, plan)
            if seeded_content is None:
                content = fallback_content
                trail.append(AgentStep(agent="Content", summary="deterministic fallback (no LLM)"))
            else:
                content = _merge_seeded_content(seeded_content, fallback_content)
                trail.append(AgentStep(
                    agent="Content",
                    summary=f"brand: {content.brand_name} · niche-seeded",
                ))

            try:
                file_set = scaffold_for_plan(
                    seeded_brief, seeded_design, content, plan, brand=brand,
                )
            except Exception as _ms_err:
                # Multi-page scaffolder broken or unhappy — fall through to the
                # single-page landing pipeline below, but reuse what we already
                # produced (brief / design / content) instead of re-running
                # those LLM calls.
                trail.append(AgentStep(
                    agent="ScaffoldMulti",
                    summary=f"failed ({type(_ms_err).__name__}); falling back to landing",
                ))
                brief = seeded_brief
                design = seeded_design
                # content is already set above
            else:
                trail.append(AgentStep(
                    agent="ScaffoldMulti",
                    summary=(
                        f"{len(file_set.files)} files · multi-page router · "
                        f"{plan.template_key} ({plan.category})"
                    ),
                ))
                new_id = db.create_project(seeded_brief.name, file_set.entry)
                return _persist_and_respond(
                    new_id, file_set, prompt, trail, name_override=seeded_brief.name,
                )

    # -------- landing / marketing pipeline --------
    # Brief -> Design -> Content -> deterministic scaffold.
    # If the multi-page branch above already produced these (and only the
    # final scaffolder failed), reuse them so we don't re-burn LLM calls.
    if "brief" not in locals():
        brief = _run_brief(prompt)
        trail.append(AgentStep(
            agent="Brief",
            summary=f"{brief.app_type} · {brief.differentiator}",
        ))

    if "design" not in locals():
        design = _run_design(brief)
        trail.append(AgentStep(
            agent="Design",
            summary=(
                f"archetype: {design.archetype} · "
                + (", ".join(design.signature_moves[:2]) if design.signature_moves else "")
            ),
        ))

    if "content" not in locals():
        content = _run_content(brief, design)
        trail.append(AgentStep(
            agent="Content",
            summary=f"brand: {content.brand_name} · {len(content.features)} features",
        ))

    file_set = scaffold_project(brief, design, content)
    trail.append(AgentStep(
        agent="Scaffold",
        summary=f"{len(file_set.files)} files · single-page Tailwind",
    ))

    if is_patch:
        db.touch_project(project_id, entry=file_set.entry)
        return _persist_and_respond(project_id, file_set, prompt, trail, name_override=None)

    new_id = db.create_project(brief.name, file_set.entry)
    return _persist_and_respond(new_id, file_set, prompt, trail, name_override=brief.name)


_CHAT_SYSTEM = (
    "You are the assistant in an AI app builder. The user just said something "
    "that is NOT a request to build anything — it's small talk, a greeting, "
    "a question about you, or general chat. Reply briefly and naturally in "
    "1-3 short sentences. Match the user's energy: if they say 'hi', say "
    "'hi' back; if they ask what you can do, list two or three concrete "
    "examples like 'snake game', 'calculator', 'coffee shop landing page'. "
    "Never start a build, never produce code, never produce JSON, never use "
    "markdown headings. Plain prose. No emoji unless the user uses one first."
)


_CHAT_FALLBACK = (
    "Hey! I can build apps, games, landing pages, and generate images. Try "
    "'snake game', 'calculator with dark theme', or 'image of a sunset'."
)


def _chat_model() -> str:
    import os
    return os.getenv(
        "CHAT_MODEL",
        os.getenv("WORKER_MODEL", "groq/llama-3.3-70b-versatile"),
    )


def _llm_chat_reply(prompt: str) -> str:
    """Single short LLM call. Falls back to a static reply on any error."""
    try:
        resp = litellm.completion(
            model=_chat_model(),
            messages=[
                {"role": "system", "content": _CHAT_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.6,
            max_tokens=160,
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or _CHAT_FALLBACK
    except Exception:
        return _CHAT_FALLBACK


def _chat_response(prompt: str) -> GenerateResponse:
    """Conversational reply via a small LLM call — no project, no files."""
    reply = _llm_chat_reply(prompt)
    return GenerateResponse(
        project_id="",
        name="chat",
        stack="static",
        entry="",
        files=[],
        trail=[AgentStep(agent="Router", summary="intent: chat"),
               AgentStep(agent="Chat",   summary=reply[:80])],
        message=reply,
    )


def _math_response(prompt: str) -> GenerateResponse:
    """Arithmetic answer — evaluates safely, no LLM."""
    result = evaluate_math(prompt)
    if result is None:
        # Shouldn't happen — classifier only routes here when evaluate_math
        # returned a value. But be safe.
        return _chat_response(prompt)
    expr, value = result
    if isinstance(value, float):
        value_str = f"{value:.6g}"
    else:
        value_str = str(value)
    return GenerateResponse(
        project_id="",
        name="math",
        stack="static",
        entry="",
        files=[],
        trail=[AgentStep(agent="Router", summary="intent: math"),
               AgentStep(agent="Math",   summary=f"{expr} = {value_str}")],
        message=f"**{expr} = {value_str}**",
    )


def _image_response(prompt: str) -> GenerateResponse:
    """Image request — return a Pollinations URL inside the assistant message.

    The frontend's Chat component already detects pollinations.ai URLs and
    renders them as inline images, so the user sees the picture in chat.
    """
    subject = extract_image_subject(prompt)
    url = generate_image_url(
        f"{subject}, 8k, professional, cinematic lighting, no text, no watermark",
        width=1024,
        height=576,
    )
    return GenerateResponse(
        project_id="",
        name="image",
        stack="static",
        entry="",
        files=[],
        trail=[AgentStep(agent="Router", summary="intent: image"),
               AgentStep(agent="ImageGen", summary=f"Pollinations · {subject[:60]}")],
        message=f"Here's your image for **{subject}**:\n\n{url}",
    )


def _persist_and_respond(
    project_id: str,
    file_set: FileSet,
    prompt: str,
    trail: list[AgentStep],
    name_override: str | None,
) -> GenerateResponse:
    db.save_files(project_id, [f.model_dump() for f in file_set.files])
    db.touch_project(project_id, entry=file_set.entry)
    db.add_message(project_id, "user", prompt)
    db.add_message(
        project_id,
        "assistant",
        file_set.summary or "Generated.",
        agent="Crew",
    )
    proj = db.get_project(project_id) or {}
    return GenerateResponse(
        project_id=project_id,
        name=name_override or proj.get("name", "project"),
        stack="react-vite",
        entry=file_set.entry,
        files=file_set.files,
        trail=trail,
        message=file_set.summary or "Generated.",
    )
