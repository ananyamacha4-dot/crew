"""Style archetype taxonomy.

The Design Director agent picks ONE archetype from this catalog and commits.
Each archetype is a coherent bundle of public design patterns (palette,
typography, spacing, motion, signature moves) — abstracted, not copied,
from well-known products. The Engineer agent uses these as anchors so the
LLM doesn't invent design from scratch every time.

NO copyrighted assets are reproduced. We extract STYLE GENOMES (color
ranges, spacing taxonomies, layout patterns) — not specific layouts.
"""

from __future__ import annotations

ARCHETYPES: dict[str, dict] = {
    "linear-minimal": {
        "label": "Linear-style minimal",
        "best_for": ["dev tools", "B2B SaaS", "internal tools"],
        "palette": {
            "primary": "#5e6ad2",
            "neutral_base": "#08090a",
            "background": "#fafafa",
            "accent": "#94a3b8",
        },
        "fonts": {
            "display": "Inter, system-ui, sans-serif",
            "body": "Inter, system-ui, sans-serif",
            "mono": "JetBrains Mono, ui-monospace, monospace",
        },
        "radius": "subtle",
        "density": "spacious",
        "motion": "subtle",
        "signature_moves": [
            "Thin 1px borders over fills",
            "Off-white background (#fafafa), never pure white",
            "Single accent color, no gradients",
            "Tight letter-spacing on large headings (tracking-tight)",
            "Generous vertical rhythm, asymmetric two-column heroes",
        ],
    },
    "stripe-fintech": {
        "label": "Stripe-style fintech",
        "best_for": ["fintech", "payments", "developer SaaS"],
        "palette": {
            "primary": "#635bff",
            "neutral_base": "#0a2540",
            "background": "#ffffff",
            "accent": "#00d4ff",
        },
        "fonts": {
            "display": "Inter, sans-serif",
            "body": "Inter, sans-serif",
            "mono": "Source Code Pro, ui-monospace, monospace",
        },
        "radius": "soft",
        "density": "comfortable",
        "motion": "subtle",
        "signature_moves": [
            "Holographic conic gradient on hero background",
            "Code samples shown prominently in dark monospace cards",
            "Deep navy primary with bright cyan accent",
            "Two-column layouts: prose left, code/screenshot right",
            "Soft, low-spread drop shadows on cards (shadow-sm)",
        ],
    },
    "notion-warm": {
        "label": "Notion-style warm",
        "best_for": ["productivity", "knowledge tools", "collaborative apps"],
        "palette": {
            "primary": "#2f3437",
            "neutral_base": "#37352f",
            "background": "#fffbf5",
            "accent": "#e16259",
        },
        "fonts": {
            "display": "Inter, system-ui, sans-serif",
            "body": "Inter, system-ui, sans-serif",
            "mono": "iA Writer Mono, ui-monospace, monospace",
        },
        "radius": "subtle",
        "density": "comfortable",
        "motion": "subtle",
        "signature_moves": [
            "Warm off-white background (#fffbf5), never blue-white",
            "Inline emoji accents in headings and feature titles",
            "Rounded corners on everything (rounded-md baseline)",
            "Pill-shaped tags and category tokens",
            "Black ink on warm cream — high contrast, low formality",
        ],
    },
    "vercel-brutalist": {
        "label": "Vercel-style geometric mono",
        "best_for": ["dev infrastructure", "platforms", "technical SaaS"],
        "palette": {
            "primary": "#000000",
            "neutral_base": "#000000",
            "background": "#ffffff",
            "accent": "#0070f3",
        },
        "fonts": {
            "display": "Geist, Inter, system-ui, sans-serif",
            "body": "Geist, Inter, system-ui, sans-serif",
            "mono": "Geist Mono, ui-monospace, monospace",
        },
        "radius": "subtle",
        "density": "comfortable",
        "motion": "subtle",
        "signature_moves": [
            "Pure black on white, no soft greys",
            "Geometric monospaced numerals in headlines and stats",
            "Triangle / diamond / hex motifs as visual anchors",
            "Tight grid alignment, no decorative curves",
            "Black-bg dark cards in product/feature sections",
        ],
    },
    "apple-premium": {
        "label": "Apple-style premium",
        "best_for": ["consumer hardware", "premium services", "luxury tech"],
        "palette": {
            "primary": "#1d1d1f",
            "neutral_base": "#1d1d1f",
            "background": "#ffffff",
            "accent": "#0071e3",
        },
        "fonts": {
            "display": "Inter, -apple-system, system-ui, sans-serif",
            "body": "Inter, -apple-system, system-ui, sans-serif",
            "mono": "SF Mono, ui-monospace, monospace",
        },
        "radius": "pill",
        "density": "spacious",
        "motion": "expressive",
        "signature_moves": [
            "Massive centered product hero (large image, full viewport)",
            "Single-column scroll narrative — one idea per viewport",
            "Pill-shaped CTAs in vivid blue",
            "All-caps small eyebrow text above oversized display headlines",
            "Generous vertical spacing — never crowded, no sidebars",
        ],
    },
    "playful-saas": {
        "label": "Playful SaaS",
        "best_for": ["consumer SaaS", "creator tools", "design tools"],
        "palette": {
            "primary": "#7c3aed",
            "neutral_base": "#1e1b4b",
            "background": "#fdfaff",
            "accent": "#f97316",
        },
        "fonts": {
            "display": "Inter, system-ui, sans-serif",
            "body": "Inter, system-ui, sans-serif",
            "mono": "JetBrains Mono, ui-monospace, monospace",
        },
        "radius": "soft",
        "density": "comfortable",
        "motion": "expressive",
        "signature_moves": [
            "Bright purple primary with orange accent for CTAs",
            "Slightly tilted (rotate-1 / -rotate-1) cards and screenshots",
            "Hand-drawn underline SVG accents under key words",
            "Sparkles/confetti micro-interactions on success states",
            "Illustrative iconography (filled, colorful) over outline icons",
        ],
    },
    "luxury-editorial": {
        "label": "Luxury editorial",
        "best_for": ["fashion", "interiors", "premium ecommerce", "wedding"],
        "palette": {
            "primary": "#1a1a1a",
            "neutral_base": "#1a1a1a",
            "background": "#f5f0e8",
            "accent": "#a16207",
        },
        "fonts": {
            "display": "Playfair Display, Georgia, serif",
            "body": "Inter, system-ui, sans-serif",
            "mono": "Courier Prime, ui-monospace, monospace",
        },
        "radius": "sharp",
        "density": "spacious",
        "motion": "subtle",
        "signature_moves": [
            "Serif display headlines paired with sans body",
            "Magazine-style asymmetric grid (12-col with intentional gaps)",
            "Earthy cream background (#f5f0e8), never bright white",
            "Sharp 0-radius corners on all components",
            "Editorial pull-quotes set in serif, with rule above and below",
        ],
    },
    "dashboard-utility": {
        "label": "Utility dashboard",
        "best_for": ["analytics", "admin panels", "data-heavy SaaS"],
        "palette": {
            "primary": "#0ea5e9",
            "neutral_base": "#020617",
            "background": "#f8fafc",
            "accent": "#10b981",
        },
        "fonts": {
            "display": "Inter, system-ui, sans-serif",
            "body": "Inter, system-ui, sans-serif",
            "mono": "JetBrains Mono, ui-monospace, monospace",
        },
        "radius": "subtle",
        "density": "tight",
        "motion": "none",
        "signature_moves": [
            "Sidebar + topbar app shell, persistent across views",
            "Information density: text-sm baseline, compact spacing",
            "Stat cards with sparkline + delta % indicator",
            "Tabular data with sticky headers and row hover",
            "Semantic colors (sky primary, emerald success, amber warn, rose danger)",
        ],
    },
}


def archetype_names() -> list[str]:
    return list(ARCHETYPES.keys())


def get_archetype(name: str) -> dict:
    if name not in ARCHETYPES:
        return ARCHETYPES["linear-minimal"]  # safe fallback
    return ARCHETYPES[name]


def archetypes_catalog_text() -> str:
    """Compact text block fed to the Design Director for grounding."""
    lines: list[str] = []
    for key, a in ARCHETYPES.items():
        lines.append(
            f"- {key} ({a['label']})\n"
            f"    best_for: {', '.join(a['best_for'])}\n"
            f"    radius: {a['radius']}, density: {a['density']}, motion: {a['motion']}\n"
            f"    signature: {'; '.join(a['signature_moves'][:3])}"
        )
    return "\n".join(lines)
