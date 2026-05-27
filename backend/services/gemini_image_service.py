"""Imagen 4 (Gemini Developer API) wrapper. Returns PNG bytes or `None`.

Never raises — callers do `if data is None: fall back to Pollinations`.
Lazy client init means importing this module is always safe (no key, no SDK,
no network → quiet None returns).

Concurrent calls share a single `genai.Client` protected by a one-shot lock.
After the first init failure (missing key, ImportError, etc.) the failure is
cached so subsequent calls don't keep paying the same cost.

Default model is `imagen-4.0-fast-generate-001` — fastest of the Imagen 4
family and the cheapest per image, which matters because a single website
generation can request 10-20 images. Override via the `IMAGEN_MODEL` env
var to swap in `imagen-4.0-generate-001` (standard) or
`imagen-4.0-ultra-generate-001` (highest quality, slowest, most expensive).
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Literal

_log = logging.getLogger(__name__)

AspectRatio = Literal["1:1", "3:4", "4:3", "9:16", "16:9"]

# Allow overriding the model via env var without code change.
# Available on the Gemini Developer API key (verified at runtime):
#   imagen-4.0-fast-generate-001   (fast, cheap — default)
#   imagen-4.0-generate-001        (standard quality)
#   imagen-4.0-ultra-generate-001  (highest quality, slowest, most expensive)
_DEFAULT_MODEL = os.getenv("IMAGEN_MODEL", "imagen-4.0-fast-generate-001")


_client = None
_client_lock = threading.Lock()
_client_init_failed = False

# Short-circuit after persistent failures (free-tier 403 on Imagen, daily
# quota exhaustion, etc.) so we don't burn ~400ms per image on a doomed call.
# Reset by restarting the process (or by failures clearing naturally after
# `_BLOCK_AFTER_FAILURES` consecutive failures triggers it).
_consecutive_failures = 0
_BLOCK_AFTER_FAILURES = 3
_blocked = False
_BLOCK_RESET_AFTER = 60  # seconds — try once again after this cool-down
import time as _time
_blocked_at = 0.0


def _get_client():
    """Return a shared `genai.Client`, or None if init has ever failed."""
    global _client, _client_init_failed
    if _client is not None or _client_init_failed:
        return _client
    with _client_lock:
        if _client is not None or _client_init_failed:
            return _client
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            _log.info("GEMINI_API_KEY not set — Imagen disabled, falling back to Pollinations.")
            _client_init_failed = True
            return None
        try:
            from google import genai  # google-genai SDK
            _client = genai.Client(api_key=api_key)
        except Exception as e:  # noqa: BLE001
            _log.warning("Gemini SDK init failed: %s", e)
            _client_init_failed = True
        return _client


def _aspect_ratio(width: int, height: int) -> AspectRatio:
    """Snap an arbitrary (width, height) to Imagen's nearest supported ratio."""
    if width <= 0 or height <= 0:
        return "1:1"
    ratio = width / height
    candidates: list[tuple[float, AspectRatio]] = [
        (1.0,    "1:1"),
        (0.75,   "3:4"),
        (1.333,  "4:3"),
        (0.5625, "9:16"),
        (1.777,  "16:9"),
    ]
    return min(candidates, key=lambda c: abs(c[0] - ratio))[1]


def _extract_png_bytes(generated_image) -> bytes | None:
    """Pull raw PNG bytes from a GeneratedImage object across SDK shapes."""
    img = getattr(generated_image, "image", None)
    if img is None:
        return None
    # 1) google-genai 2.x: Image.image_bytes attribute
    data = getattr(img, "image_bytes", None)
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    # 2) Some builds expose .data
    data = getattr(img, "data", None)
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    # 3) PIL fallback — re-encode as PNG
    pil = getattr(img, "_pil_image", None) or getattr(img, "pil_image", None)
    if pil is not None:
        try:
            import io
            buf = io.BytesIO()
            pil.save(buf, format="PNG")
            return buf.getvalue()
        except Exception:  # noqa: BLE001
            return None
    return None


def is_available() -> bool:
    """True iff the Gemini path will at least attempt to run.

    Callers can short-circuit before computing a cache key when the provider
    is known-disabled, but `generate_image_bytes` is already a no-op in that
    case, so this is purely a convenience.
    """
    return _get_client() is not None


def _note_failure() -> None:
    """Track consecutive failures and short-circuit after a threshold."""
    global _consecutive_failures, _blocked, _blocked_at
    _consecutive_failures += 1
    if _consecutive_failures >= _BLOCK_AFTER_FAILURES:
        _blocked = True
        _blocked_at = _time.monotonic()
        _log.info(
            "Imagen path blocked for %ds after %d consecutive failures.",
            _BLOCK_RESET_AFTER, _consecutive_failures,
        )


def _note_success() -> None:
    """Reset the failure counter on any success."""
    global _consecutive_failures, _blocked
    _consecutive_failures = 0
    _blocked = False


def _should_skip() -> bool:
    """True when recent failures have tripped the cool-down."""
    if not _blocked:
        return False
    if _time.monotonic() - _blocked_at > _BLOCK_RESET_AFTER:
        # cool-down elapsed — let the next call attempt again
        return False
    return True


def generate_image_bytes(
    prompt: str,
    *,
    width: int = 1024,
    height: int = 576,
    seed: int | None = None,
    timeout: float = 8.0,
    model: str | None = None,
) -> bytes | None:
    """Generate one image with Imagen 4. Returns PNG bytes or None.

    Never raises. `timeout` is plumbed via http_options on the request config
    so a stuck call can't block the generation pipeline for more than the
    given number of seconds. After several consecutive failures (e.g.,
    free-tier 403 / quota), the wrapper short-circuits for a cool-down period
    to avoid wasting time per image on a doomed call.
    """
    if _should_skip():
        return None
    client = _get_client()
    if client is None:
        return None
    prompt = (prompt or "").strip()
    if not prompt:
        return None

    chosen_model = model or _DEFAULT_MODEL
    try:
        from google.genai import types as gtypes

        config_kwargs: dict = {
            "number_of_images": 1,
            "aspect_ratio": _aspect_ratio(width, height),
        }
        # NOTE: the `seed` parameter is intentionally NOT forwarded — the
        # Gemini Developer API (keyed by GEMINI_API_KEY) rejects it with
        # "seed parameter is only supported in Gemini Enterprise Agent
        # Platform mode". The caller's seed still differentiates cache keys
        # in services.image_cache, so requesting "the same seed" still
        # produces a stable URL — we just don't pass the seed to the model.
        # Per-call timeout via http_options. Older SDK builds may not accept
        # this — guarded so a missing field doesn't crash the call.
        try:
            config_kwargs["http_options"] = gtypes.HttpOptions(
                timeout=int(timeout * 1000),
            )
        except Exception:  # noqa: BLE001
            pass

        result = client.models.generate_images(
            model=chosen_model,
            prompt=prompt,
            config=gtypes.GenerateImagesConfig(**config_kwargs),
        )
    except Exception as e:  # noqa: BLE001
        _log.warning("Imagen request failed: %s", e)
        _note_failure()
        return None

    images = getattr(result, "generated_images", None) or []
    if not images:
        _note_failure()
        return None
    data = _extract_png_bytes(images[0])
    if data:
        _note_success()
    else:
        _note_failure()
    return data
