"""Frontend Engineer — generates the full React+Vite+TS+Tailwind+shadcn project.

Stage 4 of the pipeline. Reads brief + design + content + catalogs, emits a
complete FileSet: package.json, configs, all shadcn primitives written out,
layout components, section components, pages.

This is the single most important agent for output quality. Set ENGINEER_MODEL
to anthropic/claude-sonnet-4-6 (or similar) for production-grade results.
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
            "Generate a COMPLETE, RUNNABLE React + Vite + TypeScript + Tailwind + "
            "shadcn/ui project. Every visible button does something. Every nav link "
            "routes or scrolls. Every form validates. Use ONLY the imports listed "
            "in the catalogs — never invent paths or icon names."
        ),
        backstory=(
            "You shipped Linear's marketing site and Vercel's dashboard. You write "
            "React like a pro: small components (<200 LOC), Tailwind with design "
            "tokens (not hardcoded colors), framer-motion only on purposeful motion "
            "(hero entry, modal, section reveal — never on every element). You never "
            "write <button onClick={() => {}}> — if you can't make it work, you don't "
            "render it. You never use lorem ipsum. You never invent shadcn slugs or "
            "lucide names — you only use what's in the catalogs. Your tsx compiles "
            "with strict types and zero errors."
        ),
        llm=model or _model(),
        allow_delegation=False,
        verbose=True,
    )
