"""Design-reference understanding — the 10 LLM prompts from the spec.

When a user says "make it look like Apple" or "Spotify-inspired dashboard",
we want the design system to absorb that reference rather than ignore it.
This module owns:

  1. A canonical list of 10 LLM prompts that interrogate a design reference.
     Each prompt is reusable on its own; together they form a battery the
     Design Director can run as needed.

  2. A lightweight `detect_design_inspiration()` heuristic that pulls brand
     names / aesthetic adjectives out of the user prompt so we know which
     prompts to fire.

This module is purely additive and never modifies the existing pipeline.
The hybrid pipeline (`crew.hybrid_pipeline`) is the opt-in caller.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


# ---------------------------------------------------------------------------
# The 10 design-reference prompts (spec, verbatim intent)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DesignReferencePrompt:
    id: str
    title: str
    template: str

    def render(self, *, user_prompt: str, reference: str | None = None) -> str:
        ref = reference or "[no explicit reference — infer from the user prompt]"
        return self.template.format(user_prompt=user_prompt.strip(), reference=ref)


DESIGN_REFERENCE_PROMPTS: tuple[DesignReferencePrompt, ...] = (
    DesignReferencePrompt(
        id="01-extract-language",
        title="Extract design language from the reference",
        template=(
            "USER PROMPT:\n\"\"\"\n{user_prompt}\n\"\"\"\n\n"
            "REFERENCE: {reference}\n\n"
            "Analyze the user's requested brand/design inspiration and extract:\n"
            "  - layout style\n"
            "  - spacing system\n"
            "  - typography style\n"
            "  - card design\n"
            "  - motion language\n"
            "  - color system\n"
            "  - component density\n"
            "  - UI personality\n\n"
            "Return STRICT JSON with one field per item above."
        ),
    ),
    DesignReferencePrompt(
        id="02-aesthetic-bucket",
        title="Classify into an aesthetic bucket",
        template=(
            "USER PROMPT:\n\"\"\"\n{user_prompt}\n\"\"\"\n\n"
            "REFERENCE: {reference}\n\n"
            "Pick ONE bucket that best describes what the user wants:\n"
            "  - luxury\n  - minimal\n  - brutalist\n  - futuristic\n"
            "  - glassmorphism\n  - editorial\n  - dashboard\n"
            "  - neon cyberpunk\n  - soft modern\n  - enterprise\n\n"
            "Return JSON: {{\"bucket\": \"<one>\", \"why\": \"<one sentence>\"}}."
        ),
    ),
    DesignReferencePrompt(
        id="03-design-tokens",
        title="Generate a reusable design token system",
        template=(
            "USER PROMPT:\n\"\"\"\n{user_prompt}\n\"\"\"\n\n"
            "REFERENCE: {reference}\n\n"
            "Generate a reusable design token system from the inspiration. "
            "Return STRICT JSON with these fields:\n"
            "  colors:      {{primary, secondary, accent, background, surface, foreground, muted}}\n"
            "  spacing:     scale of 8 values in rem\n"
            "  radius:      {{sm, md, lg, full}}\n"
            "  typography:  {{display, body, mono, scale: array of 8 sizes in rem}}\n"
            "  shadow:      {{sm, md, lg, glow}}\n"
            "  motion:      {{duration_fast, duration_base, duration_slow, ease}}"
        ),
    ),
    DesignReferencePrompt(
        id="04-component-set",
        title="Generate matching component set",
        template=(
            "USER PROMPT:\n\"\"\"\n{user_prompt}\n\"\"\"\n\n"
            "REFERENCE: {reference}\n\n"
            "Generate matching:\n"
            "  - buttons\n  - inputs\n  - cards\n  - modals\n"
            "  - navbars\n  - sidebars\n"
            "...using the detected design language. Return JSON with one "
            "object per component containing: {{role, variants: [], tokens_used: []}}."
        ),
    ),
    DesignReferencePrompt(
        id="05-product-archetype",
        title="Detect product archetype",
        template=(
            "USER PROMPT:\n\"\"\"\n{user_prompt}\n\"\"\"\n\n"
            "Analyze whether the user wants:\n"
            "  - marketing website\n"
            "  - dashboard\n"
            "  - ecommerce\n"
            "  - productivity app\n"
            "  - game\n"
            "  - social platform\n\n"
            "Return JSON: {{\"archetype\": \"<one>\", \"confidence\": 0-1, \"why\": \"<one sentence>\"}}."
        ),
    ),
    DesignReferencePrompt(
        id="06-motion-personality",
        title="Extract motion personality",
        template=(
            "USER PROMPT:\n\"\"\"\n{user_prompt}\n\"\"\"\n\n"
            "REFERENCE: {reference}\n\n"
            "Extract animation personality:\n"
            "  - smooth\n  - premium\n  - playful\n  - sharp\n"
            "  - cinematic\n  - subtle\n\n"
            "Return JSON: {{\"motion\": \"<one>\", \"duration_ms\": <int>, "
            "\"easing\": \"<cubic-bezier or keyword>\"}}."
        ),
    ),
    DesignReferencePrompt(
        id="07-responsive-rules",
        title="Generate responsive layout rules",
        template=(
            "USER PROMPT:\n\"\"\"\n{user_prompt}\n\"\"\"\n\n"
            "Generate responsive layout rules for 375px / 768px / 1280px. "
            "For each breakpoint, return JSON with:\n"
            "  container_width, columns, gap, font_scale, key_layout_change"
        ),
    ),
    DesignReferencePrompt(
        id="08-niche-copy",
        title="Generate realistic, niche-appropriate content",
        template=(
            "USER PROMPT:\n\"\"\"\n{user_prompt}\n\"\"\"\n\n"
            "Generate realistic content matching the niche INSTEAD of generic "
            "SaaS copy. Avoid 'Welcome to our amazing platform' or 'lorem ipsum'. "
            "Return JSON with: tagline, hero_headline, hero_subhead, primary_cta, "
            "secondary_cta, and 3 feature {{title, description}} pairs that "
            "feel native to the niche."
        ),
    ),
    DesignReferencePrompt(
        id="09-page-structure",
        title="Determine ideal page structure",
        template=(
            "USER PROMPT:\n\"\"\"\n{user_prompt}\n\"\"\"\n\n"
            "Determine the ideal page structure for the detected business type. "
            "Return JSON: list of {{name, route, sections: []}}. Sections must "
            "be drawn from the controlled vocabulary in PageSpec docs."
        ),
    ),
    DesignReferencePrompt(
        id="10-visual-hierarchy",
        title="Generate cohesive visual hierarchy",
        template=(
            "USER PROMPT:\n\"\"\"\n{user_prompt}\n\"\"\"\n\n"
            "REFERENCE: {reference}\n\n"
            "Generate a cohesive visual hierarchy system using:\n"
            "  - spacing\n  - typography\n  - contrast\n"
            "  - card elevation\n  - interaction feedback\n\n"
            "Return JSON with one object per dimension above containing "
            "{{rule, examples: []}}."
        ),
    ),
)


def all_prompts() -> tuple[DesignReferencePrompt, ...]:
    return DESIGN_REFERENCE_PROMPTS


def prompt_by_id(prompt_id: str) -> DesignReferencePrompt | None:
    for p in DESIGN_REFERENCE_PROMPTS:
        if p.id == prompt_id:
            return p
    return None


def render_all(user_prompt: str, reference: str | None = None) -> list[dict[str, str]]:
    """Render every prompt — useful when the Design Director wants the full battery."""
    return [
        {"id": p.id, "title": p.title, "prompt": p.render(user_prompt=user_prompt, reference=reference)}
        for p in DESIGN_REFERENCE_PROMPTS
    ]


# ---------------------------------------------------------------------------
# Brand/aesthetic detection from raw user prompts
# ---------------------------------------------------------------------------

# Recognized inspiration brands. Lowercased. Order doesn't matter.
_KNOWN_BRANDS: tuple[str, ...] = (
    "apple", "spotify", "xai", "openai", "anthropic", "claude", "notion",
    "airbnb", "stripe", "linear", "vercel", "figma", "framer", "lovable",
    "bolt", "v0", "tesla", "nike", "bmw", "ferrari", "lamborghini",
    "netflix", "youtube", "instagram", "twitter", "x.com", "discord",
    "slack", "github", "gitlab", "coinbase", "binance", "kraken",
    "intercom", "mintlify", "mongodb", "supabase", "cursor", "perplexity",
    "midjourney", "minimax", "elevenlabs",
)

_AESTHETIC_KEYWORDS: tuple[str, ...] = (
    "luxury", "minimal", "minimalist", "brutalist", "futuristic", "neon",
    "cyberpunk", "glassmorphism", "glass", "editorial", "soft modern",
    "enterprise", "premium", "playful", "cinematic", "dark", "light",
)


_INSPIRATION_PATTERNS = (
    re.compile(r"\b(?:look\s+like|inspired\s+by|in\s+the\s+style\s+of|like)\s+([a-z0-9][\w\.\- ]{1,40})\b", re.I),
    re.compile(r"\b([a-z][\w\.\-]{1,30})[\-\s]?(?:inspired|style|like)\b", re.I),
)


@dataclass(frozen=True)
class InspirationSignal:
    brands: tuple[str, ...]
    aesthetics: tuple[str, ...]
    raw_phrases: tuple[str, ...]

    def is_present(self) -> bool:
        return bool(self.brands or self.aesthetics or self.raw_phrases)

    def primary_reference(self) -> str | None:
        if self.brands:
            return self.brands[0]
        if self.raw_phrases:
            return self.raw_phrases[0]
        if self.aesthetics:
            return self.aesthetics[0]
        return None


def detect_design_inspiration(prompt: str) -> InspirationSignal:
    """Pull design-reference signals out of the user's prompt.

    No LLM call — purely keyword + pattern scan. Cheap enough to run on
    every request before deciding whether to fire the LLM battery.
    """
    if not prompt or not prompt.strip():
        return InspirationSignal((), (), ())

    haystack = " " + prompt.lower() + " "

    brands = tuple(b for b in _KNOWN_BRANDS if f" {b} " in haystack or f" {b}-" in haystack or f" {b}." in haystack)
    aesthetics = tuple(a for a in _AESTHETIC_KEYWORDS if f" {a} " in haystack)

    phrases: list[str] = []
    for pat in _INSPIRATION_PATTERNS:
        for m in pat.finditer(prompt):
            phrase = m.group(1).strip(" ,.;:")
            if phrase and phrase.lower() not in brands and phrase.lower() not in phrases:
                phrases.append(phrase)

    return InspirationSignal(
        brands=brands,
        aesthetics=aesthetics,
        raw_phrases=tuple(phrases),
    )


def select_prompts_for(signal: InspirationSignal) -> tuple[DesignReferencePrompt, ...]:
    """Choose the subset of the 10 prompts most relevant to the signal.

    Empty signal -> the broadly-useful subset (archetype, page structure,
    niche copy, motion). Any signal present -> the full battery.
    """
    if signal.is_present():
        return DESIGN_REFERENCE_PROMPTS
    fallback_ids = {"05-product-archetype", "06-motion-personality", "08-niche-copy", "09-page-structure"}
    return tuple(p for p in DESIGN_REFERENCE_PROMPTS if p.id in fallback_ids)
