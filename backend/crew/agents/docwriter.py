"""DocWriter agent — writes README.md for the generated project."""

from __future__ import annotations

import os

from crewai import Agent


def build_docwriter(model: str | None = None) -> Agent:
    return Agent(
        role="Technical Writer",
        goal=(
            "Write a concise README.md for the generated project. Include: one-line "
            "description, how to run, controls/usage if it's a game, and the file "
            "structure. Plain markdown, no fluff."
        ),
        backstory=(
            "You write the README a developer actually reads. You skip badges, "
            "skip 'Table of Contents', skip philosophy. You include exactly: what "
            "this is, how to run it, how to use it. Five sections max."
        ),
        llm=model or os.getenv("WORKER_MODEL", "gpt-4o-mini"),
        allow_delegation=False,
        verbose=True,
    )
