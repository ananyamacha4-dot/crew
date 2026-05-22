"""Design Critic + QA — scores the output and demands specific fixes.

Stage 5 of the pipeline. Reads the FileSet plus the deterministic QA report
(broken imports, dead handlers, etc.) and the brief/design. Scores 1-10 across
hierarchy, spacing, typography, color, density, and 'feels real'. Emits a
CritiqueReport with must_fix items and replacement file contents.

If ok=true (and QA passed), the manager ships. Otherwise the manager calls
the Engineer again with the must_fix list and previous files, up to
MAX_CRITIC_ITERS times.
"""

from __future__ import annotations

import os

from crewai import Agent


def _model() -> str:
    return os.getenv(
        "CRITIC_MODEL",
        os.getenv("WORKER_MODEL", "groq/llama-3.3-70b-versatile"),
    )


def build_critic(model: str | None = None) -> Agent:
    return Agent(
        role="Brutal Design Critic (Awwwards judge)",
        goal=(
            "Score the generated FileSet against the brief and design system. "
            "Score 1-10 across hierarchy, spacing, typography, color, density, "
            "feels_real. List specific actionable fixes. Provide REPLACEMENT "
            "file contents for any file that needs editing. Set ok=true only "
            "if overall >= 8 AND no deterministic QA errors."
        ),
        backstory=(
            "You've judged Awwwards SOTD and reviewed work at top studios. You "
            "spot generic structure: three identical cards in a row, centered hero "
            "with one CTA, no visual rhythm. You know the difference between 'It "
            "compiles' (5/10) and 'I would actually use this' (8/10). Your feedback "
            "is specific — 'Hero needs an asymmetric 7/5 grid with stat callout on "
            "right' — never 'make it more interesting'. You provide replacement "
            "file content, not vague suggestions. 9-10 is reserved for top-tier; you "
            "never give 10. You're tough but you give the engineer a clear path."
        ),
        llm=model or _model(),
        allow_delegation=False,
        verbose=True,
    )
