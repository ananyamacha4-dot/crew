"""Niche classifier — picks a category + sub-niche from a free-form user prompt.

Deterministic keyword matcher (no LLM). Sits in front of the existing template
matcher so the system can say "this is a Chinese restaurant" rather than just
"this might match a hospitality template". The output is consumed by
`template_intelligence.classify_and_plan()` which combines this signal with
the template scorer and the curated content packs.

This module is purely additive — when no niche fires, callers fall back to the
existing pipeline unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class NicheClassification:
    """Resolved niche for a prompt.

    `category` is the broad bucket ("restaurant", "ecommerce", "dashboard",
    etc.) and lines up with TemplateManifest.category. `sub_niche` is the
    specialization ("chinese", "japanese", "fashion") and may be None.
    `confidence` ranges 0.0–1.0; callers should use a threshold (0.6 by
    default) before treating the result as a strong signal.
    """

    category: str
    sub_niche: str | None
    confidence: float
    matched_terms: tuple[str, ...] = field(default_factory=tuple)

    @property
    def slug(self) -> str:
        if self.sub_niche:
            return f"{self.category}/{self.sub_niche}"
        return self.category


# ---------------------------------------------------------------------------
# Keyword tables
# ---------------------------------------------------------------------------
#
# Tables are intentionally explicit and easy to grow. Each category lists its
# trigger terms; sub-niches are nested under their parent and only fire when
# their parent category also fires.

_CATEGORY_TERMS: dict[str, tuple[str, ...]] = {
    # Restaurant is intentionally wide: cafes, bakeries, and proper
    # restaurants share the same page structure (Home/Menu/About/Gallery/
    # Contact (+ Reservations for dine-in)) and the same multi-page
    # scaffold can serve all three. Sub-niches differentiate the visual
    # palette and the content pack.
    "restaurant": (
        "restaurant", "dining", "eatery", "bistro", "diner",
        "kitchen", "chef", "cuisine", "menu", "fine dining",
        "trattoria", "ristorante", "izakaya", "brasserie",
        "cafe", "café", "coffee shop", "coffeehouse", "espresso bar",
        "roastery", "barista",
        "bakery", "patisserie", "boulangerie", "bakeshop", "pastry shop",
        "bread shop",
    ),
    "ecommerce": (
        "store", "shop", "ecommerce", "e-commerce", "storefront",
        "marketplace", "cart", "checkout", "products",
        "boutique", "online store", "online shop", "shop online",
    ),
    "dashboard": (
        "dashboard", "analytics", "metrics", "kpi", "admin panel",
        "monitoring", "stats panel",
    ),
    "portfolio": (
        "portfolio", "personal site", "personal website", "showcase",
        "freelancer site", "creative portfolio",
    ),
    # SaaS marketing — distinct from existing 'saas' templates already in
    # registry.json. The multi-page Open Lovable scaffolder handles this
    # category; non-matching SaaS prompts continue to fall through to the
    # existing single-file landing pipeline.
    "saas": (
        "saas", "saas landing", "saas marketing", "saas product",
        "b2b platform", "platform website", "product site",
        "developer tool", "developer platform", "ai saas",
    ),
    # Healthcare / medical practices (hospital, clinic, dental, wellness).
    # Routes to the open-lovable-healthcare archetype scaffolder.
    "healthcare": (
        "hospital", "clinic", "doctor", "dental", "dentist",
        "medical", "medical practice", "medical center", "medical clinic",
        "healthcare", "health care", "wellness", "wellness clinic",
        "practice", "pharmacy", "physiotherapy", "physical therapy",
        "chiropractic", "chiropractor", "telehealth", "urgent care",
    ),
}


# Sub-niche tables. Each sub-niche maps to its own list of trigger terms;
# every term implies the parent category and the sub_niche together.
_SUB_NICHES: dict[str, dict[str, tuple[str, ...]]] = {
    "restaurant": {
        "chinese": (
            "chinese", "sichuan", "szechuan", "cantonese", "hunan", "shanghai",
            "dim sum", "hot pot", "hotpot", "wok", "noodle", "noodles",
            "dumpling", "dumplings", "kung pao", "mapo", "peking",
            "lo mein", "chow mein", "wonton",
        ),
        "japanese": (
            "japanese", "sushi", "ramen", "izakaya", "tempura", "sashimi",
            "teppanyaki", "yakitori", "udon", "soba", "donburi",
        ),
        "italian": (
            "italian", "pasta", "pizzeria", "trattoria", "ristorante",
            "neapolitan", "tuscan",
        ),
        "mexican": (
            "mexican", "taqueria", "taco", "burrito", "enchilada",
            "cantina",
        ),
        "indian": (
            "indian", "curry house", "tandoor", "tandoori", "biryani",
            "masala",
        ),
        "thai": (
            "thai", "pad thai", "tom yum", "thai kitchen",
        ),
        "french": (
            "french", "bistro francais", "brasserie", "patisserie restaurant",
        ),
        "steakhouse": (
            "steakhouse", "chop house", "grill house",
        ),
        "cafe": (
            "cafe", "café", "coffee shop", "coffeehouse", "espresso bar",
            "roastery", "barista", "all day cafe", "brunch cafe",
        ),
        "bakery": (
            "bakery", "patisserie", "boulangerie", "bakeshop",
            "pastry shop", "bread shop", "sourdough bakery", "artisan bakery",
        ),
    },
    "ecommerce": {
        "fashion": (
            "clothing", "apparel", "fashion", "boutique", "wear", "outfit",
            "streetwear", "clothing store", "fashion store", "apparel store",
        ),
        "electronics": (
            "electronics", "gadgets", "devices", "tech store",
        ),
        "furniture": (
            "furniture", "home decor", "interior store",
        ),
        "beauty": (
            "beauty", "cosmetics", "skincare", "makeup",
        ),
    },
    "portfolio": {
        "designer-portfolio": (
            "designer", "designer portfolio", "design portfolio",
            "ux portfolio", "product designer", "graphic designer",
        ),
        "dev-portfolio": (
            "developer portfolio", "dev portfolio", "engineer portfolio",
            "software portfolio", "programmer portfolio",
        ),
        "photographer-portfolio": (
            "photographer portfolio", "photography portfolio",
            "photographer site",
        ),
    },
    "saas": {
        "b2b-saas": (
            "b2b saas", "b2b platform", "enterprise saas", "team saas",
        ),
        "ai-saas": (
            "ai saas", "ai platform", "ml platform", "ai tool landing",
        ),
        "developer-tool": (
            "developer tool", "developer platform", "dev tool landing",
            "api product", "cli tool landing",
        ),
    },
    "healthcare": {
        "clinic": (
            "clinic", "medical clinic", "wellness clinic", "private clinic",
        ),
        "hospital": (
            "hospital", "medical center", "medical centre",
        ),
        "dental": (
            "dental", "dentist", "dental clinic", "dentistry",
            "orthodontist", "orthodontics",
        ),
        "wellness": (
            "wellness", "wellness practice", "holistic", "wellness center",
            "wellness centre", "chiropractic", "chiropractor",
            "physiotherapy", "physical therapy",
        ),
    },
}


_WORD_BOUNDARY = re.compile(r"[^a-z0-9]+")


def _norm(text: str) -> str:
    """Lowercase + collapse non-alphanumerics to spaces, padded for substring search."""
    if not text:
        return ""
    return " " + _WORD_BOUNDARY.sub(" ", text.lower()).strip() + " "


def _phrase_in(needle: str, haystack: str) -> bool:
    if not needle:
        return False
    n = _norm(needle)
    if n.strip() == "":
        return False
    return n in haystack


def _hits(terms: tuple[str, ...], haystack: str) -> list[str]:
    return [t for t in terms if _phrase_in(t, haystack)]


def classify(prompt: str) -> NicheClassification | None:
    """Pick the best (category, sub_niche) for a prompt.

    Returns None if nothing fires — the caller should fall back to its
    existing pipeline. The confidence formula is:

        category_hits * 0.30  +  sub_niche_hits * 0.40
        (clamped to 1.0)

    so a prompt with one category word and one sub-niche word scores 0.7,
    well above the typical 0.6 threshold.
    """
    if not prompt or not prompt.strip():
        return None

    haystack = _norm(prompt)

    best: NicheClassification | None = None

    for category, terms in _CATEGORY_TERMS.items():
        cat_hits = _hits(terms, haystack)
        if not cat_hits:
            continue

        sub_niche_table = _SUB_NICHES.get(category, {})
        chosen_sub: str | None = None
        sub_hits: list[str] = []
        for sub, sub_terms in sub_niche_table.items():
            hits = _hits(sub_terms, haystack)
            if hits and len(hits) > len(sub_hits):
                chosen_sub = sub
                sub_hits = hits

        confidence = min(1.0, 0.30 * len(cat_hits) + 0.40 * len(sub_hits))
        matched = tuple(dict.fromkeys(cat_hits + sub_hits))

        candidate = NicheClassification(
            category=category,
            sub_niche=chosen_sub,
            confidence=confidence,
            matched_terms=matched,
        )

        if best is None or candidate.confidence > best.confidence:
            best = candidate

    return best


# Convenience predicate for callers that only care whether the signal is
# strong enough to switch pipelines.
def is_confident(result: NicheClassification | None, threshold: float = 0.6) -> bool:
    return result is not None and result.confidence >= threshold
