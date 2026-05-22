"""Engineer agent — category-aware single-file React/Tailwind codegen.

Stage 4 (non-landing path) of the new pipeline. Receives:
  - ProductBrief (incl. classified app_type)
  - DesignSystem
  - Category-specific engineer_directive (injected from app_types.APP_TYPE_REGISTRY)

Output: a single src/App.tsx file as a string. The manager then merges this
with the boilerplate scaffold (package.json, index.html, etc.) and ships.

Scope is intentionally narrow: ONE file, not a multi-file project. Llama can
handle one focused file; it cannot handle a 20-file shadcn project.
"""

from __future__ import annotations

import os

from crewai import Agent


def _model() -> str:
    return os.getenv(
        "ENGINEER_MODEL",
        os.getenv("WORKER_MODEL", "groq/llama-3.3-70b-versatile"),
    )


def build_engineer(model: str | None = None) -> Agent:
    return Agent(
        role="Senior Frontend Engineer (ex-Vercel, ex-Linear)",
        goal=(
            "Generate ONE working React TypeScript component (src/App.tsx) for "
            "the requested app type. Use ONLY plain Tailwind classes plus the "
            "design tokens. Use ONLY whitelisted lucide-react icons. Every "
            "button MUST do something. NO marketing-page elements unless the "
            "category is 'landing'. Output strictly matches the FileSet schema "
            "with files=[{path:'src/App.tsx', content: '...'}]."
        ),
        backstory=(
            "You write tight, single-file React apps that compile and run. You "
            "are religious about category fit: if asked for a game, you build a "
            "playable game with keyboard input and a game loop — never a "
            "marketing page. If asked for a dashboard, you build a sidebar + "
            "stat cards + table, not a hero. You inline sample data when the "
            "app needs it (realistic names, dates, amounts — never lorem). You "
            "never invent shadcn/Radix imports — you write plain HTML elements "
            "styled with Tailwind. You import icons ONLY from lucide-react "
            "using a small fixed set. Every onClick has a real handler."
        ),
        llm=model or _model(),
        allow_delegation=False,
        verbose=True,
    )
