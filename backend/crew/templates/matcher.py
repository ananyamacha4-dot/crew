"""Match a free-form user prompt to a template manifest.

Heuristic-first scoring. Each template is scored against the prompt; the
winner is returned only when it clears a confidence threshold so we don't
hijack vague prompts that the existing intent classifier should keep.

Score signals:
    + 5  exact key match anywhere in the prompt          ("coffee-shop")
    + 4  exact category-label phrase in the prompt       ("coffee shop")
    + 3  match_keyword appears in the prompt
    + 2  category name appears in the prompt
    + 1  kind hint appears                               ("dashboard", "website")
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .registry import TemplateManifest, list_templates


@dataclass(frozen=True)
class TemplateMatch:
    template: TemplateManifest
    score: int
    matched_terms: tuple[str, ...]

    @property
    def key(self) -> str:
        return self.template.key


_WORD_BOUNDARY = re.compile(r"\b")


def _norm(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9]+", " ", text.lower()).strip() + " "


def _phrase_hit(needle: str, haystack: str) -> bool:
    needle = _norm(needle)
    if needle.strip() == "":
        return False
    return needle in haystack


def score_templates(prompt: str) -> list[TemplateMatch]:
    """Return all templates with score > 0, highest first."""
    if not prompt or not prompt.strip():
        return []
    haystack = _norm(prompt)
    out: list[TemplateMatch] = []
    for tpl in list_templates():
        score = 0
        hits: list[str] = []

        key_phrase = tpl.key.replace("-", " ")
        if _phrase_hit(key_phrase, haystack):
            score += 5
            hits.append(tpl.key)

        if tpl.label and _phrase_hit(tpl.label, haystack):
            score += 4
            hits.append(tpl.label.lower())

        for kw in tpl.match_keywords:
            if _phrase_hit(kw, haystack):
                score += 3
                hits.append(kw)

        if tpl.category and _phrase_hit(tpl.category, haystack):
            score += 2
            hits.append(tpl.category)

        if tpl.kind and _phrase_hit(tpl.kind, haystack):
            score += 1
            hits.append(tpl.kind)

        if score > 0:
            # de-dup hits while preserving order
            seen: set[str] = set()
            unique_hits = []
            for h in hits:
                if h not in seen:
                    unique_hits.append(h)
                    seen.add(h)
            out.append(TemplateMatch(template=tpl, score=score, matched_terms=tuple(unique_hits)))

    out.sort(key=lambda m: m.score, reverse=True)
    return out


def match_template(prompt: str, *, min_score: int = 3) -> TemplateMatch | None:
    """Highest-scoring template if it clears `min_score`, else None.

    `min_score=3` means at least one specific keyword fired (or the category
    name was used). That keeps casual prompts like "make me an app" from
    being forcibly templated.
    """
    scored = score_templates(prompt)
    if not scored:
        return None
    top = scored[0]
    if top.score < min_score:
        return None
    return top
