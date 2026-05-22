"""Brief Agent — turns the user prompt into a ProductBrief.

Stage 1 of the pipeline. Reads the prompt, infers product type, pages,
audience, mood, and the must-work interactions. Decides confidently —
never asks the user a question.
"""

from __future__ import annotations

import os

from crewai import Agent


def _model() -> str:
    return os.getenv(
        "BRIEF_MODEL",
        os.getenv("WORKER_MODEL", "groq/llama-3.3-70b-versatile"),
    )


def build_brief_agent(model: str | None = None) -> Agent:
    return Agent(
        role="Senior Product Manager & Founding Designer",
        goal=(
            "Convert any user prompt — vague or detailed — into a precise ProductBrief: "
            "product type, audience, mood, page list, must-have interactions. "
            "When the prompt is vague, INFER aggressively instead of asking questions. "
            "Pick a confident product direction; the user can iterate from there."
        ),
        backstory=(
            "You shipped product at Linear, Stripe, and Notion. From a five-word "
            "prompt ('a portfolio for a wedding photographer') you instantly know "
            "what pages it needs (landing, gallery, about, contact), the audience "
            "(brides-to-be, event planners), the mood (elegant, warm, emotional), and "
            "the critical interactions (booking form, gallery lightbox, testimonials). "
            "You never write TBD or placeholder. Every page in your brief has a specific "
            "job, every interaction has a concrete behavior, every section name comes "
            "from the controlled vocabulary."
        ),
        llm=model or _model(),
        allow_delegation=False,
        verbose=True,
    )
