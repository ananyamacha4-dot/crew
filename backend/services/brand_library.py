"""Brand library — parses VoltAgent's awesome-design-md catalog and picks
a brand-inspired design system for each generation request.

The catalog lives at <repo-root>/awesome-design-md/design-md/<brand>/DESIGN.md.
Each file has YAML frontmatter between two `---` markers, containing:
  description  — one-paragraph design DNA
  colors       — dict of token -> hex
  typography   — dict of style -> {fontFamily, fontSize, fontWeight, ...}
  rounded      — dict (radius scale)
  spacing      — dict (spacing scale)
  components   — dict of component -> token references

Public surface:
    list_brands() -> list[BrandSummary]
    get_brand(key) -> Brand | None
    pick_brand(prompt) -> Brand
        Uses Groq via LiteLLM to pick a brand that fits the prompt.
        Falls back to a keyword-driven default so the call never errors.
"""

from __future__ import annotations

import os
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import litellm
import yaml


# ---------------------------------------------------------------------------
# Catalog loading
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CATALOG_DIR = _REPO_ROOT / "awesome-design-md" / "design-md"


@dataclass
class Brand:
    key: str                           # slug, e.g. "stripe", "linear.app"
    name: str                          # display name from frontmatter, fallback to key
    description: str                   # one-paragraph design DNA
    colors: dict[str, str]             # token -> hex (or other CSS color)
    typography: dict[str, dict[str, Any]] = field(default_factory=dict)
    rounded: dict[str, str] = field(default_factory=dict)
    spacing: dict[str, str] = field(default_factory=dict)
    components: dict[str, dict[str, Any]] = field(default_factory=dict)

    # ---- convenience accessors ----

    def primary_hex(self) -> str:
        return _first_color(self.colors, ("primary", "brand", "accent", "action"))

    def accent_hex(self) -> str:
        return _first_color(self.colors, ("accent", "secondary", "highlight", "primary-soft", "primary-deep"))

    def background_hex(self) -> str:
        return _first_color(self.colors, ("canvas", "background", "bg", "surface", "ink-bg"))

    def foreground_hex(self) -> str:
        return _first_color(self.colors, ("ink", "text", "foreground", "on-canvas", "neutral-900"))

    def display_font(self) -> str:
        return _first_typography(self.typography, ("display-xxl", "display-xl", "display-lg", "heading-lg", "heading-md"))

    def body_font(self) -> str:
        return _first_typography(self.typography, ("body-lg", "body-md", "body", "body-sm"))


@dataclass(frozen=True)
class BrandSummary:
    key: str
    description: str


_brand_cache: dict[str, Brand] | None = None


def _load_all() -> dict[str, Brand]:
    global _brand_cache
    if _brand_cache is not None:
        return _brand_cache
    out: dict[str, Brand] = {}
    if not _CATALOG_DIR.is_dir():
        _brand_cache = out
        return out
    for child in sorted(_CATALOG_DIR.iterdir()):
        if not child.is_dir():
            continue
        design_md = child / "DESIGN.md"
        if not design_md.is_file():
            continue
        try:
            brand = _parse_design_md(child.name, design_md)
            if brand and brand.colors:
                out[brand.key] = brand
        except Exception:
            continue
    _brand_cache = out
    return out


_FRONTMATTER_PAT = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_design_md(key: str, path: Path) -> Brand | None:
    raw = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_PAT.match(raw)
    if not m:
        return None
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    colors = data.get("colors") or {}
    if not isinstance(colors, dict):
        return None
    return Brand(
        key=key,
        name=str(data.get("name") or key),
        description=str(data.get("description") or "").strip(),
        colors={str(k): str(v) for k, v in colors.items() if isinstance(v, (str, int))},
        typography=data.get("typography") if isinstance(data.get("typography"), dict) else {},
        rounded=data.get("rounded") if isinstance(data.get("rounded"), dict) else {},
        spacing=data.get("spacing") if isinstance(data.get("spacing"), dict) else {},
        components=data.get("components") if isinstance(data.get("components"), dict) else {},
    )


def list_brands() -> list[BrandSummary]:
    return [BrandSummary(key=b.key, description=_one_line(b.description)) for b in _load_all().values()]


def get_brand(key: str) -> Brand | None:
    return _load_all().get(key)


# ---------------------------------------------------------------------------
# Brand selection
# ---------------------------------------------------------------------------

# Keyword shortcuts — when the prompt mentions a category, prefer this set
# (still LLM-picked from within the set, unless LLM unavailable).
_CATEGORY_PRIORITIES: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"\b(fintech|bank|payment|crypto|wallet|trading|invest|finance)\b", re.I),
     ["stripe", "revolut", "wise", "coinbase", "binance", "kraken", "mastercard"]),
    (re.compile(r"\b(coffee|cafe|caf\xe9|bakery|restaurant)\b", re.I),
     ["starbucks", "airbnb", "notion"]),
    (re.compile(r"\b(game|snake|tetris|arcade|gaming)\b", re.I),
     ["playstation", "nvidia", "spacex", "tesla"]),
    (re.compile(r"\b(music|streaming|podcast|audio)\b", re.I),
     ["spotify", "elevenlabs", "runwayml"]),
    (re.compile(r"\b(ai|llm|chatbot|agent|model)\b", re.I),
     ["claude", "x.ai", "cohere", "mistral.ai", "together.ai", "lovable", "cursor"]),
    (re.compile(r"\b(devtool|developer|api|cli|terminal|cloud)\b", re.I),
     ["vercel", "supabase", "linear.app", "hashicorp", "stripe", "warp", "raycast"]),
    (re.compile(r"\b(portfolio|personal site|resume|cv|designer)\b", re.I),
     ["framer", "figma", "linear.app", "apple", "claude", "lovable"]),
    (re.compile(r"\b(ecommerce|shop|store|marketplace|product page|sneaker|apparel)\b", re.I),
     ["shopify", "nike", "apple", "airbnb", "uber"]),
    (re.compile(r"\b(saas|landing page|platform|product launch|b2b)\b", re.I),
     ["stripe", "linear.app", "vercel", "intercom", "notion", "posthog"]),
    (re.compile(r"\b(dashboard|admin panel|analytics|stats)\b", re.I),
     ["linear.app", "stripe", "vercel", "posthog", "supabase", "mongodb"]),
    (re.compile(r"\b(news|magazine|editorial|blog)\b", re.I),
     ["theverge", "wired", "pinterest", "miro"]),
    (re.compile(r"\b(car|auto|vehicle|ev)\b", re.I),
     ["tesla", "bmw", "bmw-m", "ferrari", "lamborghini", "bugatti", "renault"]),
]


_PICKER_SYSTEM = (
    "You are a senior brand-design director. Pick ONE brand whose visual "
    "language best fits the user's request. Respond with ONLY the brand key, "
    "lowercase, exactly as it appears in the candidate list. No commentary."
)


def _picker_model() -> str:
    return os.getenv(
        "BRAND_PICKER_MODEL",
        os.getenv("WORKER_MODEL", "groq/llama-3.3-70b-versatile"),
    )


def _has_any_llm_key() -> bool:
    return bool(
        os.getenv("GROQ_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )


def _candidates_for(prompt: str) -> list[str]:
    all_brands = list(_load_all().keys())
    if not all_brands:
        return []
    for pat, preferred in _CATEGORY_PRIORITIES:
        if pat.search(prompt):
            in_catalog = [b for b in preferred if b in _load_all()]
            if in_catalog:
                return in_catalog
    # Otherwise let the LLM pick from a broad shortlist; cap to keep prompt small
    sample = random.sample(all_brands, min(24, len(all_brands)))
    return sample


def pick_brand(prompt: str) -> Brand:
    """Pick a brand-inspired design system for `prompt`.

    Order:
      1. LLM (Groq) chooses from a category-filtered shortlist
      2. Random pick from the shortlist if LLM call fails / no key
      3. Random pick from the entire catalog if shortlist is empty
      4. Hardcoded default Brand if the catalog itself is missing
    """
    catalog = _load_all()
    if not catalog:
        return _DEFAULT_BRAND

    shortlist = _candidates_for(prompt) or list(catalog.keys())

    if _has_any_llm_key():
        try:
            menu = "\n".join(f"- {k}: {_one_line(catalog[k].description)[:160]}" for k in shortlist)
            resp = litellm.completion(
                model=_picker_model(),
                messages=[
                    {"role": "system", "content": _PICKER_SYSTEM},
                    {"role": "user", "content": (
                        f"USER PROMPT:\n\"\"\"{prompt}\"\"\"\n\n"
                        f"CANDIDATES (pick exactly one key):\n{menu}"
                    )},
                ],
                temperature=0.3,
                max_tokens=20,
            )
            raw = (resp.choices[0].message.content or "").strip().lower()
            # Tolerate quotes / backticks / "key: ..." formatting
            raw = re.sub(r"[`'\"]", "", raw)
            raw = raw.split()[0] if raw else ""
            raw = raw.rstrip(":,.")
            if raw in catalog:
                return catalog[raw]
            # Try a fuzzy contains-match for things like "stripe (fintech)"
            for k in shortlist:
                if k in raw:
                    return catalog[k]
        except Exception:
            pass

    return catalog[random.choice(shortlist)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first_color(palette: dict[str, str], keys: tuple[str, ...]) -> str:
    for k in keys:
        if k in palette:
            return palette[k]
    # Fallback: try any key containing one of the substrings
    for token, value in palette.items():
        low = token.lower()
        if any(k in low for k in keys):
            return value
    # Last resort: first value
    return next(iter(palette.values()), "#5e6ad2")


def _first_typography(typo: dict[str, dict[str, Any]], keys: tuple[str, ...]) -> str:
    for k in keys:
        spec = typo.get(k)
        if isinstance(spec, dict) and "fontFamily" in spec:
            return str(spec["fontFamily"])
    for spec in typo.values():
        if isinstance(spec, dict) and "fontFamily" in spec:
            return str(spec["fontFamily"])
    return "Inter, system-ui, -apple-system, sans-serif"


def _one_line(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


# Catalog-missing fallback so the rest of the pipeline never has to
# handle "no brands available".
_DEFAULT_BRAND = Brand(
    key="default",
    name="Default",
    description="Neutral modern design system with a violet primary and a dark canvas.",
    colors={
        "primary": "#8b5cf6",
        "accent":  "#22d3ee",
        "canvas":  "#0a0a0a",
        "ink":     "#f8fafc",
    },
    typography={
        "body-md": {"fontFamily": "Inter, system-ui, -apple-system, sans-serif", "fontSize": "15px"},
    },
    rounded={"md": "8px", "lg": "12px"},
    spacing={"md": "12px", "lg": "16px"},
    components={},
)


# ---------------------------------------------------------------------------
# Prompt-injection helpers
# ---------------------------------------------------------------------------

def brand_palette_summary(brand: Brand) -> str:
    """Compact human-readable summary for stuffing into an LLM prompt."""
    swatches = ", ".join(f"{k}: {v}" for k, v in list(brand.colors.items())[:8])
    return (
        f"Brand inspiration: {brand.name}.\n"
        f"Design DNA: {_one_line(brand.description)[:400]}\n"
        f"Palette tokens: {swatches}.\n"
        f"Display font: {brand.display_font()}.\n"
        f"Body font: {brand.body_font()}."
    )
