"""Design mode registry — premium token sets the AI builder uses to make every
generated app feel like a real funded-startup product, not a wireframe.

Each mode is a COMPLETE bundle: palette, gradients, shadow style, font stack,
radius scale, motion intensity. The Brief stage picks a mode (often defaulted
from app_type), and these tokens get baked into styles.css as CSS variables
that the generated App.tsx can use via Tailwind utility classes.

Modes are intentionally distinct so consecutive generations FEEL different.
"""

from __future__ import annotations

from typing import Literal

DesignMode = Literal[
    "premium_modern",
    "neon_dark",
    "warm_editorial",
    "zinc_emerald",
    "electric_blue_dark",
    "vibrant_creative",
    "luxury_dark",
    "soft_pastel",
    "warm_luxury_red",
    "lovable_bright",
]


DESIGN_MODES: dict[str, dict] = {
    # ----------------------------------------------------------------
    "premium_modern": {
        "label": "Premium Modern (Linear/Vercel-style)",
        "feel": "Restrained, confident, slightly cool. Neutral background, single saturated accent.",
        "palette": {
            "background":           "240 6% 6%",    # near-black, slight blue cast
            "foreground":           "0 0% 96%",
            "muted":                "240 4% 13%",
            "muted_foreground":     "240 5% 65%",
            "card":                 "240 6% 9%",
            "border":               "240 4% 18%",
            "primary":              "243 75% 65%",  # indigo-violet
            "primary_foreground":   "0 0% 100%",
            "accent":               "189 94% 55%",  # cyan
            "accent_foreground":    "240 6% 6%",
        },
        "fonts": {
            "display": "Inter, system-ui, sans-serif",
            "body":    "Inter, system-ui, sans-serif",
            "mono":    "JetBrains Mono, ui-monospace, monospace",
        },
        "radius": "0.75rem",
        "shadow_style": "soft-layered",
        "animation_style": "smooth",
        "gradient_primary": "linear-gradient(135deg, hsl(243 75% 65%), hsl(189 94% 55%))",
    },

    # ----------------------------------------------------------------
    "neon_dark": {
        "label": "Neon Dark (gaming / arcade / cyber)",
        "feel": "Deep dark bg, electric neon accent, glowing interactive elements.",
        "palette": {
            "background":           "240 10% 4%",
            "foreground":           "0 0% 98%",
            "muted":                "240 8% 10%",
            "muted_foreground":     "240 5% 70%",
            "card":                 "240 10% 7%",
            "border":               "240 8% 16%",
            "primary":              "162 100% 50%",  # neon green
            "primary_foreground":   "240 10% 4%",
            "accent":               "330 90% 60%",   # neon pink
            "accent_foreground":    "240 10% 4%",
        },
        "fonts": {
            "display": "'Space Grotesk', Inter, system-ui, sans-serif",
            "body":    "Inter, system-ui, sans-serif",
            "mono":    "'JetBrains Mono', ui-monospace, monospace",
        },
        "radius": "0.5rem",
        "shadow_style": "neon-glow",
        "animation_style": "snappy",
        "gradient_primary": "linear-gradient(135deg, hsl(162 100% 50%), hsl(189 100% 55%))",
    },

    # ----------------------------------------------------------------
    "warm_editorial": {
        "label": "Warm Editorial (portfolio / restaurant / luxury hospitality)",
        "feel": "Cream background, ink-black text, serif display, hand-crafted feel.",
        "palette": {
            "background":           "40 28% 96%",   # cream
            "foreground":           "30 10% 12%",   # warm near-black
            "muted":                "40 18% 92%",
            "muted_foreground":     "30 8% 38%",
            "card":                 "40 30% 98%",
            "border":               "40 18% 86%",
            "primary":              "20 70% 35%",   # rich terracotta
            "primary_foreground":   "40 28% 96%",
            "accent":               "35 75% 55%",   # warm amber
            "accent_foreground":    "30 10% 12%",
        },
        "fonts": {
            "display": "'Playfair Display', Georgia, serif",
            "body":    "Inter, system-ui, sans-serif",
            "mono":    "'Courier Prime', ui-monospace, monospace",
        },
        "radius": "0.25rem",
        "shadow_style": "subtle-paper",
        "animation_style": "graceful",
        "gradient_primary": "linear-gradient(135deg, hsl(20 70% 35%), hsl(35 75% 55%))",
    },

    # ----------------------------------------------------------------
    "zinc_emerald": {
        "label": "Zinc + Emerald (finance / fintech / analytics)",
        "feel": "Cool zinc shell, emerald for positive numbers, sober and trustworthy.",
        "palette": {
            "background":           "240 6% 10%",
            "foreground":           "0 0% 98%",
            "muted":                "240 5% 16%",
            "muted_foreground":     "240 5% 65%",
            "card":                 "240 6% 14%",
            "border":               "240 5% 22%",
            "primary":              "158 64% 42%",   # emerald
            "primary_foreground":   "0 0% 98%",
            "accent":               "200 95% 55%",   # sky
            "accent_foreground":    "240 6% 10%",
        },
        "fonts": {
            "display": "Inter, system-ui, sans-serif",
            "body":    "Inter, system-ui, sans-serif",
            "mono":    "'JetBrains Mono', ui-monospace, monospace",
        },
        "radius": "0.5rem",
        "shadow_style": "soft-layered",
        "animation_style": "smooth",
        "gradient_primary": "linear-gradient(135deg, hsl(158 64% 42%), hsl(200 95% 55%))",
    },

    # ----------------------------------------------------------------
    "electric_blue_dark": {
        "label": "Electric Blue Dark (AI / dev tools)",
        "feel": "Inky dark base, electric blue accents, terminal-y but refined.",
        "palette": {
            "background":           "222 47% 7%",
            "foreground":           "210 40% 98%",
            "muted":                "222 30% 15%",
            "muted_foreground":     "215 20% 65%",
            "card":                 "222 40% 10%",
            "border":               "222 25% 22%",
            "primary":              "212 100% 60%",  # electric blue
            "primary_foreground":   "222 47% 7%",
            "accent":               "262 83% 68%",   # violet
            "accent_foreground":    "210 40% 98%",
        },
        "fonts": {
            "display": "Inter, system-ui, sans-serif",
            "body":    "Inter, system-ui, sans-serif",
            "mono":    "'JetBrains Mono', ui-monospace, monospace",
        },
        "radius": "0.75rem",
        "shadow_style": "neon-glow",
        "animation_style": "smooth",
        "gradient_primary": "linear-gradient(135deg, hsl(212 100% 60%), hsl(262 83% 68%))",
    },

    # ----------------------------------------------------------------
    "vibrant_creative": {
        "label": "Vibrant Creative (design / creator tools / playful SaaS)",
        "feel": "Bold purple+orange, soft cards, playful tilts and gradients.",
        "palette": {
            "background":           "270 25% 98%",
            "foreground":           "260 30% 12%",
            "muted":                "270 20% 94%",
            "muted_foreground":     "260 15% 38%",
            "card":                 "0 0% 100%",
            "border":               "270 20% 88%",
            "primary":              "270 80% 55%",   # vivid purple
            "primary_foreground":   "0 0% 100%",
            "accent":               "20 90% 58%",    # orange
            "accent_foreground":    "0 0% 100%",
        },
        "fonts": {
            "display": "Inter, system-ui, sans-serif",
            "body":    "Inter, system-ui, sans-serif",
            "mono":    "'JetBrains Mono', ui-monospace, monospace",
        },
        "radius": "1rem",
        "shadow_style": "soft-layered",
        "animation_style": "playful",
        "gradient_primary": "linear-gradient(135deg, hsl(270 80% 55%), hsl(20 90% 58%))",
    },

    # ----------------------------------------------------------------
    "luxury_dark": {
        "label": "Luxury Dark (luxury brands / fashion / hospitality)",
        "feel": "Deep black, gold accent, serif headlines, generous spacing.",
        "palette": {
            "background":           "0 0% 6%",
            "foreground":           "40 20% 95%",
            "muted":                "0 0% 12%",
            "muted_foreground":     "40 10% 65%",
            "card":                 "0 0% 9%",
            "border":               "0 0% 18%",
            "primary":              "43 65% 58%",    # warm gold
            "primary_foreground":   "0 0% 6%",
            "accent":               "30 60% 45%",    # bronze
            "accent_foreground":    "40 20% 95%",
        },
        "fonts": {
            "display": "'Playfair Display', Georgia, serif",
            "body":    "Inter, system-ui, sans-serif",
            "mono":    "'Courier Prime', ui-monospace, monospace",
        },
        "radius": "0rem",
        "shadow_style": "subtle-paper",
        "animation_style": "graceful",
        "gradient_primary": "linear-gradient(135deg, hsl(43 65% 58%), hsl(30 60% 45%))",
    },

    # ----------------------------------------------------------------
    "lovable_bright": {
        "label": "Lovable Bright (modern SaaS / healthcare / consumer landing)",
        "feel": "Soft white background, indigo primary, generous shadows, gradient accent, calm and approachable.",
        "palette": {
            "background":           "0 0% 100%",     # pure white
            "foreground":           "240 12% 12%",   # near-black text
            "muted":                "240 20% 96%",
            "muted_foreground":     "240 8% 42%",
            "card":                 "0 0% 100%",
            "border":               "240 15% 88%",
            "primary":              "243 75% 58%",   # indigo
            "primary_foreground":   "0 0% 100%",
            "accent":               "262 83% 65%",   # violet
            "accent_foreground":    "0 0% 100%",
        },
        "fonts": {
            "display": "Inter, system-ui, sans-serif",
            "body":    "Inter, system-ui, sans-serif",
            "mono":    "JetBrains Mono, ui-monospace, monospace",
        },
        "radius": "1rem",
        "shadow_style": "soft-layered",
        "animation_style": "smooth",
        "gradient_primary": "linear-gradient(135deg, hsl(243 75% 58%), hsl(262 83% 65%))",
    },

    # ----------------------------------------------------------------
    "warm_luxury_red": {
        "label": "Warm Luxury Red (Chinese fine-dining / Asian luxury)",
        "feel": "Deep red and antique gold over dark wood. Lantern-lit ambience, serif display, intimate and appetizing.",
        "palette": {
            "background":           "0 30% 8%",     # dark wood / lacquer
            "foreground":           "40 35% 92%",   # warm ivory
            "muted":                "0 18% 14%",
            "muted_foreground":     "40 18% 70%",
            "card":                 "0 22% 11%",
            "border":               "20 20% 22%",
            "primary":              "0 65% 42%",    # deep imperial red
            "primary_foreground":   "40 35% 95%",
            "accent":               "40 70% 55%",   # antique gold
            "accent_foreground":    "0 30% 8%",
        },
        "fonts": {
            "display": "'Playfair Display', Georgia, serif",
            "body":    "Inter, system-ui, sans-serif",
            "mono":    "'Courier Prime', ui-monospace, monospace",
        },
        "radius": "0.25rem",
        "shadow_style": "subtle-paper",
        "animation_style": "graceful",
        "gradient_primary": "linear-gradient(135deg, hsl(0 65% 42%), hsl(40 70% 55%))",
    },

    # ----------------------------------------------------------------
    "soft_pastel": {
        "label": "Soft Pastel (wellness / consumer / kids)",
        "feel": "Soft cream/pastel base, gentle accents, rounded, friendly.",
        "palette": {
            "background":           "30 50% 97%",
            "foreground":           "240 15% 18%",
            "muted":                "30 30% 93%",
            "muted_foreground":     "240 10% 42%",
            "card":                 "0 0% 100%",
            "border":               "30 30% 87%",
            "primary":              "340 75% 60%",   # rose
            "primary_foreground":   "0 0% 100%",
            "accent":               "170 60% 55%",   # mint
            "accent_foreground":    "240 15% 18%",
        },
        "fonts": {
            "display": "Inter, system-ui, sans-serif",
            "body":    "Inter, system-ui, sans-serif",
            "mono":    "'JetBrains Mono', ui-monospace, monospace",
        },
        "radius": "1.25rem",
        "shadow_style": "soft-layered",
        "animation_style": "playful",
        "gradient_primary": "linear-gradient(135deg, hsl(340 75% 60%), hsl(170 60% 55%))",
    },
}


# Default mode per app_type. The Brief agent can override but this is the floor.
# Landing now defaults to lovable_bright (white + indigo + violet gradient) so
# generic prompts that fall through to the single-file scaffold land on a
# polished bright site rather than the previous near-black premium_modern.
APP_TYPE_DEFAULT_MODE: dict[str, DesignMode] = {
    "landing":        "lovable_bright",
    "dashboard":      "zinc_emerald",
    "game":           "neon_dark",
    "portfolio":      "warm_editorial",
    "ecommerce":      "lovable_bright",
    "admin":          "zinc_emerald",
    "chat":           "premium_modern",
    "productivity":   "lovable_bright",
    "tool":           "electric_blue_dark",
    "mobile-app":     "vibrant_creative",
    "editor":         "electric_blue_dark",
    "social":         "lovable_bright",
}


def get_design_mode(name: str) -> dict:
    return DESIGN_MODES.get(name, DESIGN_MODES["premium_modern"])


def design_mode_for_app_type(app_type: str) -> DesignMode:
    return APP_TYPE_DEFAULT_MODE.get(app_type, "premium_modern")


def design_modes_catalog_text() -> str:
    """For the Design Director's prompt — shows all available modes."""
    lines = ["AVAILABLE DESIGN MODES (pick exactly one — commit fully):"]
    for key, info in DESIGN_MODES.items():
        lines.append(f"  - {key}: {info['feel']}")
    return "\n".join(lines)
