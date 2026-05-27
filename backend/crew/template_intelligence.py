"""Template Intelligence Engine — niche + template + content composer.

Sits in front of the existing landing pipeline. Given a free-form user prompt,
runs the niche classifier, the template matcher, the page planner, the
navigation builder, and the content-pack resolver, then returns ONE
`TemplatePlan` that the multi-page scaffolder consumes.

When the signal is weak the function returns None and the caller falls back
to the existing Brief→Design→Content→Scaffold pipeline unchanged.

This module is purely additive — it does not modify existing classes or
mutate any global state. It reuses, in order:

  niche_classifier.classify        — keyword-based category/sub-niche
  templates.matcher.match_template — manifest scorer (existing)
  templates.page_planner.plan_*    — manifest → PageSpec / InteractionSpec
  templates.navigation.build_*     — header + footer + route validation
  content_catalog.pack_for_niche   — curated data pack for the niche
"""

from __future__ import annotations

from dataclasses import dataclass

from .content_catalog import pack_for_niche, pack_name_for_niche
from .niche_classifier import NicheClassification, classify, is_confident
from .schemas import NicheClassificationModel, TemplatePlan
from .templates.matcher import TemplateMatch, match_template, score_templates
from .templates.navigation import build_navigation
from .templates.page_planner import plan_interactions, plan_pages
from .templates.registry import TemplateManifest, get_template


# ---------------------------------------------------------------------------
# Tuning knobs (kept conservative so the existing pipeline keeps the default)
# ---------------------------------------------------------------------------

# Minimum template score required before we override the existing pipeline.
# Matches the default in templates.matcher.match_template (3) but gives us
# a single knob to tune here.
DEFAULT_MIN_SCORE = 3

# Minimum niche confidence to fire the templated path.
DEFAULT_MIN_CONFIDENCE = 0.6


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _pick_template_for_niche(
    prompt: str,
    niche: NicheClassification | None,
    *,
    min_score: int,
) -> TemplateMatch | None:
    """Choose the best template manifest for the prompt + niche.

    Strategy:
      1. If the niche has a sub_niche, look for an exact key
         `{category}-{sub_niche}` in the registry. That's the strongest
         signal and bypasses scoring.
      2. Otherwise (or if that key isn't registered) fall back to the
         keyword scorer, but boost any manifest whose category matches
         the resolved niche by +3 so a generic restaurant prompt picks
         the restaurant template instead of a coincidentally-keyword-rich
         coffee one.
      3. Final gate: the chosen match must clear `min_score`.
    """
    if niche is not None and niche.sub_niche:
        direct_key = f"{niche.category}-{niche.sub_niche}"
        direct = get_template(direct_key)
        if direct is not None:
            return TemplateMatch(
                template=direct,
                score=max(min_score, 5),
                matched_terms=(direct_key,) + tuple(niche.matched_terms),
            )

    scored = score_templates(prompt)
    if not scored:
        return None

    if niche is not None:
        boosted: list[TemplateMatch] = []
        for m in scored:
            score = m.score
            if m.template.category and m.template.category.lower() == niche.category.lower():
                score += 3
            boosted.append(TemplateMatch(template=m.template, score=score, matched_terms=m.matched_terms))
        boosted.sort(key=lambda x: x.score, reverse=True)
        scored = boosted

    top = scored[0]
    if top.score < min_score:
        return None
    return top


def _to_niche_model(niche: NicheClassification | None) -> NicheClassificationModel | None:
    if niche is None:
        return None
    return NicheClassificationModel(
        category=niche.category,
        sub_niche=niche.sub_niche,
        confidence=niche.confidence,
        matched_terms=list(niche.matched_terms),
    )


def _resolve_pack(
    manifest: TemplateManifest,
    niche: NicheClassification | None,
) -> tuple[str | None, list[dict]]:
    """Resolve the niche pack first; fall back to the manifest's declared data_packs."""
    if niche is not None:
        pack_name = pack_name_for_niche(niche.category, niche.sub_niche)
        if pack_name:
            pack = pack_for_niche(niche.category, niche.sub_niche) or []
            return pack_name, pack
    if manifest.data_packs:
        from .content_catalog import get_pack  # local import — only when needed
        first = manifest.data_packs[0]
        return first, get_pack(first)
    return None, []


def _build_plan(
    match: TemplateMatch,
    niche: NicheClassification | None,
) -> TemplatePlan:
    manifest = match.template
    design = manifest.design or {}
    fonts_raw = design.get("fonts") or {}
    fonts = {k: str(v) for k, v in fonts_raw.items() if isinstance(v, str)}

    pages = plan_pages(manifest)
    interactions = plan_interactions(manifest)
    navigation = build_navigation(manifest)
    pack_name, pack = _resolve_pack(manifest, niche)

    return TemplatePlan(
        template_key=manifest.key,
        template_label=manifest.label,
        category=manifest.category,
        sub_niche=(niche.sub_niche if niche else None),
        design_mode_hint=str(design.get("design_mode_hint") or "") or None,
        palette_hint=str(design.get("palette_hint") or "") or None,
        mood=[str(m) for m in (design.get("mood") or [])],
        fonts=fonts,
        pages=pages,
        interactions=interactions,
        navigation=navigation,
        image_subjects=list(manifest.image_subjects),
        data_pack_name=pack_name,
        data_pack=pack,
        niche=_to_niche_model(niche),
        match_score=match.score,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TemplateDecision:
    """Diagnostic-friendly result. `plan` is None when the caller should fall back."""
    plan: TemplatePlan | None
    niche: NicheClassification | None
    match: TemplateMatch | None
    reason: str

    @property
    def fired(self) -> bool:
        return self.plan is not None


def classify_and_plan(
    prompt: str,
    *,
    min_score: int = DEFAULT_MIN_SCORE,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> TemplateDecision:
    """Compose niche detection + template matching + plan assembly.

    Fires (returns a non-None plan) when EITHER:
      - the niche classifier is confident AND a matching template exists, OR
      - the template scorer alone fires strongly (score >= min_score + 2)

    Otherwise returns a decision with `plan=None` and a short `reason`
    suitable for the agent trail breadcrumb.
    """
    if not prompt or not prompt.strip():
        return TemplateDecision(plan=None, niche=None, match=None, reason="empty prompt")

    niche = classify(prompt)

    # Path 1: confident niche
    if is_confident(niche, threshold=min_confidence):
        match = _pick_template_for_niche(prompt, niche, min_score=min_score)
        if match is not None:
            return TemplateDecision(
                plan=_build_plan(match, niche),
                niche=niche,
                match=match,
                reason=f"niche {niche.slug!r} -> template {match.template.key!r} (score {match.score})",
            )
        # niche found but no template — fall through to direct match below

    # Path 2: strong template signal even without niche
    direct = match_template(prompt, min_score=min_score + 2)
    if direct is not None:
        return TemplateDecision(
            plan=_build_plan(direct, niche),
            niche=niche,
            match=direct,
            reason=f"template-only match {direct.template.key!r} (score {direct.score})",
        )

    why = "no niche, no template match"
    if niche is not None:
        why = f"niche {niche.slug!r} weak (confidence {niche.confidence:.2f}); no template fired"
    return TemplateDecision(plan=None, niche=niche, match=None, reason=why)
