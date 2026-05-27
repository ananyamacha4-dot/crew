"""Load template manifests from the `awesome-designs/` registry.

The registry lives outside the Python package on purpose — it's a content
folder authors can edit without touching code. Each entry follows the shape
documented in `awesome-designs/README.md`.

Lookup order:
  1. `awesome-designs/<key>/template.json`  (per-folder override, if present)
  2. `awesome-designs/registry.json`         (master list, source of truth)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Filesystem layout
# ---------------------------------------------------------------------------

# backend/crew/templates/registry.py -> repo root is 3 levels up.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_REGISTRY_DIR = _REPO_ROOT / "awesome-designs"
_REGISTRY_JSON = _REGISTRY_DIR / "registry.json"


def registry_path() -> Path:
    """Public accessor — handy for diagnostics."""
    return _REGISTRY_DIR


# ---------------------------------------------------------------------------
# Manifest dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TemplateManifest:
    key: str
    label: str
    category: str
    kind: str
    match_keywords: tuple[str, ...]
    pages: tuple[dict[str, Any], ...]
    navigation: tuple[dict[str, str], ...]
    design: dict[str, Any]
    image_subjects: tuple[str, ...] = field(default_factory=tuple)
    data_packs: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TemplateManifest":
        return cls(
            key=str(raw.get("key") or "").strip().lower(),
            label=str(raw.get("label") or raw.get("key") or "").strip(),
            category=str(raw.get("category") or "uncategorized"),
            kind=str(raw.get("kind") or "website"),
            match_keywords=tuple(
                str(k).strip().lower()
                for k in raw.get("match_keywords") or []
                if str(k).strip()
            ),
            pages=tuple(dict(p) for p in raw.get("pages") or []),
            navigation=tuple(
                {"label": str(n.get("label", "")), "route": str(n.get("route", "/"))}
                for n in raw.get("navigation") or []
            ),
            design=dict(raw.get("design") or {}),
            image_subjects=tuple(str(s) for s in raw.get("image_subjects") or []),
            data_packs=tuple(str(s) for s in raw.get("data_packs") or []),
        )


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _safe_read_json(path: Path) -> dict[str, Any] | list[Any] | None:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _load_master() -> list[dict[str, Any]]:
    raw = _safe_read_json(_REGISTRY_JSON)
    if isinstance(raw, dict):
        templates = raw.get("templates")
        if isinstance(templates, list):
            return [t for t in templates if isinstance(t, dict)]
    if isinstance(raw, list):
        return [t for t in raw if isinstance(t, dict)]
    return []


def _load_overrides() -> dict[str, dict[str, Any]]:
    """Per-folder template.json files override the master entry for that key.

    Walks the entire `awesome-designs/` tree (not just the top level) so that
    sub-niche manifests like `restaurant/chinese/template.json` register as
    distinct templates alongside the parent `restaurant/template.json`. Each
    file must declare a unique `key`; later wins on collision (depth order).
    """
    out: dict[str, dict[str, Any]] = {}
    if not _REGISTRY_DIR.is_dir():
        return out
    for candidate in sorted(_REGISTRY_DIR.rglob("template.json")):
        if not candidate.is_file():
            continue
        raw = _safe_read_json(candidate)
        if isinstance(raw, dict) and raw.get("key"):
            out[str(raw["key"]).strip().lower()] = raw
    return out


@lru_cache(maxsize=1)
def _load_all() -> dict[str, TemplateManifest]:
    masters = {str(t.get("key", "")).strip().lower(): t for t in _load_master() if t.get("key")}
    overrides = _load_overrides()
    masters.update(overrides)  # per-folder wins
    return {k: TemplateManifest.from_dict(v) for k, v in masters.items() if k}


def list_templates() -> list[TemplateManifest]:
    """All known template manifests, sorted by key."""
    return sorted(_load_all().values(), key=lambda m: m.key)


def get_template(key: str) -> TemplateManifest | None:
    """Look up a manifest by key (case-insensitive). None if missing."""
    return _load_all().get((key or "").strip().lower())


def reload_registry() -> None:
    """Drop the cache — useful for tests and hot reloads."""
    _load_all.cache_clear()
