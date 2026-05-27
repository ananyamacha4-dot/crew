"""Turn a matched TemplateManifest into PageSpec / InteractionSpec lists.

This is the bridge between the static `awesome-designs/` manifests and the
existing pipeline schemas (`crew.schemas.ProductBrief`). It is intentionally
side-effect free and never touches an LLM — it just translates structure.
"""

from __future__ import annotations

from typing import Any

from .registry import TemplateManifest

# We import from the sibling package, not from `__init__`, to keep the import
# graph shallow (`templates` -> `schemas`, not `templates` -> `crew` -> ...).
from ..schemas import InteractionSpec, PageSpec


def plan_pages(manifest: TemplateManifest) -> list[PageSpec]:
    """Materialize the manifest's `pages` list as PageSpec instances."""
    out: list[PageSpec] = []
    for entry in manifest.pages:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "Page").strip() or "Page"
        route = str(entry.get("route") or "/").strip() or "/"
        sections = entry.get("sections") or []
        if not isinstance(sections, list):
            sections = []
        sections = [str(s).strip() for s in sections if isinstance(s, (str, int))]
        purpose = str(entry.get("purpose") or _default_purpose(name, manifest))
        out.append(PageSpec(name=name, route=route, sections=sections, purpose=purpose))
    return out


def _default_purpose(page_name: str, manifest: TemplateManifest) -> str:
    return f"{page_name} page for {manifest.label}"


def plan_interactions(manifest: TemplateManifest) -> list[InteractionSpec]:
    """Derive concrete interactions from the manifest's nav + sections.

    Every nav link becomes a routing interaction; common section IDs
    (forms, carts, players) become concrete behaviors so the engineer
    knows what handlers to wire up.
    """
    out: list[InteractionSpec] = []

    for item in manifest.navigation:
        label = item.get("label") or ""
        route = item.get("route") or "/"
        if not label:
            continue
        out.append(
            InteractionSpec(
                element=f"nav.{_slug(label)}",
                location="header",
                behavior=f"route to {route}",
            )
        )

    # Section-driven interactions.
    seen: set[str] = set()
    for page in manifest.pages:
        if not isinstance(page, dict):
            continue
        for raw in page.get("sections") or []:
            section = str(raw).strip().lower()
            if not section or section in seen:
                continue
            seen.add(section)
            spec = _section_interaction(section, str(page.get("route") or "/"))
            if spec is not None:
                out.append(spec)

    return out


def _slug(text: str) -> str:
    safe = "".join(c.lower() if c.isalnum() else "-" for c in text).strip("-")
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe or "item"


_SECTION_BEHAVIORS: dict[str, tuple[str, str]] = {
    # section_id -> (element, behavior)
    "contact-form":     ("form.contact",      "validate with zod and toast on submit"),
    "booking-form":     ("form.booking",      "validate fields and route to /confirmation on success"),
    "checkout-form":    ("form.checkout",     "validate and submit order, route to /orders/:id"),
    "auth-form":        ("form.auth",         "validate credentials and route to /"),
    "newsletter":       ("form.newsletter",   "validate email and toast on subscribe"),
    "search-bar":       ("input.search",      "filter results below as user types"),
    "cart-drawer":      ("button.cart-toggle","open cart drawer with current items"),
    "cart-table":       ("button.qty",        "increment/decrement quantity, update totals"),
    "filter-sidebar":   ("control.filters",   "toggle facets and re-query the grid"),
    "filter-bar":       ("control.filters",   "apply filters and refresh the table/grid"),
    "kanban-columns":   ("card.drag",         "drag cards between columns and persist order"),
    "now-playing-bar":  ("button.play",       "play/pause current track"),
    "composer":         ("form.compose",      "send message and append to feed"),
    "track-list":       ("row.track",         "play track on click"),
    "results-grid":     ("link.result",       "open detail page for the result"),
    "product-grid":     ("link.product",      "route to /product/:id"),
    "menu-grid":        ("button.add-to-cart","add item to cart and toast"),
    "configurator":     ("control.option",    "update selection and recompute price"),
    "booking-widget":   ("button.book",       "open booking dialog"),
    "data-table":       ("th.sort",           "sort by column on click"),
    "chart-panel":      ("control.range",     "change time range and re-render chart"),
}


def _section_interaction(section: str, route: str) -> InteractionSpec | None:
    spec = _SECTION_BEHAVIORS.get(section)
    if spec is None:
        return None
    element, behavior = spec
    return InteractionSpec(
        element=element,
        location=f"page {route} · section {section}",
        behavior=behavior,
    )
