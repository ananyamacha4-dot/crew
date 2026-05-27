"""Category-aware image prompt sets — extends `services.image_gen`.

`image_gen.generate_image_url()` is the workhorse that talks to Pollinations.
This module wraps it with a category-aware layer: given a template key
(coffee-shop, restaurant, dashboard-analytics, ...) it returns a structured
set of image URLs the generator can drop straight into hero sections, cards,
gallery grids, etc.

Public surface:
    category_subjects(template_key) -> tuple[str, ...]
    image_set_for(template_key, *, brand=None, count=6) -> list[ImageAsset]
    hero_url_for(template_key, *, brand=None) -> str
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from services.image_gen import generate_image_url

if TYPE_CHECKING:
    from services.brand_library import Brand


# ---------------------------------------------------------------------------
# Per-category prompt subjects
# ---------------------------------------------------------------------------

# Each subject is a short noun-phrase. The generator wraps it with a quality
# suffix and the brand tail. Subjects are duplicated from the registry on
# purpose so this module is callable without I/O.
CATEGORY_SUBJECTS: dict[str, tuple[str, ...]] = {
    "coffee-shop": (
        "latte art in ceramic cup, soft window light",
        "espresso machine close-up, warm reflections",
        "single-origin coffee beans on burlap",
        "cozy cafe interior with wooden tables",
        "barista pouring steamed milk",
        "fresh pastries on wooden board",
    ),
    "restaurant": (
        "plated gourmet dish on dark slate",
        "chef finishing a dish in the kitchen",
        "candlelit restaurant interior, warm bokeh",
        "red wine being poured into glass",
        "dessert plating top down",
        "fresh herbs and produce on cutting board",
    ),
    "fashion-store": (
        "editorial fashion model in studio lighting",
        "minimal product shot of jacket on white",
        "streetwear lookbook on city sidewalk",
        "modern boutique interior with bright daylight",
        "accessories flat-lay on linen",
        "model walking the runway, motion blur",
    ),
    "bakery": (
        "golden croissants on cooling rack",
        "decorated layer cake with fresh berries",
        "sourdough loaves with crackling crust",
        "macaron tower assortment",
        "open bakery display case at sunrise",
        "baker shaping dough on floured bench",
    ),
    "ai-saas": (
        "abstract neural network with glowing nodes",
        "futuristic dashboard ui floating in dark space",
        "iridescent data orb on dark background",
        "minimal product mockup on gradient",
    ),
    "startup-landing": (
        "abstract gradient background, soft glow",
        "product device mockup floating",
        "small team collaborating at a whiteboard",
    ),
    "music-streaming": (
        "abstract album cover with vibrant gradient",
        "vinyl record close-up under colored light",
        "concert crowd silhouette with stage lights",
        "music studio with monitors, warm tones",
    ),
    "chat-application": (
        "abstract chat bubbles, soft gradient",
        "team collaboration ui floating",
    ),
    "dashboard-analytics": (
        "abstract isometric chart panels",
        "data visualization with neon accents",
        "minimal stat cards floating on dark background",
    ),
    "kanban-board": (
        "sticky notes arranged on a wall",
        "workflow diagram abstract isometric",
    ),
    "expense-tracker": (
        "abstract finance chart, calming palette",
        "minimal coin stack on neutral surface",
    ),
    "portfolio": (
        "minimalist portrait, studio lighting",
        "creative workspace flat-lay",
        "abstract design mockup on dark gradient",
    ),
    "agency": (
        "modern creative studio workspace",
        "team meeting around large monitor",
        "brand identity mockup flat-lay",
    ),
    "real-estate": (
        "modern house exterior at golden hour",
        "luxury living room with floor-to-ceiling windows",
        "designer kitchen with marble island",
        "city skyline at dusk from penthouse",
    ),
    "photography": (
        "dramatic portrait, single key light",
        "landscape at sunrise, mist over mountains",
        "candid street photography, soft grain",
        "wedding moment, golden hour backlight",
    ),
    "fitness": (
        "athlete training in modern gym, cinematic",
        "yoga pose silhouette at sunrise",
        "kettlebell on rubber floor close-up",
        "personal trainer coaching client",
    ),
    "travel-booking": (
        "mountain landscape with hiker silhouette",
        "tropical beach overhead drone shot",
        "narrow european street with travelers",
        "hot air balloons over cappadocia at sunrise",
        "ancient temple at golden hour",
    ),
    "hotel": (
        "luxury hotel room with city view",
        "infinity pool at sunset with mountains",
        "minimal spa interior, warm wood",
        "boutique hotel lobby with art",
    ),
    "ecommerce": (
        "premium product on white seamless background",
        "lifestyle product shot, soft natural light",
        "packaging design flat-lay",
    ),
    "furniture-store": (
        "scandinavian living room with neutral palette",
        "wooden chair, studio product shot",
        "minimalist bedroom, soft morning light",
        "natural materials close-up: oak, linen, brass",
    ),
    "car-showcase": (
        "luxury car studio shot, gradient lighting",
        "ev charging at modern station, dusk",
        "car interior dashboard with ambient lighting",
        "car driving on winding mountain road",
    ),
    "education-platform": (
        "student studying with laptop, soft daylight",
        "modern lecture hall, depth of field",
        "books and notebook on desk flat-lay",
        "online learning ui mockup on gradient",
    ),
    "movie-streaming": (
        "cinematic film still, dramatic lighting",
        "abstract film poster composition",
        "popcorn close-up in red and white box",
        "empty cinema interior with red seats",
    ),
    "food-delivery": (
        "burger close-up with melted cheese",
        "pizza shot top down on wooden table",
        "noodle bowl with steam, chopsticks",
        "delivery driver on scooter, city blur",
    ),
    "crypto-dashboard": (
        "abstract candlestick chart, neon palette",
        "futuristic trading floor with glowing screens",
        "minimal coin stack on gradient",
    ),
    "banking-app": (
        "minimal credit card mockup on gradient",
        "abstract finance pattern, calm palette",
        "modern bank interior with natural light",
    ),
    "medical-clinic": (
        "doctor with patient, warm clinic interior",
        "modern medical clinic reception, soft palette",
        "smiling doctor portrait, clean background",
        "stethoscope on neutral surface, soft focus",
    ),
    "gaming-platform": (
        "neon arcade interior with glowing signage",
        "esports stage with bright stage lights",
        "abstract game cover art, vivid colors",
        "controller close-up on dark surface",
    ),
    "news-magazine": (
        "editorial photo cover composition",
        "newsroom with monitors and writers",
        "abstract editorial illustration",
    ),
    "social-media": (
        "abstract avatar pattern grid",
        "social media ui mockup on gradient",
        "diverse lifestyle photo, candid moment",
    ),
}


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ImageAsset:
    """A single ready-to-use image URL + the subject behind it."""
    subject: str
    url: str
    seed: int


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def category_subjects(template_key: str) -> tuple[str, ...]:
    """Return the curated subjects for a template, or () if unknown."""
    return CATEGORY_SUBJECTS.get((template_key or "").strip().lower(), ())


def hero_url_for(
    template_key: str,
    *,
    brand: "Brand | None" = None,
    width: int = 1280,
    height: int = 640,
    seed: int | None = None,
) -> str:
    """First subject in the category, expanded into a full Pollinations URL."""
    subjects = category_subjects(template_key)
    if not subjects:
        subject = f"{template_key.replace('-', ' ')} editorial hero"
    else:
        subject = subjects[0]
    prompt = _wrap_with_brand(subject, brand)
    return generate_image_url(prompt, width=width, height=height, seed=seed)


def image_set_for(
    template_key: str,
    *,
    brand: "Brand | None" = None,
    count: int = 6,
    width: int = 960,
    height: int = 540,
    seed: int | None = None,
) -> list[ImageAsset]:
    """Return up to `count` image assets for the category, cycling subjects."""
    subjects = list(category_subjects(template_key))
    if not subjects:
        return []
    rng = random.Random(seed)
    chosen: list[str] = []
    while len(chosen) < max(0, count):
        chosen.extend(subjects)
    chosen = chosen[: count]

    out: list[ImageAsset] = []
    for subject in chosen:
        asset_seed = rng.randint(1, 10_000_000)
        prompt = _wrap_with_brand(subject, brand)
        url = generate_image_url(prompt, width=width, height=height, seed=asset_seed)
        out.append(ImageAsset(subject=subject, url=url, seed=asset_seed))
    return out


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

_QUALITY_TAIL = "8k, professional photography, no text, no watermark"


def _wrap_with_brand(subject: str, brand: "Brand | None") -> str:
    parts = [subject]
    if brand and getattr(brand, "description", ""):
        first_sentence = brand.description.split(".")[0].strip()
        if first_sentence:
            parts.append(f"styled like {brand.name}: {first_sentence[:120]}")
    parts.append(_QUALITY_TAIL)
    return ", ".join(parts)
