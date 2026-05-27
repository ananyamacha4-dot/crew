"""Functional navigation generator.

The engineering rule in the spec is non-negotiable:
    every <Link to="/x"> MUST have a matching <Route path="/x">.

This module produces the data the engineer needs to honor that rule:

  build_navigation(manifest) -> dict with three lists
      header   — top-level nav (drives <Header>)
      footer   — column-grouped links (drives <Footer>)
      routes   — every page route the app must mount

  validate_routes(nav, pages) -> list[str]
      Returns a list of warnings for any nav link without a matching route.
      Used by the QA pass to fail-closed on dead buttons.
"""

from __future__ import annotations

from typing import Any

from ..schemas import NavItem
from .registry import TemplateManifest


def build_navigation(manifest: TemplateManifest) -> dict[str, Any]:
    header_items = [
        NavItem(label=item["label"], route=item["route"])
        for item in manifest.navigation
        if item.get("label") and item.get("route")
    ]

    routes: list[str] = []
    seen: set[str] = set()
    for page in manifest.pages:
        route = str(page.get("route") or "").strip()
        if not route or route in seen:
            continue
        seen.add(route)
        routes.append(route)

    footer = _default_footer(manifest, header_items)

    return {
        "header": [item.model_dump() for item in header_items],
        "footer": {col: [it.model_dump() for it in items] for col, items in footer.items()},
        "routes": routes,
    }


def _default_footer(
    manifest: TemplateManifest,
    header_items: list[NavItem],
) -> dict[str, list[NavItem]]:
    """A reasonable default footer derived from the template's role.

    We don't try to be clever here — the content writer can rewrite this
    later. The goal is just to give the engineer a complete, link-only
    footer that won't render dead buttons.
    """
    product_col: list[NavItem] = []
    company_col: list[NavItem] = []
    resources_col: list[NavItem] = []

    for item in header_items:
        label_lower = item.label.lower()
        if label_lower in {"about", "contact", "careers", "team"}:
            company_col.append(item)
        elif label_lower in {"docs", "blog", "guides", "help", "support"}:
            resources_col.append(item)
        else:
            product_col.append(item)

    footer = {"Product": product_col, "Company": company_col, "Resources": resources_col}
    # drop empty columns
    return {col: items for col, items in footer.items() if items}


def validate_routes(navigation: dict[str, Any], pages: list[dict[str, Any]]) -> list[str]:
    page_routes = {str(p.get("route") or "").strip() for p in pages if isinstance(p, dict)}
    warnings: list[str] = []

    for entry in navigation.get("header") or []:
        route = str(entry.get("route") or "")
        if route.startswith("#") or route.startswith("http"):
            continue
        base = route.split("?", 1)[0].split("#", 1)[0]
        if base and base not in page_routes:
            warnings.append(f"nav link {route!r} has no matching route in pages")

    for items in (navigation.get("footer") or {}).values():
        for entry in items:
            route = str(entry.get("route") or "")
            if route.startswith("#") or route.startswith("http"):
                continue
            base = route.split("?", 1)[0].split("#", 1)[0]
            if base and base not in page_routes:
                warnings.append(f"footer link {route!r} has no matching route in pages")

    return warnings
