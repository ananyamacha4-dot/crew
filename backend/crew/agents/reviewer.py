"""Reviewer agent — sanity-checks the FileSet and emits a ReviewReport."""

from __future__ import annotations

import os

from crewai import Agent


def build_reviewer(model: str | None = None) -> Agent:
    return Agent(
        role="Code Reviewer & QA",
        goal=(
            "Review the generated files. Catch obvious bugs: missing imports, "
            "undefined references, package.json that doesn't list a dep that the "
            "code imports, broken JSX, missing index.html root div. Emit a "
            "ReviewReport with ok=True only if the code will boot."
        ),
        backstory=(
            "You have reviewed thousands of PRs. You are not a perfectionist — "
            "you only flag things that will actually break at runtime. If the "
            "code will boot and the obvious user flow works, you mark it ok. "
            "When you do find an issue, you provide the exact replacement file "
            "content in 'fixes', not just a description."
        ),
        llm=model or os.getenv("WORKER_MODEL", "gpt-4o-mini"),
        allow_delegation=False,
        verbose=True,
    )
