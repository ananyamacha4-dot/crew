"""Hybrid AI Builder pipeline — opt-in, additive entry point.

This module composes the new template / design-reference / content-catalog /
image-catalog modules into a single helper. It does NOT replace the existing
`crew.manager.generate()` flow; instead, callers (CLI tools, an HTTP route,
the existing manager when a flag is set) can call `plan_hybrid_project()`
to get a fully-populated `HybridPlan` and then hand the plan to the existing
scaffold/engineer agents.

Pipeline (per the spec's CORE GENERATION FLOW):

    1. classify intent / match template
    2. detect design inspiration
    3. plan pages + interactions from manifest
    4. build functional navigation + validate routes
    5. attach data packs (menus, products, ...)
    6. attach image asset set (hero + gallery)
    7. return a HybridPlan the existing pipeline can consume

Nothing in this module triggers a network call by default — Pollinations URLs
are *constructed*, not fetched, so the plan stays cheap to build.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from .content_catalog import get_packs
from .design_reference import (
    DesignReferencePrompt,
    InspirationSignal,
    detect_design_inspiration,
    select_prompts_for,
)
from .schemas import InteractionSpec, NavItem, PageSpec, ProductBrief
from .templates import (
    TemplateManifest,
    TemplateMatch,
    build_navigation,
    match_template,
    plan_interactions,
    plan_pages,
    validate_routes,
)

if TYPE_CHECKING:
    from services.brand_library import Brand
    from services.image_catalog import ImageAsset


# ---------------------------------------------------------------------------
# Plan dataclass — the single bag the rest of the pipeline consumes
# ---------------------------------------------------------------------------

@dataclass
class HybridPlan:
    prompt: str
    template: TemplateManifest | None
    template_score: int
    matched_terms: tuple[str, ...]

    pages: list[PageSpec] = field(default_factory=list)
    interactions: list[InteractionSpec] = field(default_factory=list)

    navigation_header: list[NavItem] = field(default_factory=list)
    navigation_footer: dict[str, list[NavItem]] = field(default_factory=dict)
    routes: list[str] = field(default_factory=list)
    route_warnings: list[str] = field(default_factory=list)

    inspiration: InspirationSignal = field(default_factory=lambda: InspirationSignal((), (), ()))
    design_prompts: tuple[DesignReferencePrompt, ...] = ()

    data_packs: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    image_assets: list["ImageAsset"] = field(default_factory=list)
    hero_image_url: str | None = None

    def has_template(self) -> bool:
        return self.template is not None

    def to_brief_seed(self) -> ProductBrief:
        """Materialize a ProductBrief seeded from the matched template.

        The existing Design + Content + Engineer agents accept a ProductBrief
        on input; this lets the hybrid plan slot directly into the current
        pipeline without modifying it.
        """
        tpl = self.template
        name = tpl.key if tpl else "hybrid-project"
        differentiator = (
            f"premium {tpl.label.lower()} starting from the awesome-designs template"
            if tpl else "hybrid generation"
        )
        return ProductBrief(
            name=name,
            app_type=_app_type_for_kind(tpl.kind if tpl else "website"),
            product_type=tpl.kind if tpl else "website",
            audience="users who want a polished, functional multi-page experience",
            mood=list((tpl.design.get("mood") if tpl else None) or ["modern", "premium"]),
            differentiator=differentiator,
            pages=self.pages,
            interactions=self.interactions,
        )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def plan_hybrid_project(
    prompt: str,
    *,
    brand: "Brand | None" = None,
    include_images: bool = True,
    image_count: int = 6,
    min_template_score: int = 3,
) -> HybridPlan:
    """Build a HybridPlan from a free-form user prompt.

    Args:
        prompt:            the raw user input
        brand:             optional Brand chosen by the existing brand picker;
                           used to color image prompts when `include_images`
        include_images:    when True, construct Pollinations URLs for hero +
                           gallery. URLs only — no network call is made here.
        image_count:       number of gallery assets to attach
        min_template_score: pass-through to the template matcher
    """
    match = match_template(prompt, min_score=min_template_score)
    inspiration = detect_design_inspiration(prompt)
    design_prompts = select_prompts_for(inspiration)

    plan = HybridPlan(
        prompt=prompt,
        template=match.template if match else None,
        template_score=match.score if match else 0,
        matched_terms=match.matched_terms if match else (),
        inspiration=inspiration,
        design_prompts=design_prompts,
    )

    if match is None:
        # No template matched — still useful for the design-reference prompts
        # and the inspiration signal. Caller can fall back to the existing
        # `crew.manager.generate()` flow.
        return plan

    manifest = match.template

    plan.pages = plan_pages(manifest)
    plan.interactions = plan_interactions(manifest)

    nav = build_navigation(manifest)
    plan.navigation_header = [NavItem(**item) for item in nav["header"]]
    plan.navigation_footer = {
        col: [NavItem(**item) for item in items]
        for col, items in nav["footer"].items()
    }
    plan.routes = list(nav["routes"])
    plan.route_warnings = validate_routes(nav, list(manifest.pages))

    if manifest.data_packs:
        plan.data_packs = get_packs(manifest.data_packs)

    if include_images:
        # Local import — keeps `services.image_catalog` optional for callers
        # that only want planning without image URLs.
        from services.image_catalog import hero_url_for, image_set_for

        plan.hero_image_url = hero_url_for(manifest.key, brand=brand)
        plan.image_assets = image_set_for(manifest.key, brand=brand, count=image_count)

    return plan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _app_type_for_kind(kind: str) -> str:
    """Map a manifest `kind` to the closest ProductBrief.app_type literal."""
    k = (kind or "").strip().lower()
    if k == "landing":
        return "landing"
    if k == "app":
        return "dashboard"  # most apps in our templates are dashboard-shaped
    return "landing"        # websites are landing-mode in the existing pipeline


# ---------------------------------------------------------------------------
# Convenience — render the plan as a debugging dict
# ---------------------------------------------------------------------------

def plan_to_debug_dict(plan: HybridPlan) -> dict[str, Any]:
    return {
        "matched_template": plan.template.key if plan.template else None,
        "template_score": plan.template_score,
        "matched_terms": list(plan.matched_terms),
        "inspiration": {
            "brands": list(plan.inspiration.brands),
            "aesthetics": list(plan.inspiration.aesthetics),
            "raw_phrases": list(plan.inspiration.raw_phrases),
        },
        "design_prompt_ids": [p.id for p in plan.design_prompts],
        "pages": [
            {"name": p.name, "route": p.route, "sections": list(p.sections)}
            for p in plan.pages
        ],
        "interactions": [
            {"element": i.element, "location": i.location, "behavior": i.behavior}
            for i in plan.interactions
        ],
        "navigation_header": [n.model_dump() for n in plan.navigation_header],
        "navigation_footer": {
            col: [n.model_dump() for n in items]
            for col, items in plan.navigation_footer.items()
        },
        "routes": list(plan.routes),
        "route_warnings": list(plan.route_warnings),
        "data_packs": {name: len(items) for name, items in plan.data_packs.items()},
        "hero_image_url": plan.hero_image_url,
        "image_assets": [
            {"subject": a.subject, "url": a.url, "seed": a.seed}
            for a in plan.image_assets
        ],
    }
