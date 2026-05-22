"""Coder agent — turns a PlanSpec into actual file contents (FileSet)."""

from __future__ import annotations

import os

from crewai import Agent


def build_coder(model: str | None = None) -> Agent:
    return Agent(
        role="Full-Stack Engineer",
        goal=(
            "Implement every file listed in the plan. Output ONLY a JSON object "
            "matching the FileSet schema. Code must be runnable as-is — no "
            "placeholders, no TODOs, no '// implement this'."
        ),
        backstory=(
            "You are a senior full-stack engineer who writes idiomatic, modern "
            "code. For React+Vite projects you produce: package.json (with react, "
            "react-dom, vite, @vitejs/plugin-react), vite.config.js, index.html "
            "with the root div, src/main.jsx, src/App.jsx, and any components. "
            "For static projects you produce index.html with inline <style> and "
            "<script>. You never use external CDN scripts. You never reference "
            "files you didn't create. You write complete, working code."
        ),
        llm=model or os.getenv("WORKER_MODEL", "gpt-4o-mini"),
        allow_delegation=False,
        verbose=True,
    )
