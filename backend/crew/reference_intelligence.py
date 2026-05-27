"""Reference Intelligence Engine — thin layer over Template Intelligence.

Delegates classification + planning to `template_intelligence.classify_and_plan`
and attaches Open Lovable reference patterns to the resulting plan. The new
archetype scaffolders (SaaS / portfolio / ecommerce) consume those patterns
to keep defaults consistent across outputs without each scaffolder having to
re-load the same data.

This module is purely additive — every existing caller of
`template_intelligence.classify_and_plan` keeps working. Callers that want
the reference context use `reference_intelligence.classify_and_plan`
instead and get back a richer plan.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import template_intelligence as _ti
from .reference_patterns import load_patterns
from .schemas import TemplatePlan
from .templates.registry import get_template
from .templates.matcher import TemplateMatch
from crew.schemas import LayoutStrategy

# Source label attached to plans so the trail / UI can show where the
# reference inspiration came from.
REFERENCE_SOURCE = "open-lovable"


# Categories that have an Open Lovable archetype manifest. When a niche
# classifies into one of these, we prefer the open-lovable-* manifest over
# whatever the generic matcher picked, because the new archetype scaffolders
# expect the page shapes those manifests define.
_OPEN_LOVABLE_KEY_BY_CATEGORY: dict[str, str] = {
    "saas":       "open-lovable-saas",
    "portfolio":  "open-lovable-portfolio",
    "ecommerce":  "open-lovable-ecommerce",
    "healthcare": "open-lovable-healthcare",
}


@dataclass(frozen=True)
class ReferenceDecision:
    """Mirror of `template_intelligence.TemplateDecision` with patterns attached."""
    plan: TemplatePlan | None
    reason: str
    layout_strategy: LayoutStrategy | None = None
    template_match: object | None = None  # original TemplateMatch
    niche: object | None = None           # original NicheClassification

    @property
    def fired(self) -> bool:
        return self.plan is not None


def _attach_patterns(plan: TemplatePlan) -> TemplatePlan:
    """Return a copy of the plan with reference patterns attached.

    The plan's `reference_patterns` and `reference_source` fields are
    populated from the Open Lovable patterns file. We rebuild the model via
    `model_copy(update=...)` so we don't mutate the original (which could
    be shared across callers — TemplatePlan is a Pydantic model, not frozen,
    but treating it as immutable keeps reasoning simple).
    """
    patterns = load_patterns()
    archetype_key = plan.template_key
    archetype_layouts = (patterns.get("archetype_layouts") or {}).get(archetype_key, [])
    # Slim down what we attach — full patterns dict is large; pass only what
    # scaffolders actually use.
    slim = {
        "component_vocabulary": patterns.get("component_vocabulary", {}),
        "motion_conventions": patterns.get("motion_conventions", {}),
        "layout_principles": patterns.get("layout_principles", []),
        "archetype_layout": archetype_layouts,
    }
    return plan.model_copy(update={
        "reference_patterns": slim,
        "reference_source": REFERENCE_SOURCE,
    })


def _prefer_open_lovable(plan: TemplatePlan, niche) -> TemplatePlan:
    """If the niche maps to an Open Lovable archetype, swap to that manifest.

    The default matcher in `template_intelligence` may pick a generic top-level
    template (e.g., `portfolio`, `ecommerce`, `ai-saas`) instead of the new
    Open Lovable manifest for the same category. That's fine for many uses,
    but the new multi-page scaffolders are built around the page shapes
    declared in the open-lovable-* manifests. Swap when one exists so the
    scaffolders see the pages they were designed for.
    """
    # Prefer the niche's category over the matched template's, because the
    # matched template may be a generic (e.g., `portfolio` whose category is
    # "personal") even when the niche clearly says "portfolio".
    target_category = (niche.category if niche is not None else None) or plan.category
    ol_key = _OPEN_LOVABLE_KEY_BY_CATEGORY.get(target_category)
    if not ol_key or plan.template_key == ol_key:
        return plan
    manifest = get_template(ol_key)
    if manifest is None:
        return plan
    # Build a fresh plan from the OL manifest, carrying the original niche
    # (so the scaffolder still gets the right sub_niche and data pack).
    fake_match = TemplateMatch(template=manifest, score=plan.match_score, matched_terms=tuple())
    return _ti._build_plan(fake_match, niche)


def classify_and_plan(
    prompt: str,
    *,
    min_score: int = _ti.DEFAULT_MIN_SCORE,
    min_confidence: float = _ti.DEFAULT_MIN_CONFIDENCE,
) -> ReferenceDecision:
    """Run the template intelligence engine and attach Open Lovable patterns."""
    inner = _ti.classify_and_plan(
        prompt, min_score=min_score, min_confidence=min_confidence,
    )
    if not inner.fired or inner.plan is None:
        return ReferenceDecision(
            plan=None,
            reason=inner.reason,
            layout_strategy=None,
            template_match=inner.match,
            niche=inner.niche,
        )
    preferred = _prefer_open_lovable(inner.plan, inner.niche)
    enriched = _attach_patterns(preferred)

    layout_strategy = generate_layout_strategy(prompt, enriched)
    swap_note = ""
    if preferred.template_key != inner.plan.template_key:
        swap_note = f" -> swapped to '{preferred.template_key}'"
    return ReferenceDecision(
        plan=enriched,
        reason=inner.reason + swap_note,
        layout_strategy=layout_strategy,
        template_match=inner.match,
        niche=inner.niche,
    )


def generate_layout_strategy(prompt: str, plan: TemplatePlan) -> LayoutStrategy:

    text = prompt.lower()

    # -------- wedding websites --------

    if "wedding" in text:

        if any(x in text for x in ["royal", "palace", "indian", "luxury"]):
            return LayoutStrategy(
                visual_style="royal-indian-luxury",
                page_style="cinematic-editorial",
                hero_style="fullscreen-video-overlay",
                navigation_style="floating-glass-navbar",
                section_density="spacious",
                animation_style="cinematic-slow",
                layout_structure=[
                    "hero",
                    "couple-story",
                    "events-timeline",
                    "gallery",
                    "venue-showcase",
                    "rsvp",
                    "footer",
                ],
                page_graph=[
                    {"name": "Home", "route": "/"},
                    {"name": "Story", "route": "/story"},
                    {"name": "Events", "route": "/events"},
                    {"name": "Gallery", "route": "/gallery"},
                    {"name": "RSVP", "route": "/rsvp"},
                ],
            )

        if any(x in text for x in ["beach", "coastal", "ocean"]):
            return LayoutStrategy(
                visual_style="soft-beach-romantic",
                page_style="airy-editorial",
                hero_style="sunset-image-hero",
                navigation_style="minimal-transparent",
                section_density="comfortable",
                animation_style="floaty-soft",
                layout_structure=[
                    "hero",
                    "love-story",
                    "travel-info",
                    "gallery",
                    "schedule",
                    "rsvp",
                ],
                page_graph=[
                    {"name": "Home", "route": "/"},
                    {"name": "Travel", "route": "/travel"},
                    {"name": "Schedule", "route": "/schedule"},
                    {"name": "Gallery", "route": "/gallery"},
                    {"name": "RSVP", "route": "/rsvp"},
                ],
            )

    # -------- restaurant --------

    if plan.category == "restaurant":

        return LayoutStrategy(
            visual_style="editorial-food-luxury",
            page_style="immersive-restaurant",
            hero_style="food-cinematic",
            navigation_style="sticky-dark-navbar",
            section_density="comfortable",
            animation_style="smooth-premium",
            layout_structure=[
                "hero",
                "chef-specials",
                "menu-preview",
                "gallery",
                "reservation-banner",
                "footer",
            ],
            page_graph=[
                {"name": "Home", "route": "/"},
                {"name": "Menu", "route": "/menu"},
                {"name": "Gallery", "route": "/gallery"},
                {"name": "Reservations", "route": "/reservations"},
                {"name": "Contact", "route": "/contact"},
            ],
        )

    # -------- fallback --------

    return LayoutStrategy(
        visual_style="modern-premium",
        page_style="clean-modern",
        hero_style="split-hero",
        navigation_style="standard-topbar",
        section_density="comfortable",
        animation_style="subtle",
        layout_structure=[
            "hero",
            "features",
            "gallery",
            "cta",
        ],
        page_graph=[
            {"name": "Home", "route": "/"},
        ],
    )