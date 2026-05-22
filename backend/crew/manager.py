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
    build_engineer,
)
from .app_types import (
    APP_TYPE_REGISTRY,
    DESIGN_QUALITY_RULES,
    PALETTE_HINTS,
    app_type_classifier_catalog,
    get_app_type,
)
from .archetypes import archetypes_catalog_text
from .design_modes import (
    DESIGN_MODES,
    design_mode_for_app_type,
    design_modes_catalog_text,
    get_design_mode,
)
from .scaffold import design_tokens_block, scaffold_boilerplate, scaffold_project
from .schemas import (
    AgentStep,
    ContentPack,
    DesignSystem,
    FileSet,
    GeneratedFile,
    GenerateResponse,
    NavItem,
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
        "STEP 1 — CLASSIFY the app_type. Pick ONE key from this catalog:\n\n"
        f"{app_type_classifier_catalog()}\n\n"
        "Classification rules:\n"
        "  - 'snake game', '2048', 'tic tac toe' -> game\n"
        "  - 'calculator', 'unit converter', 'qr generator', 'password generator' -> tool\n"
        "  - 'sales dashboard', 'analytics view', 'crypto tracker' -> dashboard\n"
        "  - 'todo list', 'kanban board', 'pomodoro' -> productivity\n"
        "  - 'chat app', 'whatsapp clone' -> chat\n"
        "  - 'sneaker store', 'plant shop' -> ecommerce\n"
        "  - 'landing page for X', 'website for X business' -> landing\n"
        "  - 'portfolio for a designer' -> portfolio\n"
        "  - 'admin panel for users' -> admin\n"
        "  - 'instagram-style feed', 'twitter clone' -> social\n"
        "  - 'markdown editor', 'code editor' -> editor\n"
        "  - 'banking app UI', 'mobile fitness app screen' -> mobile-app\n\n"
        "STEP 2 — Produce the ProductBrief JSON object. Required fields:\n"
        "  name                  (kebab-case)\n"
        "  app_type              (one of the catalog keys; SEE CLASSIFICATION RULES ABOVE)\n"
        "  primary_screen_goal   (one sentence: what the LOAD-TIME experience\n"
        "                         must let the user do. NOT a marketing pitch.\n"
        "                         e.g. 'play snake with arrow keys',\n"
        "                              'calculate arithmetic with a button grid',\n"
        "                              'see today's sales metrics at a glance')\n"
        "  specific_features     (list of strings — concrete things to include,\n"
        "                         derived from the user prompt. e.g. for calculator:\n"
        "                         ['number pad 0-9', 'operations +-*/',\n"
        "                          'decimal point', 'clear button', 'history list'])\n"
        "  audience              (one sentence)\n"
        "  mood                  (3-5 adjectives)\n"
        "  differentiator        (one sentence)\n\n"
        "CRITICAL:\n"
        "  - app_type determines what gets built. DO NOT default to 'landing'\n"
        "    unless the user explicitly asked for a marketing/landing site.\n"
        "  - 'calculator with dark theme' is app_type=tool, NOT landing.\n"
        "  - 'snake game' is app_type=game, NOT landing.\n"
        "  - 'dashboard for X' is app_type=dashboard, NOT landing.\n\n"
        "Output ONLY a JSON object. No commentary. No markdown fences."
    )
    raw = _run_task(agent, description, "A JSON object matching ProductBrief.")
    return _parse_into(raw, ProductBrief)


def _run_engineer_app_tsx(brief: ProductBrief, design: DesignSystem) -> str:
    """Non-landing codegen: LLM emits a single src/App.tsx string for the app type."""
    agent = build_engineer()
    info = get_app_type(brief.app_type)

    forbidden = "; ".join(info.get("forbidden_blocks", [])) or "(none)"
    required = "; ".join(info.get("required_blocks", [])) or "(none)"
    specific = "\n".join(f"  - {f}" for f in brief.specific_features) or "  (none specified)"

    palette_hint = PALETTE_HINTS.get(brief.app_type, "Match the archetype palette.")

    description = (
        f"USER PROMPT (paraphrased via brief):\n"
        f"  name: {brief.name}\n"
        f"  app_type: {brief.app_type}\n"
        f"  audience: {brief.audience}\n"
        f"  mood: {', '.join(brief.mood) if brief.mood else '(unspecified)'}\n"
        f"  primary_screen_goal: {brief.primary_screen_goal}\n"
        f"  specific_features:\n{specific}\n\n"
        f"CATEGORY ({info['label']}):\n"
        f"  primary_layout: {info['primary_layout']}\n"
        f"  must_include: {required}\n"
        f"  must_NOT_include: {forbidden}\n\n"
        f"CATEGORY DIRECTIVE:\n{info['engineer_directive']}\n\n"
        f"PALETTE FEEL FOR THIS CATEGORY:\n  {palette_hint}\n\n"
        f"{DESIGN_QUALITY_RULES}\n\n"
        f"{design_tokens_block(design)}\n\n"
        "FIXED IMPORTS YOU MAY USE (and nothing else from external packages):\n"
        "  import { useState, useEffect, useRef, useMemo } from 'react';\n"
        "  import { ArrowRight, ArrowLeft, ArrowUp, ArrowDown, Check, X, Plus,\n"
        "    Minus, Star, Heart, Search, Settings, Bell, User, Users, Home,\n"
        "    Mail, Send, Calendar, Clock, MapPin, Eye, EyeOff, Trash2, Edit,\n"
        "    Copy, Download, Upload, Filter, ChevronRight, ChevronLeft,\n"
        "    ChevronDown, ChevronUp, Menu, MoreHorizontal, Play, Pause,\n"
        "    RefreshCw, Sparkles, Zap, Code, Terminal, Database, Github,\n"
        "    TrendingUp, TrendingDown, BarChart3, ShoppingCart, CreditCard,\n"
        "    DollarSign, Sun, Moon, Layers, Rocket, Target, Award\n"
        "  } from 'lucide-react';\n"
        "  import { toast } from 'sonner';\n"
        "  import { cn } from './lib/utils';\n\n"
        "OUTPUT RULES — non-negotiable:\n"
        " 1. Output ONLY the file content of src/App.tsx. NO markdown fences.\n"
        "    NO commentary. NO 'Here is the code:'. Start with `import` and end\n"
        "    with the final closing `}` of the App component.\n"
        " 2. Export App as DEFAULT: `export default function App() { ... }`.\n"
        " 3. Use ONLY plain HTML elements + Tailwind classes. NO shadcn,\n"
        "    NO @radix-ui, NO router, NO third-party UI library imports.\n"
        " 4. Use ONLY tokens from the AVAILABLE TAILWIND TOKENS block above.\n"
        "    No hardcoded hex colors.\n"
        " 5. Every button MUST have a real handler — alert/toast/setState/scroll.\n"
        "    NO onClick={() => {}} stubs. If you can't make it work, don't render.\n"
        " 6. NO 'lorem ipsum'. NO 'placeholder' text. NO 'TODO'.\n"
        " 7. Inline sample data realistically (names, dates, amounts).\n"
        " 8. Mobile-responsive. Container with sensible max width.\n"
        " 9. Single file. ~150-400 lines target. Define small helper sub-components\n"
        "    inside the same file if needed.\n"
        "10. The required_blocks listed above MUST appear. The must_NOT_include\n"
        "    blocks must NOT appear under any circumstance.\n"
    )

    raw = _run_task(agent, description, "The raw TSX file content for src/App.tsx.")
    return _clean_tsx_output(raw)


def _run_polish_pass(brief: ProductBrief, design: DesignSystem, first_pass: str) -> str:
    """Second-pass aesthetic refinement on App.tsx. Functionality stays the
    same; spacing / hierarchy / hover states / shadows / motion get refined.

    Toggle via POLISH_PASS env (default on for non-landing types). Skipping
    saves ~30-60s of LLM time at a meaningful quality cost.
    """
    if os.getenv("POLISH_PASS", "1") not in {"1", "true", "yes"}:
        return first_pass

    agent = build_engineer()  # same role, different task framing
    description = (
        "You are running a UI POLISH PASS. The component already exists and "
        "WORKS. Your job is to make it look like a real funded-startup product "
        "(Linear / Vercel / Stripe / Notion / Raycast tier). DO NOT change "
        "functionality. DO NOT remove handlers. DO NOT change state logic.\n\n"
        f"APP CONTEXT: app_type={brief.app_type}, name={brief.name}, "
        f"goal='{brief.primary_screen_goal}'.\n\n"
        f"{design_tokens_block(design)}\n\n"
        "REFINEMENTS YOU MUST APPLY (this is the spec):\n"
        "  HIERARCHY:\n"
        "    - Big headlines: font-display + tracking-tight + font-bold/-semibold.\n"
        "    - Sub-text: text-muted-foreground + text-sm.\n"
        "    - Increase vertical rhythm between sections (py-12+ where appropriate).\n"
        "  SURFACES:\n"
        "    - Cards: use surface-1 (or bg-card + border-border), p-6+, rounded.\n"
        "    - Featured / hovered cards: add shadow-lifted or hover-lift.\n"
        "    - For neon / dark modes, add a glow on the hero CTA and active stats.\n"
        "  HOVERS & MOTION:\n"
        "    - Every <button> gets a hover state (hover:bg-..., hover:opacity-90, OR hover-lift).\n"
        "    - Add transition-colors / transition-opacity / transition-transform where appropriate.\n"
        "    - Heroes/headers get animate-fade-up; section series can stagger via\n"
        "      animate-fade-up-1, -2, -3.\n"
        "  ACCENTS:\n"
        "    - Use gradient-text on ONE big headline (the hero or page title).\n"
        "    - Optionally a gradient-bg badge or subtle gradient-bg block as accent.\n"
        "    - Consider a grid-pattern or dot-pattern background behind the hero "
        "      (use absolute overlay).\n"
        "  POLISH:\n"
        "    - Icons next to titles where helpful.\n"
        "    - Pill / badge for status: bg-primary/10 text-primary rounded-full px-3 py-1 text-xs.\n"
        "    - Consistent spacing: gap-6 in grids, gap-2 inside cards.\n"
        "    - Container: max-w-6xl mx-auto px-6.\n"
        "  FORBIDDEN:\n"
        "    - Removing functionality. Removing onClick handlers. Removing state.\n"
        "    - Hardcoded hex colors. Use design tokens only.\n"
        "    - Excessive animation. Subtle only.\n\n"
        "OUTPUT: re-emit the FULL App.tsx (start with `import`, end with the\n"
        "final `}` of App). NO markdown fences. NO commentary. NO explanation.\n\n"
        "FIRST-PASS CODE TO REFINE:\n"
        "```tsx\n"
        f"{first_pass}\n"
        "```\n"
    )
    raw = _run_task(agent, description, "The refined TSX content for src/App.tsx.")
    refined = _clean_tsx_output(raw)
    # Safety net: if the polish pass produced something tiny (LLM truncation),
    # fall back to the first pass.
    if len(refined) < 0.6 * len(first_pass):
        return first_pass
    return refined


_FENCE_PAT = re.compile(r"^```[a-zA-Z]*\s*\n?|\n?```\s*$", re.MULTILINE)
_EXPLAIN_PREFIX_PAT = re.compile(r"^[\s\S]*?(?=^import\s)", re.MULTILINE)


def _clean_tsx_output(raw: str) -> str:
    """Strip markdown fences and any prose preamble the LLM added."""
    s = raw.strip()
    # Strip leading/trailing code fences.
    s = _FENCE_PAT.sub("", s)
    # If the LLM added "Here is the code:\n\nimport React from ...", chop the preamble.
    m = re.search(r"(?ms)^import\s.+", s)
    if m:
        s = s[m.start():]
    return s.strip()


def _run_design(brief: ProductBrief) -> DesignSystem:
    agent = build_design_director()
    default_mode = design_mode_for_app_type(brief.app_type)
    description = (
        f"PRODUCT BRIEF:\n{brief.model_dump_json(indent=2)}\n\n"
        "STEP 1 — Pick a DESIGN MODE that fits this app's mood and category.\n"
        f"  Default for app_type='{brief.app_type}': {default_mode}\n"
        f"  You may override if the brief.mood points elsewhere.\n\n"
        f"{design_modes_catalog_text()}\n\n"
        f"STEP 2 — Pick an ARCHETYPE (visual personality):\n"
        f"{archetypes_catalog_text()}\n\n"
        "Produce a DesignSystem JSON:\n"
        "  design_mode       (REQUIRED — one of the design_mode keys above)\n"
        "  archetype         (one of the archetype keys above)\n"
        "  palette           (list of {name, base hex, description}; "
        "primary + neutral + accent at minimum)\n"
        "  fonts             ({display, body, mono} font-family strings)\n"
        "  radius            ('sharp' | 'subtle' | 'soft' | 'pill')\n"
        "  density           ('tight' | 'comfortable' | 'spacious')\n"
        "  motion            ('none' | 'subtle' | 'expressive')\n"
        "  shadow_style      ('flat' | 'subtle-paper' | 'soft-layered' | 'neon-glow')\n"
        "  animation_style   ('none' | 'smooth' | 'snappy' | 'playful' | 'graceful')\n"
        "  signature_moves   (3-5 specific visual moves)\n\n"
        "Commit fully — do NOT blend modes. Output ONLY JSON, no fences."
    )
    raw = _run_task(agent, description, "A JSON object matching DesignSystem.")
    ds = _parse_into(raw, DesignSystem)
    # Hard floor: if design_mode is missing/unknown, use the category default.
    if ds.design_mode not in DESIGN_MODES:
        ds.design_mode = default_mode
    return ds


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

    # --- Stage 1: Brief (classifies app_type) ---
    brief = _run_brief(prompt)
    trail.append(AgentStep(
        agent="Brief",
        summary=f"app_type: {brief.app_type} · goal: {brief.primary_screen_goal[:80]}",
    ))

    # --- Stage 2: Design ---
    design = _run_design(brief)
    trail.append(AgentStep(
        agent="Design",
        summary=(
            f"archetype: {design.archetype}"
            + (f" · {', '.join(design.signature_moves[:2])}" if design.signature_moves else "")
        ),
    ))

    # --- Stage 3 + 4: branch by app_type ---
    if brief.app_type == "landing":
        # Landing: run Content writer, then deterministic scaffold (works well).
        content = _run_content(brief, design)
        trail.append(AgentStep(
            agent="Content",
            summary=f"brand: {content.brand_name} · {len(content.features)} features",
        ))
        file_set = scaffold_project(brief, design, content)
        trail.append(AgentStep(
            agent="Scaffold",
            summary=f"{len(file_set.files)} files · landing template",
        ))
    else:
        # Non-landing: skip Content writer (no marketing copy needed).
        # Boilerplate from scaffold + LLM-generated category-specific App.tsx,
        # then a UI Polish Pass that refines aesthetics without changing behavior.
        stub_content = _stub_content_for(brief)
        boilerplate = scaffold_boilerplate(stub_content, design)

        first_pass = _run_engineer_app_tsx(brief, design)
        trail.append(AgentStep(
            agent="Engineer",
            summary=f"{brief.app_type} App.tsx · first pass · {len(first_pass)} chars",
        ))

        polished = _run_polish_pass(brief, design, first_pass)
        if polished != first_pass:
            trail.append(AgentStep(
                agent="Polish",
                summary=f"refined to {len(polished)} chars (Δ {len(polished) - len(first_pass):+d})",
            ))

        files = list(boilerplate.files) + [
            GeneratedFile(path="src/App.tsx", content=polished),
        ]
        file_set = FileSet(
            files=files,
            entry="public/index.html",
            summary=f"{brief.app_type}: {brief.name}",
        )

    # --- Persist & respond ---
    if is_patch:
        db.touch_project(project_id, entry=file_set.entry)  # type: ignore[arg-type]
        return _persist_and_respond(project_id, file_set, prompt, trail, name_override=None)  # type: ignore[arg-type]

    new_id = db.create_project(brief.name, file_set.entry)
    return _persist_and_respond(new_id, file_set, prompt, trail, name_override=brief.name)


def _stub_content_for(brief: ProductBrief) -> ContentPack:
    """Minimal ContentPack for non-landing apps. Only brand_name + a generic
    hero are used (the latter is just for the <title> tag in index.html)."""
    brand = brief.name.replace("-", " ").title() if brief.name else "App"
    return ContentPack(
        brand_name=brand,
        tagline="",
        hero_headline=brand,
        hero_subhead=brief.primary_screen_goal or "",
        primary_cta="Open",
        nav_items=[NavItem(label="Home", route="/")],
        features=[],
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
