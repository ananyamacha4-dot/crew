"""Loader for `awesome-designs/open-lovable/patterns.json`.

The patterns file is a passive reference document — non-template metadata
(component vocabulary, motion conventions, layout principles, per-archetype
default layouts) inspired by Firecrawl's Open Lovable project. The new
archetype scaffolders read it to keep their defaults consistent across
SaaS / portfolio / ecommerce outputs.

This module is intentionally tiny: filesystem path resolution + an LRU
cache + safe defaults if the file is missing.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


# backend/crew/reference_patterns.py -> repo root is 2 levels up.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PATTERNS_FILE = _REPO_ROOT / "awesome-designs" / "open-lovable" / "patterns.json"


_DEFAULT: dict[str, Any] = {
    "source": "open-lovable",
    "source_repo": "https://github.com/firecrawl/open-lovable",
    "stack": {"in_use": [], "aspirational": []},
    "component_vocabulary": {"primitives": [], "icons_library": "lucide-react", "favored_icons": []},
    "layout_principles": [],
    "responsive_breakpoints": {},
    "motion_conventions": {},
    "archetype_layouts": {},
    "content_principles": [],
}


def patterns_path() -> Path:
    """Public accessor — useful for diagnostics."""
    return _PATTERNS_FILE


@lru_cache(maxsize=1)
def load_patterns() -> dict[str, Any]:
    """Return the parsed patterns document, or a safe default if missing/invalid."""
    if not _PATTERNS_FILE.is_file():
        return dict(_DEFAULT)
    try:
        with _PATTERNS_FILE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return dict(_DEFAULT)
    if not isinstance(data, dict):
        return dict(_DEFAULT)
    # Backfill any missing top-level keys with defaults so callers can
    # always do `patterns["motion_conventions"]` without a None check.
    merged = dict(_DEFAULT)
    merged.update(data)
    return merged


def archetype_layout(key: str) -> list[str]:
    """Return the default section sequence for an archetype key, or []."""
    layouts = load_patterns().get("archetype_layouts") or {}
    seq = layouts.get(key)
    if isinstance(seq, list):
        return [str(s) for s in seq]
    return []


def reload_patterns() -> None:
    """Drop the cache — useful for tests and hot reloads."""
    load_patterns.cache_clear()
