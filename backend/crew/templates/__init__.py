"""Template system for the hybrid AI Builder.

This subpackage is purely additive — none of the existing pipeline modules
(`manager.py`, `scaffold.py`, `app_mode.py`) need to change to coexist with it.
The hybrid pipeline in `crew.hybrid_pipeline` is the opt-in entry point.

Public surface:
    registry       — load template manifests from `awesome-designs/`
    matcher        — match a user prompt to a template key
    page_planner   — turn a matched manifest into PageSpec/InteractionSpec lists
    navigation     — derive functional Header/Footer navigation maps
"""

from .registry import (
    TemplateManifest,
    list_templates,
    get_template,
    registry_path,
)
from .matcher import match_template, score_templates, TemplateMatch
from .page_planner import plan_pages, plan_interactions
from .navigation import build_navigation, validate_routes

__all__ = [
    "TemplateManifest",
    "list_templates",
    "get_template",
    "registry_path",
    "match_template",
    "score_templates",
    "TemplateMatch",
    "plan_pages",
    "plan_interactions",
    "build_navigation",
    "validate_routes",
]
