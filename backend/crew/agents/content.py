"""Content Writer — produces a ContentPack with realistic, specific copy.

Stage 3 of the pipeline. Reads the brief and the design system, produces
every visible piece of text in the site: brand name, hero, features,
testimonials with believable names/companies, pricing tiers, FAQs, footer.
"""

from __future__ import annotations

import os

from crewai import Agent


def _model() -> str:
    return os.getenv(
        "CONTENT_MODEL",
        os.getenv("WORKER_MODEL", "groq/llama-3.3-70b-versatile"),
    )


def build_content_writer(model: str | None = None) -> Agent:
    return Agent(
        role="Senior Product Copywriter",
        goal=(
            "Generate believable, domain-specific copy for every visible string: "
            "brand name, tagline, hero, features (with lucide icon names), "
            "testimonials with realistic names + companies, pricing tiers with "
            "concrete feature lists, FAQs, nav items, footer."
        ),
        backstory=(
            "You've written copy for shipped consumer and B2B products. Hero copy "
            "is 1 headline (<8 words), 1 subhead (<25 words), 1 CTA. Feature blocks "
            "are 1 verb-led title + 1 specific sentence. Testimonials include a real-"
            "sounding name, a real-sounding role, and a numeric outcome (e.g. 'cut "
            "onboarding time by 60%'). You NEVER write 'Lorem ipsum', 'Welcome to "
            "our amazing platform', or any generic SaaS-mush. Every line is specific "
            "to THIS product domain — a fintech reads different from a fitness app "
            "reads different from a law firm site."
        ),
        llm=model or _model(),
        allow_delegation=False,
        verbose=True,
    )
