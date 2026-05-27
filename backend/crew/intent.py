"""Top-level intent classifier — runs before the build pipeline.

Routes raw user input to ONE of:
    build  — wants a website / app / game / dashboard (default)
    math   — wants an arithmetic answer ("2+2", "what is 20% of 250")
    image  — wants an image, not an app ("draw...", "image of...")
    chat   — small talk, greeting, generic question — replied to via a small
             LLM call so the assistant feels alive, not a static menu

Heuristic-first (no LLM). Precedence: build > math > image > chat.
"""

from __future__ import annotations

import ast
import operator
import re
from typing import Literal

Intent = Literal["build", "math", "image", "chat"]


# Strong "build" signals. If any of these are in the prompt, treat as build
# even if it also looks like an image or greeting.
_BUILD_HINT_PAT = re.compile(
    r"\b("
    r"website|webapp|web\s*app|app|application|game|dashboard|tool|"
    r"landing\s*page|landing|portfolio|admin\s*panel|"
    r"calculator|todo|to-do|task\s*list|timer|stopwatch|pomodoro|notes|"
    r"snake|tic\s*tac\s*toe|pong|flappy|tetris|2048|wordle|"
    r"clone|builder|generator|tracker|editor|chat\s*app|music\s*player|"
    # Open Lovable archetype hints (saas / portfolio / ecommerce / hospitality / healthcare)
    r"saas|ecommerce|e-commerce|store|shop|boutique|storefront|"
    r"restaurant|cafe|caf\xe9|coffee\s*shop|bakery|"
    r"hospital|clinic|dental|medical|healthcare|wellness|pharmacy"
    r")\b",
    re.I,
)


_IMAGE_PAT = re.compile(
    r"\b("
    r"(?:generate|make|create|render|draw|paint|design|produce|give\s+me)\s+"
    r"(?:an?\s+|some\s+)?(?:image|picture|photo|photograph|illustration|"
    r"render|artwork|art|logo|icon|wallpaper|banner|portrait|landscape)|"
    r"(?:image|picture|photo|illustration|artwork)\s+of\s+|"
    r"^\s*(?:image|picture|photo|illustration|artwork|logo|wallpaper):\s+|"
    r"^\s*(?:draw|paint|sketch|render)\s+(?:a|an|some|the|me|us)\s+\w+"
    r")",
    re.I,
)


# Words we strip before testing for math — "what is 2+2" -> "2+2".
_MATH_PREAMBLE = re.compile(
    r"^\s*(?:"
    r"what(?:'s|s|\s+is)?|"
    r"how\s+much\s+is|"
    r"calculate|compute|solve|evaluate|"
    r"can\s+you\s+(?:tell\s+me\s+)?(?:what(?:'s|s|\s+is)?\s+)?"
    r")\s*",
    re.I,
)

# After preamble strip, the body must look mostly like arithmetic.
_MATH_BODY = re.compile(r"^[\s\d+\-*/().,xX^%]+(?:\s*=\s*\??)?\s*$")


# English-word -> operator substitutions, applied before parsing.
# IMPORTANT: longer / more-specific phrases come first so they aren't eaten
# by shorter ones (e.g., "power of" before bare "of").
_WORD_OPS = [
    (re.compile(r"\b(?:to\s+the\s+)?power\s+of\b", re.I), "**"),
    (re.compile(r"\bmultipl(?:y|ied)\s+by\b", re.I), "*"),
    (re.compile(r"\bdivided\s+by\b", re.I), "/"),
    (re.compile(r"\bmod(?:ulo)?\b", re.I),  "%"),
    (re.compile(r"\bplus\b", re.I),         "+"),
    (re.compile(r"\bminus\b", re.I),        "-"),
    (re.compile(r"\btimes\b", re.I),        "*"),
    (re.compile(r"\bover\b", re.I),         "/"),
    (re.compile(r"\bof\b", re.I),           "*"),
    (re.compile(r"\^"),                     "**"),
    (re.compile(r"\bx\b", re.I),            "*"),
]


# Words that aren't operators but show up in math sentences and should be
# stripped before parsing ("to" in "2 to the power of 10", "the", "result").
_MATH_FILLER = re.compile(r"\b(?:to|the|result|equals?|answer)\b", re.I)


def _to_math_expr(prompt: str) -> str | None:
    """Return a python-evaluable arithmetic string, or None if it's not math."""
    s = _MATH_PREAMBLE.sub("", prompt or "").strip().rstrip("?!.")
    if not s:
        return None
    # Percent FIRST — but only when % is suffixed to a number directly (no
    # space). That way "20% of 250" gets rewritten before "% of" is eaten by
    # the bare "of" rule, and bare "17 % 5" survives as modulo.
    s = re.sub(r"(\d+(?:\.\d+)?)%", r"(\1/100)", s)
    # "multiply 6 by 7" -> "6 * 7"  (handle BEFORE the bare-word op pass)
    s = re.sub(
        r"\bmultipl(?:y|ied)\s+(\d+(?:\.\d+)?)\s+by\s+(\d+(?:\.\d+)?)\b",
        r"\1 * \2",
        s,
        flags=re.I,
    )
    # Convert words to operators
    for pat, repl in _WORD_OPS:
        s = pat.sub(repl, s)
    # Strip math filler words ("to the" in "2 to the power of 10" after sub)
    s = _MATH_FILLER.sub(" ", s)
    s = s.replace(",", "")  # 1,000 -> 1000
    s = re.sub(r"\s+", " ", s).strip().rstrip("=?")
    if not _MATH_BODY.match(s):
        return None
    if not re.search(r"\d", s):
        return None
    return s


# Safe AST-based evaluator — accepts numbers + the operators below, nothing else.
_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _safe_eval(expr: str) -> float | int:
    tree = ast.parse(expr, mode="eval")

    def _eval(node: ast.AST) -> float | int:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            return _BINOPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARYOPS:
            return _UNARYOPS[type(node.op)](_eval(node.operand))
        raise ValueError(f"unsupported node {type(node).__name__}")

    return _eval(tree)


def evaluate_math(prompt: str) -> tuple[str, float | int] | None:
    """If `prompt` is arithmetic, return (canonical_expr, result). Else None."""
    expr = _to_math_expr(prompt)
    if expr is None:
        return None
    try:
        result = _safe_eval(expr)
    except (SyntaxError, ValueError, ZeroDivisionError):
        return None
    # Trim trailing .0 on whole floats
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    return expr, result


def classify_intent(prompt: str) -> Intent:
    """Return one of: 'build' | 'math' | 'image' | 'chat'.

    Precedence:
      1. Build hint wins   — "build me X" beats every other signal.
      2. Math expression   — even "what's 2+2" lands here.
      3. Image request     — "draw / image of" patterns.
      4. Chat              — everything else (greetings, questions, small talk).
    """
    p = (prompt or "").strip()
    if not p:
        return "chat"

    if _BUILD_HINT_PAT.search(p):
        return "build"

    if evaluate_math(p) is not None:
        return "math"

    if _IMAGE_PAT.search(p):
        return "image"

    return "chat"


def extract_image_subject(prompt: str) -> str:
    """Strip command preamble so we feed Pollinations the SUBJECT, not the verb.

    'generate an image of a sunset over Tokyo' -> 'a sunset over Tokyo'
    'draw a cyberpunk samurai' -> 'a cyberpunk samurai' (kept)
    """
    p = (prompt or "").strip()
    p = re.sub(r"^\s*(?:image|picture|photo|illustration|artwork|logo|wallpaper)\s*:\s*", "", p, flags=re.I)
    p = re.sub(
        r"^\s*(?:please\s+)?(?:generate|make|create|render|draw|paint|design|produce|give\s+me)\s+"
        r"(?:an?\s+|some\s+)?(?:image|picture|photo|photograph|illustration|render|artwork|art|"
        r"logo|icon|wallpaper|banner|portrait|landscape)\s+(?:of\s+|that\s+shows\s+|showing\s+|with\s+)?",
        "",
        p,
        flags=re.I,
    )
    p = re.sub(r"^\s*(?:image|picture|photo|illustration|artwork)\s+of\s+", "", p, flags=re.I)
    return p.strip(" ,.;:") or prompt.strip()
