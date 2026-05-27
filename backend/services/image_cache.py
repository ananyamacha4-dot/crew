"""Hash-keyed disk cache for generated images.

Layout: backend/storage/generated_assets/<sha256_prefix>.png
Public URL: f"{PUBLIC_BACKEND_URL}/assets/<sha256_prefix>.png"

The same (provider, prompt, width, height, seed) tuple always maps to the same
file so re-generations never re-call Imagen. Atomic writes mean partially
written files never get served.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def cache_dir() -> Path:
    """Return the asset cache directory, creating it on first call."""
    # backend/services/image_cache.py -> backend/storage/generated_assets/
    here = Path(__file__).resolve()
    d = here.parents[1] / "storage" / "generated_assets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _backend_url() -> str:
    """Origin used for `/assets/...` URLs. Set PUBLIC_BACKEND_URL in production."""
    return os.getenv("PUBLIC_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")


def cache_key(provider: str, prompt: str, width: int, height: int, seed: int | None) -> str:
    """Deterministic short hash for (provider, prompt, size, seed) tuples."""
    blob = f"{provider}|{prompt}|{int(width)}x{int(height)}|{int(seed or 0)}".encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:32]


def cached_path(key: str) -> Path:
    """Filesystem path where the asset lives (may or may not exist)."""
    return cache_dir() / f"{key}.png"


def cached_url(key: str) -> str:
    """Public URL the frontend / generated React code uses to load the asset."""
    return f"{_backend_url()}/assets/{key}.png"


def write_atomic(path: Path, data: bytes) -> None:
    """Write `data` to `path` atomically. Never leaves a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
