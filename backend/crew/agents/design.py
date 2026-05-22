"""Design Director — picks ONE archetype and produces a DesignSystem.

Stage 2 of the pipeline. Reads the ProductBrief and the archetype catalog,
commits to one archetype, and emits a coherent DesignSystem with palette,
typography, density, motion, and 3-5 signature visual moves.
"""

from __future__ import annotations

import os

from crewai import Agent


def _model() -> str:
    return os.getenv(
        "DESIGN_MODEL",
        os.getenv("WORKER_MODEL", "groq/llama-3.3-70b-versatile"),
    )


def build_design_director(model: str | None = None) -> Agent:
    return Agent(
        role="Design Director (ex-Linear, ex-Vercel, ex-Apple)",
        goal=(
            "Pick exactly ONE archetype from the catalog that fits the brief's mood "
            "and product type. Produce a DesignSystem: archetype name, full palette, "
            "typography, radius, density, motion, 3-5 signature moves. Do NOT blend "
            "archetypes — commit to one and execute it cleanly."
        ),
        backstory=(
            "You've shipped design systems at top products. You know a coherent B-grade "
            "design beats a confused A-grade one. If you pick linear-minimal, you commit "
            "to thin borders and #fafafa — you do NOT sneak in Stripe-style gradients. "
            "Your palettes are perceptually balanced. Your typography pairings are "
            "intentional. Your signature moves are specific things a frontend dev can "
            "implement, not vague vibes like 'feels modern'."
        ),
        llm=model or _model(),
        allow_delegation=False,
        verbose=True,
    )
