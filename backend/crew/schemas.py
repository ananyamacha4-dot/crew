"""Pydantic schemas — the typed contracts between agents and the HTTP layer.

Pipeline schemas (Lovable-style multi-agent):
    Stage 1  ProductBrief   (Brief Agent)
    Stage 2  DesignSystem   (Design Director)
    Stage 3  ContentPack    (Content Writer)
    Stage 4  FileSet        (Engineer)
    Stage 5  CritiqueReport (Critic + deterministic QA)

The HTTP-facing models (GenerateRequest/Response, SaveFileRequest) are kept
stable so the Next.js frontend keeps working without changes.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Stack = Literal["static", "react-vite"]


# Field aliases the LLM uses when it emits a dict instead of the expected
# bare string for a list[str] field. We search these in order and pick the
# first non-empty string value.
_STRING_ALIAS_KEYS = (
    "section", "id", "name", "slug", "type",
    "move", "value", "text", "label", "feature",
    "item", "description", "title",
)


def _coerce_to_string_list(value: object) -> object:
    """Accept many shapes the LLM emits for a list[str] field.

    Pass through if already a clean list[str]. Otherwise:
      - "a, b, c" -> ["a", "b", "c"]
      - [{"section": "hero"}, {"move": "thin borders"}] -> ["hero", "thin borders"]
      - [{"name": "x"}, "y"] -> ["x", "y"]
    """
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, str):
                if item.strip():
                    out.append(item.strip())
            elif isinstance(item, dict):
                for k in _STRING_ALIAS_KEYS:
                    v = item.get(k)
                    if isinstance(v, str) and v.strip():
                        out.append(v.strip())
                        break
        return out
    return value


# ===========================================================================
# Stage 1 — Brief
# ===========================================================================

class PageSpec(BaseModel):
    name: str = Field(description="Human page name, e.g. 'Landing', 'Pricing'")
    route: str = Field(description="URL path, e.g. '/', '/pricing'")
    sections: list[str] = Field(
        default_factory=list,
        description=(
            "Ordered section IDs from the controlled vocabulary: hero, "
            "features-grid, feature-spotlight, testimonials, logo-cloud, "
            "pricing-table, faq, cta-band, footer, stats-band, how-it-works, "
            "blog-grid, contact-form, team-grid, gallery-grid, comparison-table, "
            "newsletter, dashboard-shell, sidebar-nav, topbar, stat-cards, "
            "data-table, chart-panel."
        ),
    )
    purpose: str = Field(default="", description="One sentence about this page's job")

    @field_validator("sections", mode="before")
    @classmethod
    def _coerce_sections(cls, value: object) -> object:
        return _coerce_to_string_list(value)


class InteractionSpec(BaseModel):
    element: str = Field(description="Selector-ish ID, e.g. 'nav.cta-button'")
    location: str = Field(default="", description="Where it lives, e.g. 'header right'")
    behavior: str = Field(
        description=(
            "Concrete behavior: 'route to /signup', 'open SignupDialog', "
            "'scroll to #pricing', 'toggle theme', 'submit form with zod validation'"
        ),
    )


class ProductBrief(BaseModel):
    name: str = Field(description="Project name in kebab-case")
    product_type: str = Field(
        description=(
            "Short label: 'saas-landing', 'portfolio', 'ecommerce', 'dashboard', "
            "'blog', 'event', 'mobile-app-landing', 'agency', 'restaurant', etc."
        ),
    )
    audience: str = Field(description="Who this is for, in one sentence")
    mood: list[str] = Field(
        default_factory=list,
        description="3-5 adjectives: 'confident', 'playful', 'minimal', 'warm', etc.",
    )
    differentiator: str = Field(default="", description="What's distinctive about this product")
    pages: list[PageSpec] = Field(default_factory=list)
    interactions: list[InteractionSpec] = Field(default_factory=list)
    must_not: list[str] = Field(default_factory=list)

    @field_validator("mood", "must_not", mode="before")
    @classmethod
    def _coerce_string_list(cls, value: object) -> object:
        return _coerce_to_string_list(value)


# ===========================================================================
# Stage 2 — Design System
# ===========================================================================

class ColorScale(BaseModel):
    name: str = Field(description="Token name: 'primary', 'neutral', 'accent', 'success', 'danger'")
    base: str = Field(description="Base hex, e.g. '#4f46e5'")
    description: str = Field(default="", description="When this color is used")

    @model_validator(mode="before")
    @classmethod
    def _coerce_base_aliases(cls, value: object) -> object:
        if isinstance(value, dict) and "base" not in value:
            for alias in ("base hex", "base_hex", "hex", "color"):
                if alias in value:
                    return {**value, "base": value[alias]}
        return value


class DesignSystem(BaseModel):
    archetype: str = Field(description="Catalog key, e.g. 'linear-minimal', 'stripe-fintech'")
    palette: list[ColorScale] = Field(default_factory=list)
    fonts: dict[str, str] = Field(
        default_factory=dict,
        description="{'display': 'Inter', 'body': 'Inter', 'mono': 'JetBrains Mono'}",
    )
    radius: Literal["sharp", "subtle", "soft", "pill"] = "subtle"
    density: Literal["tight", "comfortable", "spacious"] = "comfortable"
    motion: Literal["none", "subtle", "expressive"] = "subtle"
    signature_moves: list[str] = Field(default_factory=list)

    @field_validator("signature_moves", mode="before")
    @classmethod
    def _coerce_signature_moves(cls, value: object) -> object:
        return _coerce_to_string_list(value)


# ===========================================================================
# Stage 3 — Content Pack
# ===========================================================================

class FeatureBlock(BaseModel):
    title: str
    description: str
    icon: str = Field(description="Lucide icon name, e.g. 'Zap', 'Shield', 'Sparkles'")


class Testimonial(BaseModel):
    quote: str
    author: str
    role: str
    company: str


class PricingTier(BaseModel):
    name: str
    price: str
    period: str = Field(description="'/mo', '/yr', 'one-time', or ''")
    description: str = ""
    features: list[str] = Field(default_factory=list)
    cta_label: str = "Get started"
    highlighted: bool = False

    @field_validator("price", "period", mode="before")
    @classmethod
    def _coerce_scalar_to_str(cls, value: object) -> object:
        if isinstance(value, (int, float)):
            return str(value)
        return value

    @field_validator("features", mode="before")
    @classmethod
    def _coerce_features(cls, value: object) -> object:
        return _coerce_to_string_list(value)


class FAQ(BaseModel):
    question: str
    answer: str


class NavItem(BaseModel):
    label: str
    route: str


class ContentPack(BaseModel):
    brand_name: str
    tagline: str = ""
    hero_headline: str
    hero_subhead: str = ""
    primary_cta: str = "Get started"
    secondary_cta: str | None = None
    nav_items: list[NavItem] = Field(default_factory=list)
    features: list[FeatureBlock] = Field(default_factory=list)
    testimonials: list[Testimonial] = Field(default_factory=list)
    pricing_tiers: list[PricingTier] = Field(default_factory=list)
    faqs: list[FAQ] = Field(default_factory=list)
    footer_links: dict[str, list[NavItem]] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _remap_aliases(cls, value: object) -> object:
        # Llama loves renaming fields. Normalize the most common drift so the
        # pipeline doesn't die on cosmetic key differences.
        if not isinstance(value, dict):
            return value
        aliases: dict[str, tuple[str, ...]] = {
            "hero_headline": ("headline", "header", "hero", "title", "hero_title"),
            "hero_subhead": (
                "subhead", "subheadline", "header_subhead", "subtitle",
                "hero_subtitle", "hero_description", "subheader",
            ),
            "primary_cta": ("cta", "cta_primary", "primary_button", "primary_cta_label"),
            "secondary_cta": ("cta_secondary", "secondary_button"),
            "brand_name": ("brand", "name", "product_name"),
            "nav_items": ("nav", "navigation", "nav_links"),
            "footer_links": ("footer", "footer_columns"),
            "pricing_tiers": ("pricing", "tiers", "plans"),
        }
        out = dict(value)
        for canonical, alt_keys in aliases.items():
            if canonical in out:
                continue
            for k in alt_keys:
                if k in out:
                    out[canonical] = out.pop(k)
                    break
        return out


# ===========================================================================
# Stage 4 — Engineer output
# ===========================================================================

class GeneratedFile(BaseModel):
    path: str
    content: str


class FileSet(BaseModel):
    files: list[GeneratedFile]
    entry: str = "index.html"
    summary: str = ""


# ===========================================================================
# Stage 5 — Critique
# ===========================================================================

class CritiqueScore(BaseModel):
    dimension: str
    score: int = Field(ge=1, le=10)
    note: str = ""


class CritiqueReport(BaseModel):
    ok: bool = False
    overall_score: int = Field(default=5, ge=1, le=10)
    scores: list[CritiqueScore] = Field(default_factory=list)
    must_fix: list[str] = Field(default_factory=list)
    nice_to_fix: list[str] = Field(default_factory=list)
    fixes: list[GeneratedFile] = Field(
        default_factory=list,
        description="REPLACEMENT file contents for any file the critic wants to patch.",
    )


# ===========================================================================
# Legacy schemas (kept so older imports / docs don't break)
# ===========================================================================

class FileStub(BaseModel):
    path: str
    purpose: str


class PlanSpec(BaseModel):
    name: str
    description: str = ""
    stack: Stack = "react-vite"
    files: list[FileStub] = Field(default_factory=list)
    entry: str = "index.html"
    needs_research: bool = False


class ReviewReport(BaseModel):
    ok: bool
    issues: list[str] = Field(default_factory=list)
    fixes: list[GeneratedFile] = Field(default_factory=list)


class PatchSpec(BaseModel):
    changes: list[GeneratedFile] = Field(default_factory=list)
    deletions: list[str] = Field(default_factory=list)
    summary: str = ""


# ===========================================================================
# HTTP request / response shapes (must stay stable for the frontend)
# ===========================================================================

class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    project_id: str | None = Field(
        default=None,
        description="If set, patch the existing project instead of creating a new one.",
    )


class AgentStep(BaseModel):
    agent: str
    summary: str


class GenerateResponse(BaseModel):
    project_id: str
    name: str
    stack: Stack
    entry: str
    files: list[GeneratedFile]
    trail: list[AgentStep] = Field(default_factory=list)
    message: str = ""


class SaveFileRequest(BaseModel):
    path: str = Field(min_length=1, max_length=400)
    content: str
