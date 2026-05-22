"""Researcher agent — runs when the Planner sets needs_research=True.

Equipped with three free tools: DuckDuckGo search, Wikipedia lookup, and a
generic HTTP GET. No paid API keys required.
"""

from __future__ import annotations

import os

from crewai import Agent

from ..tools import duckduckgo_search, http_get, wikipedia_lookup


def build_researcher(model: str | None = None) -> Agent:
    return Agent(
        role="Research Analyst",
        goal=(
            "Find the specific facts the Coder needs: API shapes, game mechanics, "
            "library versions. Use DuckDuckGo for current info, Wikipedia for "
            "well-established facts, and http_get for raw API/doc URLs. Return a "
            "short bulleted brief — facts only, no opinions, no code."
        ),
        backstory=(
            "You are a fast researcher. You pick the right tool: Wikipedia for "
            "general topics (game rules, algorithms), DuckDuckGo for current info, "
            "http_get for specific URLs. You make at most 3 tool calls, then "
            "synthesize a 5-10 bullet brief. You never write code. You never "
            "speculate — if a tool returns nothing, say so."
        ),
        llm=model or os.getenv("WORKER_MODEL", "gpt-4o-mini"),
        tools=[duckduckgo_search, wikipedia_lookup, http_get],
        allow_delegation=False,
        max_iter=5,
        verbose=True,
    )
