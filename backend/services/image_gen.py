"""Image generation via Pollinations.ai — free, no API key, URL-based.

Pollinations exposes `https://image.pollinations.ai/prompt/<urlencoded_prompt>`
which returns a generated PNG when you GET the URL. We never store or proxy
the image — we just hand the URL back to the frontend, which renders it via
the existing image-URL detector in Chat.tsx.

Public surface:
    generate_image_url(prompt, *, width=1024, height=576, seed=None) -> str
    generate_hero_image_url(brief, brand=None) -> str
        Convenience that builds a domain-aware hero prompt from a ProductBrief.
"""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from typing import TYPE_CHECKING
from urllib.parse import quote

if TYPE_CHECKING:
    from crew.schemas import ProductBrief
    from services.brand_library import Brand


_log = logging.getLogger(__name__)

POLLINATIONS_BASE = "https://image.pollinations.ai/prompt"


# --- Pollinations pre-fetch helpers (additive) ---------------------------
# Single shared httpx.Client gives us HTTP connection pooling so 25 parallel
# fetches share TCP/TLS handshakes. Lazy init keeps imports safe.
#
# Pollinations rate-limits the free tier to 1 concurrent request per IP
# (HTTP 402: "Queue full"). The semaphore below serializes the actual HTTP
# call so we never trip that limit, but cache-hit checks (the common case
# on re-generations) stay parallel because the semaphore is acquired AFTER
# the cache lookup.

_http_client = None
_pollinations_fetch_lock = threading.Semaphore(
    int(os.getenv("POLLINATIONS_FETCH_CONCURRENCY", "1") or 1)
)

# Short-circuit pre-fetching for a cooldown period after consecutive failures
# (typically 402 "queue full" from Pollinations free tier). This stops us from
# paying retry-backoff cost on every image once the rate limit is tripped —
# we just embed raw URLs for the rest of the scaffold pass instead.
_PREFETCH_GIVEUP_AFTER = int(os.getenv("POLLINATIONS_GIVEUP_AFTER", "2") or 2)
_PREFETCH_COOLDOWN_SECONDS = float(
    os.getenv("POLLINATIONS_COOLDOWN_SECONDS", "120") or 120
)
_prefetch_consecutive_failures = 0
_prefetch_blocked_at = 0.0
_prefetch_lock = threading.Lock()


def _prefetch_should_skip() -> bool:
    """True when recent failures have tripped the cool-down."""
    if _prefetch_blocked_at <= 0:
        return False
    if time.monotonic() - _prefetch_blocked_at > _PREFETCH_COOLDOWN_SECONDS:
        return False
    return True


def _prefetch_note_failure() -> None:
    global _prefetch_consecutive_failures, _prefetch_blocked_at
    with _prefetch_lock:
        _prefetch_consecutive_failures += 1
        if _prefetch_consecutive_failures >= _PREFETCH_GIVEUP_AFTER:
            _prefetch_blocked_at = time.monotonic()
            _log.info(
                "Pollinations pre-fetch blocked for %ds after %d failures "
                "— remaining images use raw URLs.",
                int(_PREFETCH_COOLDOWN_SECONDS), _prefetch_consecutive_failures,
            )


def _prefetch_note_success() -> None:
    global _prefetch_consecutive_failures, _prefetch_blocked_at
    with _prefetch_lock:
        _prefetch_consecutive_failures = 0
        _prefetch_blocked_at = 0.0


def _get_http_client():
    global _http_client
    if _http_client is not None:
        return _http_client
    try:
        import httpx
    except ImportError:
        return None
    try:
        timeout_s = float(os.getenv("POLLINATIONS_FETCH_TIMEOUT", "20.0"))
    except (TypeError, ValueError):
        timeout_s = 20.0
    _http_client = httpx.Client(
        # 20s total / 5s connect — Pollinations server-side generation of a
        # cold prompt can take 8-15s; CDN-warm hits return in under 1s.
        timeout=httpx.Timeout(timeout_s, connect=5.0),
        follow_redirects=True,
        headers={"User-Agent": "ai-builder/1.0"},
    )
    return _http_client


def _pollinations_url(
    prompt: str, width: int, height: int, seed: int,
    model: str | None, nologo: bool,
) -> str:
    """Build the raw Pollinations URL — extracted so we can both pre-fetch and
    use it as the last-resort fallback string.
    """
    params: list[str] = [
        f"width={int(width)}",
        f"height={int(height)}",
        f"seed={int(seed)}",
    ]
    if nologo:
        params.append("nologo=true")
    chosen_model = model or os.getenv("IMAGE_MODEL", "flux")
    if chosen_model:
        params.append(f"model={quote(chosen_model)}")
    return f"{POLLINATIONS_BASE}/{quote(prompt)}?{'&'.join(params)}"


def _try_pollinations_cache(
    prompt: str, width: int, height: int, seed: int,
    model: str | None, nologo: bool,
) -> str | None:
    """Pre-fetch the Pollinations URL during scaffold and persist the PNG.

    Returns a stable `{PUBLIC_BACKEND_URL}/assets/<hash>.png` URL on success,
    or None on any failure so the caller can fall back to the raw URL.

    Cache-hit lookups are lock-free (parallel-friendly). Actual HTTP fetches
    serialize on `_pollinations_fetch_lock` so we never trip the free-tier
    rate limit (1 concurrent request per IP).
    """
    try:
        from . import image_cache
        key = image_cache.cache_key("pollinations", prompt, width, height, seed)
        path = image_cache.cached_path(key)
        # Fast path: cache hit (no lock, parallel-safe — disk reads are atomic).
        if path.exists() and path.stat().st_size > 0:
            return image_cache.cached_url(key)
        # Short-circuit when we've been rate-limited too many times already.
        if _prefetch_should_skip():
            return None
        client = _get_http_client()
        if client is None:
            return None
        url = _pollinations_url(prompt, width, height, seed, model, nologo)

        # Serialize the actual HTTP call so Pollinations free-tier doesn't
        # 402 us with "queue full". Cache lookups above stay parallel.
        with _pollinations_fetch_lock:
            # Re-check the cache under the lock — another worker may have
            # just filled it while we were waiting.
            if path.exists() and path.stat().st_size > 0:
                _prefetch_note_success()
                return image_cache.cached_url(key)
            if _prefetch_should_skip():
                return None
            try:
                resp = client.get(url)
            except Exception as e:  # noqa: BLE001
                _log.debug("Pollinations fetch raised on %r: %s", prompt[:60], e)
                _prefetch_note_failure()
                return None
            if resp.status_code != 200:
                _prefetch_note_failure()
                return None
            ct = (resp.headers.get("content-type") or "").lower()
            if not ct.startswith("image/"):
                _prefetch_note_failure()
                return None
            data = resp.content
            if not data or len(data) < 100:
                _prefetch_note_failure()
                return None
            image_cache.write_atomic(path, data)
            _prefetch_note_success()
            return image_cache.cached_url(key)
    except Exception as e:  # noqa: BLE001
        _log.debug("Pollinations pre-fetch failed for %r: %s", prompt[:60], e)
        return None


def _try_together(prompt: str, width: int, height: int, seed: int) -> str | None:
    """Try Together.ai FLUX.1-schnell (free tier). Returns cached local URL or None."""
    api_key = os.getenv("TOGETHER_API_KEY")
    if not api_key:
        return None
    try:
        from . import image_cache
        key = image_cache.cache_key("together", prompt, width, height, seed)
        path = image_cache.cached_path(key)
        if path.exists() and path.stat().st_size > 0:
            return image_cache.cached_url(key)

        client = _get_http_client()
        if client is None:
            return None

        resp = client.post(
            "https://api.together.xyz/v1/images/generations",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "black-forest-labs/FLUX.1-schnell-Free",
                "prompt": prompt,
                "width": min(width, 1024),
                "height": min(height, 1024),
                "steps": 4,
                "n": 1,
                "seed": seed,
                "response_format": "b64_json",
            },
        )
        if resp.status_code != 200:
            _log.debug("Together returned %d: %s", resp.status_code, resp.text[:200])
            return None

        import base64
        data_json = resp.json()
        b64 = data_json.get("data", [{}])[0].get("b64_json")
        if not b64:
            return None
        img_bytes = base64.b64decode(b64)
        if len(img_bytes) < 100:
            return None
        image_cache.write_atomic(path, img_bytes)
        return image_cache.cached_url(key)
    except Exception as e:
        _log.debug("Together image gen failed: %s", e)
        return None


def generate_image_url(
    prompt: str,
    *,
    width: int = 1024,
    height: int = 576,
    seed: int | None = None,
    nologo: bool = True,
    model: str | None = None,
) -> str:
    """Build an image URL the frontend can load directly via <img src>.

    Provider chain (tries each, falls through on failure):
      1. Gemini Imagen (if key present)
      2. Together.ai FLUX.1-schnell (free tier, if key present)
      3. Pollinations pre-fetch + cache (stable local URL)
      4. Raw Pollinations URL (last-resort, always works)
    """
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("prompt is empty")
    if seed is None:
        seed = random.randint(1, 10_000_000)

    # --- Provider 1: Imagen 4 (Gemini) ---
    provider = os.getenv("IMAGE_PROVIDER", "auto").strip().lower()
    if provider in ("gemini", "auto"):
        try:
            from . import image_cache, gemini_image_service
            key = image_cache.cache_key("gemini", prompt, width, height, seed)
            path = image_cache.cached_path(key)
            if path.exists() and path.stat().st_size > 0:
                return image_cache.cached_url(key)
            data = gemini_image_service.generate_image_bytes(
                prompt, width=width, height=height, seed=seed, timeout=8.0,
            )
            if data:
                image_cache.write_atomic(path, data)
                return image_cache.cached_url(key)
        except Exception:
            pass

    # --- Provider 2: Together.ai FLUX.1-schnell (free) ---
    together_url = _try_together(prompt, width, height, seed)
    if together_url:
        return together_url

    # --- Provider 3: Pollinations pre-fetch + cache ---
    if os.getenv("POLLINATIONS_PREFETCH", "true").strip().lower() != "false":
        cached = _try_pollinations_cache(prompt, width, height, seed, model, nologo)
        if cached:
            return cached

    # --- Provider 4: raw Pollinations URL (always reachable) ---
    return _pollinations_url(prompt, width, height, seed, model, nologo)


def generate_hero_image_url(
    brief: "ProductBrief",
    brand: "Brand | None" = None,
    *,
    width: int = 1280,
    height: int = 640,
) -> str:
    """Build a hero image whose prompt reflects the brief + brand DNA.

    Used by the build pipeline to give every landing page a real, on-brand
    illustration instead of an empty placeholder.
    """
    parts: list[str] = []

    # Lead with the product domain
    domain_hint = (brief.differentiator or "").strip() or (brief.audience or "").strip()
    if domain_hint:
        parts.append(domain_hint)

    # App-type aesthetic
    app_type = getattr(brief, "app_type", None) or ""
    aesthetic_by_type = {
        "landing":     "editorial hero illustration",
        "dashboard":   "abstract data visualization, isometric chart, glassy panels",
        "game":        "stylized game key art, cinematic lighting",
        "portfolio":   "minimalist photographic still life",
        "ecommerce":   "premium product photography, soft lighting",
        "admin":       "abstract workflow diagram, isometric",
        "chat":        "abstract message bubbles, soft gradient",
        "productivity":"clean stationery flat-lay, soft shadows",
        "tool":        "macro of precision instrument, studio lighting",
        "mobile-app":  "mobile device mockup on neutral surface",
        "editor":      "modern workstation with split screens",
        "social":      "diverse community vignette, candid moment",
    }
    parts.append(aesthetic_by_type.get(app_type, "premium editorial hero"))

    # Mood
    mood = ", ".join((brief.mood or [])[:3])
    if mood:
        parts.append(mood)

    # Brand DNA cue
    if brand and brand.description:
        first_sentence = brand.description.split(".")[0]
        parts.append(f"styled like {brand.name}: {first_sentence[:120]}")

    # Tail keywords for consistency
    parts.append("8k, professional photography, no text, no watermark")

    full_prompt = ", ".join(p for p in parts if p)
    return generate_image_url(full_prompt, width=width, height=height)
