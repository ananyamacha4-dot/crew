import json
import os
import random
from pathlib import Path

import litellm

from .brand_library import brand_palette_summary, pick_brand


# Get backend root directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load palette JSON
palette_path = BASE_DIR / "data" / "themePalettes.json"

with open(palette_path, "r", encoding="utf-8") as f:
    PALETTES = json.load(f)


def detect_theme(prompt: str):
    """
    Detect project/app category from user prompt
    """

    prompt = prompt.lower()

    # Coffee / Cafe
    if (
        "coffee" in prompt
        or "cafe" in prompt
        or "restaurant" in prompt
        or "bakery" in prompt
    ):
        return "coffee shop"

    # Fintech
    if (
        "finance" in prompt
        or "bank" in prompt
        or "crypto" in prompt
        or "payment" in prompt
        or "wallet" in prompt
    ):
        return "fintech"

    # Gaming
    if (
        "game" in prompt
        or "snake" in prompt
        or "arcade" in prompt
        or "gaming" in prompt
    ):
        return "gaming"

    # Medical
    if (
        "hospital" in prompt
        or "doctor" in prompt
        or "medical" in prompt
        or "health" in prompt
    ):
        return "medical"

    # Portfolio
    if (
        "portfolio" in prompt
        or "personal website" in prompt
        or "resume" in prompt
    ):
        return "portfolio"

    # Ecommerce
    if (
        "store" in prompt
        or "shop" in prompt
        or "ecommerce" in prompt
        or "shopping" in prompt
    ):
        return "ecommerce"

    return None


def get_random_palette(category: str):
    """
    Randomly choose palette from category
    """

    if category not in PALETTES:
        return None

    palettes = PALETTES[category]

    if not palettes:
        return None

    return random.choice(palettes)


def build_palette_prompt(palette: dict):
    """
    Convert palette into AI-readable prompt text
    """

    colors = palette["colors"]

    return f"""
COLOR PALETTE INSTRUCTIONS:

Theme Name:
{palette['name']}

Use these colors consistently across the UI:

Primary Color:
{colors['primary']}

Secondary Color:
{colors['secondary']}

Accent Color:
{colors['accent']}

Background Color:
{colors['background']}

Text Color:
{colors['text']}

IMPORTANT DESIGN RULES:
- Maintain strong visual consistency
- Use the accent color for buttons/interactions
- Use primary/secondary colors for layout hierarchy
- Ensure good contrast and readability
- Create a premium modern UI aesthetic
"""


def enhance_prompt(user_prompt: str):
    """
    Enhance user prompt with intelligent design palette
    """

    category = detect_theme(user_prompt)

    # No category detected
    if not category:
        return user_prompt

    palette = get_random_palette(category)

    # No palette found
    if not palette:
        return user_prompt

    palette_prompt = build_palette_prompt(palette)

    enhanced_prompt = f"""
USER REQUEST:
{user_prompt}

{palette_prompt}

IMPORTANT:
Generate a visually polished modern application.
Prioritize real functionality over landing-page marketing sections.
"""

    return enhanced_prompt


# ---------------------------------------------------------------------------
# LLM-driven prompt optimizer
# ---------------------------------------------------------------------------

_OPTIMIZER_SYSTEM_PROMPT = (
    "You are a senior product designer + technical PM. Your job: take a short "
    "user prompt for an app or website and expand it into a richly specified "
    "build prompt that another AI can implement. You add specifics — you do "
    "NOT change the kind of product the user asked for. If they asked for a "
    "snake game, the output is a snake game; if they asked for a coffee shop "
    "site, the output is a coffee shop site. No filler words like 'modern' "
    "or 'sleek' — every adjective must be backed by a concrete choice."
)


_OPTIMIZER_USER_TEMPLATE = """ORIGINAL PROMPT:
\"\"\"{prompt}\"\"\"

DETECTED CATEGORY: {category}
{brand_block}{palette_block}
Rewrite the prompt as ONE rich paragraph that:
  - preserves the exact product the user asked for
  - adopts the brand inspiration above as the visual starting point (palette, typography, design DNA)
  - adds concrete UI/UX requirements (layout, components, states)
  - adds responsiveness requirements (mobile 375px, tablet 768px, desktop 1280px)
  - adds animation + micro-interaction details (use framer-motion-style language)
  - adds typography + color guidance using the brand palette hex values explicitly
  - adds tech-stack: React + Tailwind, single-page, accessible, keyboard-friendly
  - calls out FUNCTIONALITY before marketing copy (especially for tools / games / apps)
  - NEVER ships a black-and-white-only result; every screen uses the brand palette

Output ONLY the rewritten prompt. No preamble. No headings. No quotes around it."""


def _optimizer_model() -> str:
    return os.getenv(
        "OPTIMIZER_MODEL",
        os.getenv("WORKER_MODEL", "groq/llama-3.3-70b-versatile"),
    )


def _has_any_llm_key() -> bool:
    return bool(
        os.getenv("GROQ_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )


def _strip_wrapping_quotes(text: str) -> str:
    s = text.strip()
    while len(s) >= 2 and s[0] in "\"'" and s[-1] == s[0]:
        s = s[1:-1].strip()
    return s


def optimize_prompt(user_prompt: str) -> str:
    """Expand a short user prompt into a detailed, theme-aware build prompt.

    Tries the LLM first (with palette + category injected as design hints).
    Falls back to the deterministic `enhance_prompt` if no provider key is
    configured or the LLM call fails — the endpoint should never hard-error.
    """
    user_prompt = (user_prompt or "").strip()
    if not user_prompt:
        raise ValueError("prompt is empty")

    category = detect_theme(user_prompt)
    palette = get_random_palette(category) if category else None
    palette_block = ""
    if palette:
        palette_block = (
            "\nDESIGN HINTS (use these as the starting point — refine, don't ignore):\n"
            + build_palette_prompt(palette).strip()
            + "\n"
        )

    # Brand inspiration from VoltAgent's awesome-design-md catalog.
    # `pick_brand` is robust to LLM failures and a missing catalog — it always
    # returns a Brand, so we can build the block unconditionally.
    brand = pick_brand(user_prompt)
    brand_block = "\nBRAND INSPIRATION:\n" + brand_palette_summary(brand) + "\n"

    if not _has_any_llm_key():
        return _fallback_optimize(user_prompt, category, palette, brand)

    user_message = _OPTIMIZER_USER_TEMPLATE.format(
        prompt=user_prompt,
        category=category or "generic-app",
        brand_block=brand_block,
        palette_block=palette_block,
    )

    try:
        response = litellm.completion(
            model=_optimizer_model(),
            messages=[
                {"role": "system", "content": _OPTIMIZER_SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
            temperature=0.4,
            max_tokens=600,
        )
        text = (response.choices[0].message.content or "").strip()
        text = _strip_wrapping_quotes(text)
        if len(text) < len(user_prompt) + 20:
            # Suspiciously short — LLM didn't actually expand. Fall back.
            return _fallback_optimize(user_prompt, category, palette, brand)
        return text
    except Exception:
        return _fallback_optimize(user_prompt, category, palette, brand)


def _fallback_optimize(user_prompt: str, category: str | None, palette: dict | None, brand=None) -> str:
    """Deterministic fallback when the LLM is unavailable or errors."""
    parts: list[str] = [user_prompt.rstrip(".") + "."]

    if category:
        parts.append(f"Category: {category}.")
    parts.append(
        "Build it as a single-page React + Tailwind app. "
        "Prioritize functionality over marketing copy."
    )
    if brand and brand.colors:
        swatches = ", ".join(f"{k} {v}" for k, v in list(brand.colors.items())[:6])
        parts.append(
            f"Use the {brand.name} brand DNA — palette: {swatches}; "
            f"display font: {brand.display_font()}; body font: {brand.body_font()}."
        )
    if palette:
        c = palette["colors"]
        parts.append(
            f"Secondary palette '{palette['name']}': primary {c['primary']}, "
            f"secondary {c['secondary']}, accent {c['accent']}, "
            f"background {c['background']}, text {c['text']}."
        )
    parts.append(
        "Fully responsive (375px / 768px / 1280px), accessible color contrast, "
        "keyboard navigation, smooth state transitions, subtle framer-motion "
        "entries on first paint, and hover micro-interactions on every "
        "interactive element. The final UI MUST use the brand palette above — "
        "not a black-and-white-only design."
    )
    return " ".join(parts)