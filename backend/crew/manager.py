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
    build_design_director,
)
from .archetypes import archetypes_catalog_text
from .scaffold import scaffold_project
from .schemas import (
    AgentStep,
    ContentPack,
    DesignSystem,
    FileSet,
    GeneratedFile,
    GenerateResponse,
    ProductBrief,
)

MAX_CRITIC_ITERS = int(os.getenv("MAX_CRITIC_ITERS", "1"))


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


def _parse_into(text: str, model_cls: Type[M]) -> M:
    raw = _strip_fences(text)
    data: Any
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        repaired = repair_json(raw, return_objects=True)
        if isinstance(repaired, str):
            raise RuntimeError(f"unparseable LLM output: {raw[:300]!r}")
        data = repaired
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
        "Produce a ProductBrief JSON with these fields:\n"
        "  name             (kebab-case)\n"
        "  product_type     (one short label, e.g. 'saas-landing', 'portfolio',\n"
        "                    'ecommerce', 'dashboard', 'blog', 'event',\n"
        "                    'mobile-app-landing', 'agency', 'restaurant')\n"
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
        "  data-table, chart-panel.\n\n"
        "INTERACTION EXAMPLES (each must be CONCRETE):\n"
        "  - element 'nav.cta', location 'header right', behavior 'route to /signup'\n"
        "  - element 'pricing.upgrade', location 'pricing card 2', behavior 'open UpgradeDialog'\n"
        "  - element 'contact.submit', location 'contact form', behavior 'react-hook-form + zod, then toast.success'\n\n"
        "If the prompt is vague, INFER aggressively — pick a confident direction. "
        "Output ONLY a JSON object. No commentary. No markdown fences."
    )
    raw = _run_task(agent, description, "A JSON object matching ProductBrief.")
    return _parse_into(raw, ProductBrief)


def _run_design(brief: ProductBrief) -> DesignSystem:
    agent = build_design_director()
    description = (
        f"PRODUCT BRIEF:\n{brief.model_dump_json(indent=2)}\n\n"
        f"ARCHETYPE CATALOG (pick exactly ONE archetype key):\n"
        f"{archetypes_catalog_text()}\n\n"
        "Produce a DesignSystem JSON:\n"
        "  archetype         (one of the catalog keys above)\n"
        "  palette           (list of {name, base hex, description}; "
        "at least 'primary', 'neutral', 'accent')\n"
        "  fonts             ({display, body, mono} font-family strings)\n"
        "  radius            ('sharp' | 'subtle' | 'soft' | 'pill')\n"
        "  density           ('tight' | 'comfortable' | 'spacious')\n"
        "  motion            ('none' | 'subtle' | 'expressive')\n"
        "  signature_moves   (3-5 specific moves you will execute)\n\n"
        "Commit to ONE archetype. Do NOT blend. Output ONLY JSON, no fences."
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
        " 4. Every <Link to='/x'> MUST have a matching <Route path='/x'> in App.tsx.\n"
        " 5. Use the ContentPack copy VERBATIM. Never invent your own marketing copy.\n"
        "    Never use 'lorem ipsum'.\n"
        " 6. Use the design palette via CSS variables / Tailwind tokens.\n"
        "    Do NOT hardcode hex colors in JSX.\n"
        " 7. Mobile-first responsive: every section must work at 375px, 768px, 1280px.\n"
        " 8. framer-motion only on purposeful motion (hero entry, modal, section\n"
        "    reveal). Never animate every element.\n"
        " 9. Forms: react-hook-form + zod. Inline error messages + sonner toast on submit.\n"
        "10. Render sections in the order listed in brief.pages[].sections.\n"
        "11. No '...' placeholders. No TODOs. No commented-out code. Complete content.\n"
        "12. JSON output rules — STRICT:\n"
        "    - Top-level keys: 'files' (list of {path, content}), 'entry', 'summary'.\n"
        "    - Inside string values, escape special chars: \\n for newlines,\n"
        "      \\\" for double-quotes, \\\\ for backslashes. NEVER use literal newlines\n"
        "      inside JSON string values.\n"
        "    - 'entry' must be 'index.html'.\n"
        "    - No markdown fences. No commentary. Just the JSON object.\n"
    )

    description = "\n\n".join(parts)
    raw = _run_task(agent, description, "A JSON object matching FileSet.")
    return _parse_into(raw, FileSet)


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

    # -------- patch mode --------
    # For now patches re-run the full create pipeline on the new prompt.
    # The previous project's files are discarded; the scaffolded result wins.
    # (We can add real "diff this file" patching later once create-mode is stable.)
    if is_patch:
        # fall through to create-mode flow; we'll just overwrite the existing project files
        pass

    # -------- create mode (LLM agents for content, deterministic scaffold for code) --------
    brief = _run_brief(prompt)
    trail.append(AgentStep(
        agent="Brief",
        summary=f"{brief.product_type} · {brief.differentiator}",
    ))

    design = _run_design(brief)
    trail.append(AgentStep(
        agent="Design",
        summary=(
            f"archetype: {design.archetype} · "
            + (", ".join(design.signature_moves[:2]) if design.signature_moves else "")
        ),
    ))

    content = _run_content(brief, design)
    trail.append(AgentStep(
        agent="Content",
        summary=f"brand: {content.brand_name} · {len(content.features)} features",
    ))

    # Deterministic scaffold — produces a complete, runnable React+Vite+Tailwind
    # project from the brief/design/content. No LLM in this stage, so the code
    # always compiles and renders in Sandpack.
    file_set = scaffold_project(brief, design, content)
    trail.append(AgentStep(
        agent="Scaffold",
        summary=f"{len(file_set.files)} files · single-page Tailwind",
    ))

    if is_patch:
        db.touch_project(project_id, entry=file_set.entry)  # type: ignore[arg-type]
        return _persist_and_respond(project_id, file_set, prompt, trail, name_override=None)  # type: ignore[arg-type]

    new_id = db.create_project(brief.name, file_set.entry)
    return _persist_and_respond(new_id, file_set, prompt, trail, name_override=brief.name)


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
