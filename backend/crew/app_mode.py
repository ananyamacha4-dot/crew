"""Functional-app builder — bypasses the landing-page pipeline.

When the user asks for a calculator, todo list, timer, etc., the marketing
brief/design/content pipeline is the wrong tool: it always emits a hero +
features + pricing landing page. This module dispatches those prompts to
deterministic single-file React templates that ACTUALLY WORK in Sandpack.

Public surface:
    classify_app_kind(prompt) -> AppKind | None
        None means "this is not an app prompt; use the landing pipeline".
    build_app_project(prompt, kind, brand=None) -> FileSet
        Returns the full FileSet (package.json, index.html, src/*, ...) ready
        for the existing Sandpack preview. When a Brand is passed, every
        template is colored with the brand's palette via Tailwind
        arbitrary-value syntax (bg-[#xxxxxx]).
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Literal

from .schemas import FileSet, GeneratedFile

if TYPE_CHECKING:
    from services.brand_library import Brand

AppKind = Literal[
    "calculator",
    "todo",
    "timer",
    "notes",
    "snake",
    "tictactoe",
    "pong",
    "sudoku",
    "memory",
    "minesweeper",
    "2048",
    "kanban",
    "expense_tracker",
    "functional",
]


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------

# Apps first, then games. Order matters: more specific patterns above generic
# ones (so "snake game" is matched as "snake" before any generic "game"
# fallback would trigger).
_APP_PATTERNS: list[tuple[AppKind, re.Pattern[str]]] = [
    # ----- functional utilities -----
    ("calculator", re.compile(r"\b(calculator|calc\s*app|arithmetic\s+app)\b", re.I)),
    ("todo",       re.compile(r"\b(todo|to-do|task\s*list|task\s*manager|checklist)\b", re.I)),
    ("timer",      re.compile(r"\b(timer|stopwatch|pomodoro|countdown)\b", re.I)),
    ("notes",      re.compile(r"\b(notepad|note[\s-]?taking|notes\s+app|scratchpad)\b", re.I)),
    # ----- games -----
    ("snake",      re.compile(r"\bsnake(\s*game)?\b", re.I)),
    ("tictactoe",  re.compile(r"\b(tic[\s-]?tac[\s-]?toe|noughts\s+and\s+crosses|xo\s*game)\b", re.I)),
    ("pong",       re.compile(r"\bpong(\s*game)?\b", re.I)),
    ("sudoku", re.compile(r"\bsudoku(\s*game)?\b", re.I)),
("memory", re.compile(r"\b(memory|memory\s*game|card\s*match)\b", re.I)),
("minesweeper", re.compile(r"\b(minesweeper|mines)\b", re.I)),
("2048", re.compile(r"\b2048\b", re.I)),
("kanban", re.compile(r"\b(kanban|trello|task\s*board)\b", re.I)),
("expense_tracker", re.compile(r"\b(expense\s*tracker|budget\s*tracker|finance\s*tracker)\b", re.I)),
]


# Generic "this is clearly an app/game, not a marketing page" signal. If a
# prompt matches but no specific template was found, the caller should still
# route through the app/game pipeline rather than dumping the user into a
# Hero + Pricing landing page.
_FUNCTIONAL_HINT = re.compile(
    r"\b("
    r"game|playable|arcade|"
    r"app(?!le)|tool|utility|widget|dashboard|"
    r"editor|player|tracker|generator|converter|builder|"
    r"clicker|simulator"
    r")\b",
    re.I,
)


# Explicit landing-page request — if any of these are in the prompt, we
# DON'T force app mode even if it also contains the word "app".
_LANDING_HINT = re.compile(
    r"\b(landing\s*page|marketing\s*site|homepage|home\s*page|"
    r"product\s*page|website\s*for|sales\s*page|brochure)\b",
    re.I,
)


def classify_app_kind(prompt: str) -> AppKind | None:
    for kind, pat in _APP_PATTERNS:
        if pat.search(prompt):
            return kind

    if looks_like_functional_app(prompt):
        return "functional"

    return None


def looks_like_functional_app(prompt: str) -> bool:
    """True when the prompt clearly wants an interactive product, not a
    marketing page. Used by the manager to decide whether an unmatched prompt
    should still avoid the landing pipeline. False if the prompt explicitly
    says 'landing page' / 'website for X' etc."""
    if _LANDING_HINT.search(prompt):
        return False
    return bool(_FUNCTIONAL_HINT.search(prompt))


def wants_dark_theme(prompt: str) -> bool:
    return bool(re.search(r"\b(dark|night)\s*(theme|mode)?\b", prompt, re.I))


# ---------------------------------------------------------------------------
# FileSet builder
# ---------------------------------------------------------------------------

def build_app_project(prompt: str, kind: AppKind, brand: "Brand | None" = None) -> FileSet:
    dark = wants_dark_theme(prompt) or kind == "calculator"  # calculator defaults dark
    template, app_brand_name, summary_extra = _app_for_kind(kind)

    theme = _derive_theme(brand, dark)
    app_tsx = _inject_theme(template, theme)
    css = _styles_css(theme)

    files = [
        GeneratedFile(path="package.json",       content=_package_json(app_brand_name)),
        GeneratedFile(path="tsconfig.json",      content=_tsconfig()),
        GeneratedFile(path="public/index.html",  content=_index_html(app_brand_name)),
        GeneratedFile(path="src/index.tsx",      content=_index_tsx()),
        GeneratedFile(path="src/styles.css",     content=css),
        GeneratedFile(path="src/lib/utils.ts",   content=_utils_ts()),
        GeneratedFile(path="src/App.tsx",        content=app_tsx),
    ]
    brand_suffix = f" · inspired by {brand.name}" if brand else ""
    summary = f"{app_brand_name}: functional {kind} app · {summary_extra}{brand_suffix}"
    return FileSet(files=files, entry="public/index.html", summary=summary)


def _app_for_kind(kind: AppKind) -> tuple[str, str, str]:
    if kind == "calculator":
        return _CALCULATOR_APP_TSX, "Calc", "arithmetic, keyboard support, themed"

    if kind == "todo":
        return _TODO_APP_TSX, "TaskList", "add/toggle/remove, persisted in localStorage"

    if kind == "timer":
        return _TIMER_APP_TSX, "Timer", "start/pause/reset, ms-precision"

    if kind == "notes":
        return _NOTES_APP_TSX, "Notes", "multi-note, persisted in localStorage"

    if kind == "snake":
        return _SNAKE_APP_TSX, "Snake", "playable canvas game · arrow keys + WASD · score + restart"

    if kind == "tictactoe":
        return _TICTACTOE_APP_TSX, "TicTacToe", "playable · 2-player · win + draw detection + reset"

    if kind == "pong":
        return _PONG_APP_TSX, "Pong", "playable canvas game · paddle + AI opponent + score"

    if kind == "sudoku":
        return _SUDOKU_APP_TSX, "Sudoku", "playable sudoku puzzle with validation"

    if kind == "memory":
        return _MEMORY_APP_TSX, "Memory", "memory card matching game"

    if kind == "minesweeper":
        return _MINESWEEPER_APP_TSX, "Minesweeper", "playable minesweeper game"

    if kind == "2048":
        return _2048_APP_TSX, "2048", "playable 2048 sliding puzzle"

    if kind == "kanban":
        return _KANBAN_APP_TSX, "Kanban", "task management board"

    if kind == "expense_tracker":
        return _EXPENSE_TRACKER_APP_TSX, "ExpenseTracker", "expense tracking dashboard"
    if kind == "functional":
        return (
            _FUNCTIONAL_APP_PROMPT,
            "FunctionalApp",
            "AI-generated functional application"
        )

    raise ValueError(f"unknown app kind {kind!r}")

# ---------------------------------------------------------------------------
# Boilerplate (kept minimal — mirrors scaffold.py shape so Sandpack is happy)
# ---------------------------------------------------------------------------

def _package_json(brand: str) -> str:
    return json.dumps({
        "name": _slugify(brand) or "generated-app",
        "version": "0.0.1",
        "dependencies": {
            "react": "^18.3.1",
            "react-dom": "^18.3.1",
            "lucide-react": "^0.460.0",
            "sonner": "^1.5.0",
            "clsx": "^2.1.1",
            "tailwind-merge": "^2.5.0",
        },
        "main": "src/index.tsx",
    }, indent=2)


def _tsconfig() -> str:
    return json.dumps({
        "compilerOptions": {
            "target": "ES2020",
            "lib": ["ES2020", "DOM", "DOM.Iterable"],
            "module": "ESNext",
            "moduleResolution": "bundler",
            "jsx": "react-jsx",
            "strict": False,
            "esModuleInterop": True,
            "skipLibCheck": True,
            "isolatedModules": True,
            "allowSyntheticDefaultImports": True,
            "baseUrl": ".",
            "paths": {"@/*": ["src/*"]},
        },
        "include": ["src"],
    }, indent=2)


def _index_html(brand: str) -> str:
    title = _escape_html(brand)
    return (
        '<!doctype html>\n<html lang="en">\n  <head>\n'
        '    <meta charset="UTF-8" />\n'
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
        f'    <title>{title}</title>\n'
        '    <script src="https://cdn.tailwindcss.com"></script>\n'
        '  </head>\n  <body>\n    <div id="root"></div>\n  </body>\n</html>\n'
    )


def _index_tsx() -> str:
    return (
        "import { createRoot } from 'react-dom/client';\n"
        "import { Toaster } from 'sonner';\n"
        "import App from './App';\n"
        "import './styles.css';\n\n"
        "const root = createRoot(document.getElementById('root')!);\n"
        "root.render(<><App /><Toaster richColors position=\"top-right\" /></>);\n"
    )


def _utils_ts() -> str:
    return (
        "import { clsx, type ClassValue } from 'clsx';\n"
        "import { twMerge } from 'tailwind-merge';\n\n"
        "export function cn(...inputs: ClassValue[]) {\n"
        "  return twMerge(clsx(inputs));\n"
        "}\n"
    )


def _styles_css(theme: dict[str, str]) -> str:
    color_scheme = "dark" if theme["__dark__"] == "1" else "light"
    return (
        f":root {{ color-scheme: {color_scheme}; }}\n"
        "html, body, #root { height: 100%; }\n"
        f"body {{ margin: 0; background: {theme['BG']}; color: {theme['FG']};\n"
        "       font-family: ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif;\n"
        "       -webkit-font-smoothing: antialiased; }\n"
    )


# ---------------------------------------------------------------------------
# Brand -> calculator theme derivation
# ---------------------------------------------------------------------------

_THEME_TOKEN_NAMES = (
    "BG", "SURFACE", "SURFACE_2", "SURFACE_3",
    "FG", "MUTED_FG", "BORDER",
    "PRIMARY", "PRIMARY_HOVER", "PRIMARY_FG",
    "ACCENT", "ACCENT_HOVER", "ACCENT_FG",
    "OP_BG", "OP_HOVER", "FN_BG", "FN_HOVER", "FN_FG",
    "RING",
)


def _derive_theme(brand: "Brand | None", dark: bool) -> dict[str, str]:
    primary = _safe_hex(brand.primary_hex() if brand else "#8b5cf6", "#8b5cf6")
    accent  = _safe_hex(brand.accent_hex() if brand else "#f97316", "#f97316")

    if dark:
        bg = "#0a0a0a"
        if brand:
            # Try to find a true-dark hex in the brand palette before defaulting.
            for v in brand.colors.values():
                hx = _safe_hex(v)
                if hx and _luminance(hx) < 0.08:
                    bg = hx
                    break
        fg = "#fafafa"
        surface   = _lighten(bg, 0.06)
        surface_2 = _lighten(bg, 0.12)
        surface_3 = _lighten(bg, 0.18)
        muted_fg  = "#9ca3af"
        border    = _lighten(bg, 0.10)
        op_bg     = _mix(primary, bg, 0.65)        # primary tinted dark
        op_hover  = _mix(primary, bg, 0.45)
        fn_bg     = _mix(accent, "#ffffff", 0.65)  # bright neutral fn keys
        fn_hover  = _mix(accent, "#ffffff", 0.55)
        fn_fg     = "#0a0a0a"
    else:
        bg = "#fafafa"
        if brand:
            for v in brand.colors.values():
                hx = _safe_hex(v)
                if hx and _luminance(hx) > 0.92:
                    bg = hx
                    break
        fg = "#0a0a0a"
        surface   = _darken(bg, 0.03)
        surface_2 = _darken(bg, 0.06)
        surface_3 = _darken(bg, 0.10)
        muted_fg  = "#525252"
        border    = _darken(bg, 0.08)
        op_bg     = _mix(primary, "#ffffff", 0.20)
        op_hover  = _mix(primary, "#ffffff", 0.10)
        fn_bg     = _mix(accent, "#ffffff", 0.65)
        fn_hover  = _mix(accent, "#ffffff", 0.55)
        fn_fg     = "#0a0a0a"

    return {
        "__dark__":      "1" if dark else "0",
        "BG":            bg,
        "SURFACE":       surface,
        "SURFACE_2":     surface_2,
        "SURFACE_3":     surface_3,
        "FG":            fg,
        "MUTED_FG":      muted_fg,
        "BORDER":        border,
        "PRIMARY":       primary,
        "PRIMARY_HOVER": _lighten(primary, 0.08) if _luminance(primary) < 0.5 else _darken(primary, 0.08),
        "PRIMARY_FG":    _contrasting_fg(primary),
        "ACCENT":        accent,
        "ACCENT_HOVER":  _lighten(accent, 0.08) if _luminance(accent) < 0.5 else _darken(accent, 0.08),
        "ACCENT_FG":     _contrasting_fg(accent),
        "OP_BG":         op_bg,
        "OP_HOVER":      op_hover,
        "FN_BG":         fn_bg,
        "FN_HOVER":      fn_hover,
        "FN_FG":         fn_fg,
        "RING":          accent,
    }


def _inject_theme(template: str, theme: dict[str, str]) -> str:
    out = template
    for token in _THEME_TOKEN_NAMES:
        out = out.replace(f"__{token}__", theme[token])
    return out


# ---------------------------------------------------------------------------
# Color math
# ---------------------------------------------------------------------------

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _safe_hex(value: str | None, fallback: str = "") -> str:
    if not value:
        return fallback
    s = value.strip()
    m = _HEX_RE.match(s)
    if not m:
        return fallback
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return "#" + h.lower()


def _to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _to_hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{max(0, min(255, c)):02x}" for c in rgb)


def _luminance(hex_color: str) -> float:
    r, g, b = _to_rgb(hex_color)
    # Quick perceptual approximation — good enough to bucket dark vs. light.
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def _lighten(hex_color: str, amount: float) -> str:
    r, g, b = _to_rgb(hex_color)
    return _to_hex((
        int(r + (255 - r) * amount),
        int(g + (255 - g) * amount),
        int(b + (255 - b) * amount),
    ))


def _darken(hex_color: str, amount: float) -> str:
    r, g, b = _to_rgb(hex_color)
    return _to_hex((int(r * (1 - amount)), int(g * (1 - amount)), int(b * (1 - amount))))


def _mix(hex_a: str, hex_b: str, weight_a: float) -> str:
    """Mix two hex colors. weight_a = 1.0 -> all a, 0.0 -> all b."""
    ra, ga, ba = _to_rgb(hex_a)
    rb, gb, bb = _to_rgb(hex_b)
    wa = max(0.0, min(1.0, weight_a))
    wb = 1.0 - wa
    return _to_hex((
        int(ra * wa + rb * wb),
        int(ga * wa + gb * wb),
        int(ba * wa + bb * wb),
    ))


def _contrasting_fg(bg_hex: str) -> str:
    return "#0a0a0a" if _luminance(bg_hex) > 0.55 else "#fafafa"


# ---------------------------------------------------------------------------
# App templates
# ---------------------------------------------------------------------------

_CALCULATOR_APP_TSX = r"""import { useEffect, useState, useCallback } from 'react';

type Op = '+' | '-' | '*' | '/';

const OP_LABEL: Record<Op, string> = { '+': '+', '-': '−', '*': '×', '/': '÷' };

function applyOp(a: number, b: number, op: Op): number {
  switch (op) {
    case '+': return a + b;
    case '-': return a - b;
    case '*': return a * b;
    case '/': return b === 0 ? NaN : a / b;
  }
}

function formatDisplay(n: string): string {
  if (n === '' || n === '-') return n || '0';
  if (n === 'Error') return n;
  if (n.length > 14) {
    const num = Number(n);
    if (!Number.isFinite(num)) return 'Error';
    return num.toPrecision(10).replace(/\.?0+($|e)/, '$1');
  }
  return n;
}

export default function App() {
  const [display, setDisplay] = useState<string>('0');
  const [accumulator, setAccumulator] = useState<number | null>(null);
  const [pendingOp, setPendingOp] = useState<Op | null>(null);
  const [justEvaluated, setJustEvaluated] = useState(false);

  const clearAll = useCallback(() => {
    setDisplay('0');
    setAccumulator(null);
    setPendingOp(null);
    setJustEvaluated(false);
  }, []);

  const inputDigit = useCallback((d: string) => {
    setJustEvaluated(false);
    setDisplay((cur) => {
      if (cur === 'Error') return d;
      if (justEvaluated) return d;
      if (cur === '0') return d;
      if (cur.length >= 14) return cur;
      return cur + d;
    });
  }, [justEvaluated]);

  const inputDecimal = useCallback(() => {
    setDisplay((cur) => {
      if (cur === 'Error' || justEvaluated) return '0.';
      if (cur.includes('.')) return cur;
      return cur + '.';
    });
    setJustEvaluated(false);
  }, [justEvaluated]);

  const toggleSign = useCallback(() => {
    setDisplay((cur) => {
      if (cur === '0' || cur === 'Error') return cur;
      return cur.startsWith('-') ? cur.slice(1) : '-' + cur;
    });
  }, []);

  const percent = useCallback(() => {
    setDisplay((cur) => {
      const n = Number(cur);
      if (!Number.isFinite(n)) return 'Error';
      return String(n / 100);
    });
  }, []);

  const backspace = useCallback(() => {
    setDisplay((cur) => {
      if (cur === 'Error' || justEvaluated) return '0';
      if (cur.length <= 1 || (cur.length === 2 && cur.startsWith('-'))) return '0';
      return cur.slice(0, -1);
    });
  }, [justEvaluated]);

  const chooseOp = useCallback((op: Op) => {
    setDisplay((cur) => {
      const current = Number(cur);
      if (!Number.isFinite(current)) { setAccumulator(null); setPendingOp(null); return 'Error'; }
      if (accumulator === null || pendingOp === null) {
        setAccumulator(current);
      } else if (!justEvaluated) {
        const next = applyOp(accumulator, current, pendingOp);
        if (!Number.isFinite(next)) { setAccumulator(null); setPendingOp(null); return 'Error'; }
        setAccumulator(next);
        return formatDisplay(String(next));
      }
      return cur;
    });
    setPendingOp(op);
    setJustEvaluated(false);
  }, [accumulator, pendingOp, justEvaluated]);

  const equals = useCallback(() => {
    setDisplay((cur) => {
      const current = Number(cur);
      if (accumulator === null || pendingOp === null) return cur;
      const next = applyOp(accumulator, current, pendingOp);
      if (!Number.isFinite(next)) {
        setAccumulator(null); setPendingOp(null); setJustEvaluated(true);
        return 'Error';
      }
      setAccumulator(next);
      setPendingOp(null);
      setJustEvaluated(true);
      return formatDisplay(String(next));
    });
  }, [accumulator, pendingOp]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const k = e.key;
      if (/^[0-9]$/.test(k))                   { e.preventDefault(); inputDigit(k); return; }
      if (k === '.')                            { e.preventDefault(); inputDecimal(); return; }
      if (k === '+' || k === '-' || k === '*' || k === '/') { e.preventDefault(); chooseOp(k as Op); return; }
      if (k === 'Enter' || k === '=')           { e.preventDefault(); equals(); return; }
      if (k === 'Backspace')                    { e.preventDefault(); backspace(); return; }
      if (k === 'Escape' || k === 'c' || k === 'C') { e.preventDefault(); clearAll(); return; }
      if (k === '%')                            { e.preventDefault(); percent(); return; }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [inputDigit, inputDecimal, chooseOp, equals, backspace, clearAll, percent]);

  const expression = accumulator !== null && pendingOp !== null
    ? `${formatDisplay(String(accumulator))} ${OP_LABEL[pendingOp]}`
    : ' ';

  const Btn = ({
    label, onClick, variant = 'num', wide = false, ariaLabel,
  }: { label: string; onClick: () => void; variant?: 'num' | 'op' | 'fn' | 'eq'; wide?: boolean; ariaLabel?: string; }) => {
    const base = 'h-16 rounded-2xl text-2xl font-medium select-none transition active:scale-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-[__RING__]';
    const styles = {
      num: 'bg-[__SURFACE_2__] hover:bg-[__SURFACE_3__] text-[__FG__]',
      op:  'bg-[__OP_BG__] hover:bg-[__OP_HOVER__] text-[__FG__]',
      fn:  'bg-[__FN_BG__] hover:bg-[__FN_HOVER__] text-[__FN_FG__] font-semibold',
      eq:  'bg-[__PRIMARY__] hover:bg-[__PRIMARY_HOVER__] text-[__PRIMARY_FG__]',
    }[variant];
    return (
      <button
        type="button"
        onClick={onClick}
        aria-label={ariaLabel ?? label}
        className={`${base} ${styles} ${wide ? 'col-span-2' : ''}`}
      >{label}</button>
    );
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[__BG__] p-4">
      <div className="w-full max-w-sm rounded-3xl bg-[__SURFACE__] p-5 shadow-2xl ring-1 ring-[__BORDER__]">
        <div className="mb-4 px-2">
          <div className="text-xs text-[__MUTED_FG__] h-4 text-right">{expression}</div>
          <div
            role="status"
            aria-live="polite"
            aria-label={`Display ${formatDisplay(display)}`}
            className="text-right text-5xl font-light text-[__FG__] tabular-nums truncate"
          >
            {formatDisplay(display)}
          </div>
        </div>
        <div className="grid grid-cols-4 gap-2">
          <Btn label="C"    variant="fn" onClick={clearAll} ariaLabel="Clear" />
          <Btn label="±"   variant="fn" onClick={toggleSign} ariaLabel="Toggle sign" />
          <Btn label="%"    variant="fn" onClick={percent} ariaLabel="Percent" />
          <Btn label={OP_LABEL['/']} variant="op" onClick={() => chooseOp('/')} ariaLabel="Divide" />

          <Btn label="7"    onClick={() => inputDigit('7')} />
          <Btn label="8"    onClick={() => inputDigit('8')} />
          <Btn label="9"    onClick={() => inputDigit('9')} />
          <Btn label={OP_LABEL['*']} variant="op" onClick={() => chooseOp('*')} ariaLabel="Multiply" />

          <Btn label="4"    onClick={() => inputDigit('4')} />
          <Btn label="5"    onClick={() => inputDigit('5')} />
          <Btn label="6"    onClick={() => inputDigit('6')} />
          <Btn label={OP_LABEL['-']} variant="op" onClick={() => chooseOp('-')} ariaLabel="Subtract" />

          <Btn label="1"    onClick={() => inputDigit('1')} />
          <Btn label="2"    onClick={() => inputDigit('2')} />
          <Btn label="3"    onClick={() => inputDigit('3')} />
          <Btn label={OP_LABEL['+']} variant="op" onClick={() => chooseOp('+')} ariaLabel="Add" />

          <Btn label="0" wide onClick={() => inputDigit('0')} />
          <Btn label="."    onClick={inputDecimal} ariaLabel="Decimal" />
          <Btn label="="    variant="eq" onClick={equals} ariaLabel="Equals" />
        </div>
        <p className="mt-4 text-center text-xs text-[__MUTED_FG__]">
          Keyboard: digits, + − × ÷, Enter, Backspace, Esc to clear
        </p>
      </div>
    </div>
  );
}
"""


_TODO_APP_TSX = r"""import { useEffect, useState } from 'react';
import { Check, Trash2, Plus } from 'lucide-react';

type Todo = { id: string; text: string; done: boolean };

const STORAGE_KEY = 'app.todos.v1';

function load(): Todo[] {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); } catch { return []; }
}

export default function App() {
  const [todos, setTodos] = useState<Todo[]>(() => load());
  const [draft, setDraft] = useState('');
  const [filter, setFilter] = useState<'all' | 'active' | 'done'>('all');

  useEffect(() => { localStorage.setItem(STORAGE_KEY, JSON.stringify(todos)); }, [todos]);

  function add() {
    const text = draft.trim();
    if (!text) return;
    setTodos((t) => [{ id: crypto.randomUUID(), text, done: false }, ...t]);
    setDraft('');
  }

  function toggle(id: string) {
    setTodos((t) => t.map((x) => (x.id === id ? { ...x, done: !x.done } : x)));
  }

  function remove(id: string) {
    setTodos((t) => t.filter((x) => x.id !== id));
  }

  function clearDone() {
    setTodos((t) => t.filter((x) => !x.done));
  }

  const filtered = todos.filter((t) =>
    filter === 'all' ? true : filter === 'active' ? !t.done : t.done,
  );
  const remaining = todos.filter((t) => !t.done).length;

  return (
    <div className="min-h-screen flex items-start justify-center bg-[__BG__] p-6">
      <div className="w-full max-w-xl mt-12 rounded-2xl bg-[__SURFACE__] shadow-sm ring-1 ring-[__BORDER__] p-6">
        <h1 className="text-2xl font-semibold text-[__FG__] mb-4">Tasks</h1>

        <form
          onSubmit={(e) => { e.preventDefault(); add(); }}
          className="flex gap-2 mb-4"
        >
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="What needs doing?"
            className="flex-1 rounded-lg border border-[__BORDER__] bg-[__SURFACE__] px-3 py-2 text-sm text-[__FG__] placeholder:text-[__MUTED_FG__] focus:outline-none focus:ring-2 focus:ring-[__RING__]"
          />
          <button
            type="submit"
            className="rounded-lg bg-[__PRIMARY__] px-4 py-2 text-sm font-medium text-[__PRIMARY_FG__] hover:bg-[__PRIMARY_HOVER__] inline-flex items-center gap-1"
          >
            <Plus className="h-4 w-4" /> Add
          </button>
        </form>

        <div className="flex items-center justify-between mb-3 text-sm text-[__MUTED_FG__]">
          <div className="flex gap-1">
            {(['all', 'active', 'done'] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-2 py-1 rounded ${filter === f ? 'bg-[__PRIMARY__] text-[__PRIMARY_FG__]' : 'hover:bg-[__SURFACE_2__]'}`}
              >{f}</button>
            ))}
          </div>
          <span>{remaining} left</span>
        </div>

        <ul className="space-y-1">
          {filtered.length === 0 && (
            <li className="text-sm text-[__MUTED_FG__] py-6 text-center">Nothing here yet.</li>
          )}
          {filtered.map((t) => (
            <li key={t.id} className="flex items-center gap-3 py-2 px-2 rounded hover:bg-[__SURFACE_2__] group">
              <button
                onClick={() => toggle(t.id)}
                aria-label={t.done ? 'Mark active' : 'Mark done'}
                className={`h-5 w-5 rounded border flex items-center justify-center transition ${
                  t.done
                    ? 'bg-[__PRIMARY__] border-[__PRIMARY__] text-[__PRIMARY_FG__]'
                    : 'border-[__BORDER__] hover:border-[__ACCENT__]'
                }`}
              >
                {t.done && <Check className="h-3 w-3" />}
              </button>
              <span className={`flex-1 text-sm ${t.done ? 'line-through text-[__MUTED_FG__]' : 'text-[__FG__]'}`}>
                {t.text}
              </span>
              <button
                onClick={() => remove(t.id)}
                aria-label="Delete"
                className="text-[__MUTED_FG__] hover:text-red-500 opacity-0 group-hover:opacity-100 transition"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>

        {todos.some((t) => t.done) && (
          <button
            onClick={clearDone}
            className="mt-4 text-xs text-[__MUTED_FG__] hover:text-[__FG__]"
          >Clear completed</button>
        )}
      </div>
    </div>
  );
}
"""


_TIMER_APP_TSX = r"""import { useEffect, useRef, useState } from 'react';
import { Play, Pause, RotateCcw } from 'lucide-react';

function fmt(ms: number): string {
  const total = Math.max(0, Math.floor(ms));
  const m = Math.floor(total / 60000);
  const s = Math.floor((total % 60000) / 1000);
  const cs = Math.floor((total % 1000) / 10);
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${String(cs).padStart(2, '0')}`;
}

export default function App() {
  const [elapsed, setElapsed] = useState(0);
  const [running, setRunning] = useState(false);
  const [laps, setLaps] = useState<number[]>([]);
  const startRef = useRef<number>(0);
  const baseRef = useRef<number>(0);

  useEffect(() => {
    if (!running) return;
    startRef.current = performance.now();
    let raf = 0;
    const tick = () => {
      setElapsed(baseRef.current + (performance.now() - startRef.current));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [running]);

  function toggle() {
    if (running) {
      baseRef.current = elapsed;
      setRunning(false);
    } else {
      setRunning(true);
    }
  }

  function reset() {
    setRunning(false);
    setElapsed(0);
    setLaps([]);
    baseRef.current = 0;
  }

  function lap() {
    if (running) setLaps((l) => [elapsed, ...l].slice(0, 50));
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[__BG__] p-6">
      <div className="w-full max-w-md rounded-2xl bg-[__SURFACE__] shadow-sm ring-1 ring-[__BORDER__] p-8">
        <div className="text-center text-6xl font-light tabular-nums tracking-tight text-[__FG__]">
          {fmt(elapsed)}
        </div>
        <div className="mt-6 flex justify-center gap-3">
          <button
            onClick={toggle}
            className="rounded-full bg-[__PRIMARY__] px-6 py-3 text-sm font-medium text-[__PRIMARY_FG__] hover:bg-[__PRIMARY_HOVER__] inline-flex items-center gap-2"
          >
            {running ? <><Pause className="h-4 w-4" />Pause</> : <><Play className="h-4 w-4" />Start</>}
          </button>
          <button
            onClick={lap}
            disabled={!running}
            className="rounded-full bg-[__SURFACE__] px-4 py-3 text-sm font-medium text-[__FG__] ring-1 ring-[__BORDER__] hover:bg-[__SURFACE_2__] disabled:opacity-40"
          >Lap</button>
          <button
            onClick={reset}
            className="rounded-full bg-[__SURFACE__] px-4 py-3 text-sm font-medium text-[__MUTED_FG__] ring-1 ring-[__BORDER__] hover:bg-[__SURFACE_2__] inline-flex items-center gap-1"
          >
            <RotateCcw className="h-4 w-4" /> Reset
          </button>
        </div>
        {laps.length > 0 && (
          <ul className="mt-6 max-h-56 overflow-y-auto divide-y divide-[__BORDER__] text-sm text-[__FG__]">
            {laps.map((l, i) => (
              <li key={i} className="flex justify-between py-2 px-1 tabular-nums">
                <span className="text-[__MUTED_FG__]">#{laps.length - i}</span>
                <span>{fmt(l)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
"""


_NOTES_APP_TSX = r"""import { useEffect, useMemo, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';

type Note = { id: string; title: string; body: string; updated: number };

const STORAGE_KEY = 'app.notes.v1';

function load(): Note[] {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); } catch { return []; }
}

export default function App() {
  const [notes, setNotes] = useState<Note[]>(() => load());
  const [activeId, setActiveId] = useState<string | null>(() => load()[0]?.id ?? null);

  useEffect(() => { localStorage.setItem(STORAGE_KEY, JSON.stringify(notes)); }, [notes]);

  const sorted = useMemo(
    () => [...notes].sort((a, b) => b.updated - a.updated),
    [notes],
  );
  const active = notes.find((n) => n.id === activeId) ?? null;

  function newNote() {
    const n: Note = { id: crypto.randomUUID(), title: 'Untitled', body: '', updated: Date.now() };
    setNotes((xs) => [n, ...xs]);
    setActiveId(n.id);
  }

  function update(id: string, patch: Partial<Note>) {
    setNotes((xs) => xs.map((n) => (n.id === id ? { ...n, ...patch, updated: Date.now() } : n)));
  }

  function remove(id: string) {
    setNotes((xs) => xs.filter((n) => n.id !== id));
    if (activeId === id) setActiveId(null);
  }

  return (
    <div className="min-h-screen flex bg-[__BG__]">
      <aside className="w-64 border-r border-[__BORDER__] bg-[__SURFACE__] flex flex-col">
        <div className="p-3 border-b border-[__BORDER__] flex items-center justify-between">
          <h1 className="font-semibold text-[__FG__]">Notes</h1>
          <button
            onClick={newNote}
            aria-label="New note"
            className="rounded-md bg-[__PRIMARY__] p-1.5 text-[__PRIMARY_FG__] hover:bg-[__PRIMARY_HOVER__]"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>
        <ul className="flex-1 overflow-y-auto">
          {sorted.length === 0 && (
            <li className="p-4 text-sm text-[__MUTED_FG__]">No notes yet.</li>
          )}
          {sorted.map((n) => (
            <li
              key={n.id}
              onClick={() => setActiveId(n.id)}
              className={`cursor-pointer border-b border-[__BORDER__] px-3 py-2 ${
                n.id === activeId ? 'bg-[__SURFACE_2__]' : 'hover:bg-[__SURFACE_2__]'
              }`}
            >
              <div className="text-sm font-medium text-[__FG__] truncate">{n.title || 'Untitled'}</div>
              <div className="text-xs text-[__MUTED_FG__] truncate">{n.body.slice(0, 60) || 'Empty'}</div>
            </li>
          ))}
        </ul>
      </aside>

      <main className="flex-1 flex flex-col">
        {active ? (
          <>
            <div className="flex items-center justify-between border-b border-[__BORDER__] bg-[__SURFACE__] px-4 py-2">
              <input
                value={active.title}
                onChange={(e) => update(active.id, { title: e.target.value })}
                className="flex-1 bg-transparent text-base font-semibold text-[__FG__] focus:outline-none"
              />
              <button
                onClick={() => remove(active.id)}
                aria-label="Delete"
                className="text-[__MUTED_FG__] hover:text-red-500"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
            <textarea
              value={active.body}
              onChange={(e) => update(active.id, { body: e.target.value })}
              placeholder="Start typing..."
              className="flex-1 resize-none bg-transparent p-4 text-sm text-[__FG__] placeholder:text-[__MUTED_FG__] focus:outline-none"
            />
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-sm text-[__MUTED_FG__]">
            Select or create a note.
          </div>
        )}
      </main>
    </div>
  );
}
"""


# ---------------------------------------------------------------------------
# Game templates — playable, not landing pages
# ---------------------------------------------------------------------------

_SNAKE_APP_TSX = r"""import { useEffect, useRef, useState, useCallback } from 'react';
import { Play, Pause, RotateCcw } from 'lucide-react';

const COLS = 24;
const ROWS = 24;
const CELL = 18;
const TICK_MS = 110;

type Pt = { x: number; y: number };
type Dir = 'up' | 'down' | 'left' | 'right';

const VECT: Record<Dir, Pt> = {
  up:    { x:  0, y: -1 },
  down:  { x:  0, y:  1 },
  left:  { x: -1, y:  0 },
  right: { x:  1, y:  0 },
};

const OPP: Record<Dir, Dir> = { up: 'down', down: 'up', left: 'right', right: 'left' };

function randCell(occupied: Pt[]): Pt {
  for (let i = 0; i < 256; i++) {
    const p = { x: Math.floor(Math.random() * COLS), y: Math.floor(Math.random() * ROWS) };
    if (!occupied.some((q) => q.x === p.x && q.y === p.y)) return p;
  }
  return { x: 0, y: 0 };
}

export default function App() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [snake, setSnake] = useState<Pt[]>(() => [{ x: 12, y: 12 }, { x: 11, y: 12 }, { x: 10, y: 12 }]);
  const [food, setFood] = useState<Pt>(() => ({ x: 17, y: 12 }));
  const [dir, setDir] = useState<Dir>('right');
  const [pendingDir, setPendingDir] = useState<Dir>('right');
  const [score, setScore] = useState(0);
  const [best, setBest] = useState<number>(() => Number(localStorage.getItem('snake.best') || 0));
  const [running, setRunning] = useState(true);
  const [over, setOver] = useState(false);

  const reset = useCallback(() => {
    setSnake([{ x: 12, y: 12 }, { x: 11, y: 12 }, { x: 10, y: 12 }]);
    setFood({ x: 17, y: 12 });
    setDir('right');
    setPendingDir('right');
    setScore(0);
    setRunning(true);
    setOver(false);
  }, []);

  // Tick
  useEffect(() => {
    if (!running || over) return;
    const id = window.setInterval(() => {
      setSnake((prev) => {
        const d = pendingDir;
        setDir(d);
        const head = prev[0];
        const next = { x: head.x + VECT[d].x, y: head.y + VECT[d].y };
        if (next.x < 0 || next.x >= COLS || next.y < 0 || next.y >= ROWS) {
          setOver(true); setRunning(false); return prev;
        }
        if (prev.some((p) => p.x === next.x && p.y === next.y)) {
          setOver(true); setRunning(false); return prev;
        }
        const ate = next.x === food.x && next.y === food.y;
        const grown = ate ? [next, ...prev] : [next, ...prev.slice(0, -1)];
        if (ate) {
          setScore((s) => {
            const ns = s + 1;
            setBest((b) => {
              const nb = Math.max(b, ns);
              localStorage.setItem('snake.best', String(nb));
              return nb;
            });
            return ns;
          });
          setFood(randCell(grown));
        }
        return grown;
      });
    }, TICK_MS);
    return () => window.clearInterval(id);
  }, [running, over, pendingDir, food]);

  // Input
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const k = e.key.toLowerCase();
      const map: Record<string, Dir> = {
        arrowup: 'up', w: 'up',
        arrowdown: 'down', s: 'down',
        arrowleft: 'left', a: 'left',
        arrowright: 'right', d: 'right',
      };
      const wanted = map[k];
      if (wanted) {
        e.preventDefault();
        if (OPP[wanted] !== dir) setPendingDir(wanted);
        return;
      }
      if (k === ' ') { e.preventDefault(); setRunning((r) => !r); return; }
      if (k === 'r') { e.preventDefault(); reset(); return; }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [dir, reset]);

  // Render
  useEffect(() => {
    const c = canvasRef.current; if (!c) return;
    const ctx = c.getContext('2d'); if (!ctx) return;
    ctx.fillStyle = '__BG__'; ctx.fillRect(0, 0, c.width, c.height);
    // grid hairlines
    ctx.strokeStyle = '__BORDER__'; ctx.lineWidth = 1;
    for (let x = 0; x <= COLS; x++) { ctx.beginPath(); ctx.moveTo(x * CELL + 0.5, 0); ctx.lineTo(x * CELL + 0.5, ROWS * CELL); ctx.stroke(); }
    for (let y = 0; y <= ROWS; y++) { ctx.beginPath(); ctx.moveTo(0, y * CELL + 0.5); ctx.lineTo(COLS * CELL, y * CELL + 0.5); ctx.stroke(); }
    // food
    ctx.fillStyle = '__ACCENT__';
    ctx.beginPath();
    ctx.arc(food.x * CELL + CELL / 2, food.y * CELL + CELL / 2, CELL / 2 - 2, 0, Math.PI * 2);
    ctx.fill();
    // snake
    snake.forEach((p, i) => {
      ctx.fillStyle = i === 0 ? '__PRIMARY__' : '__PRIMARY_HOVER__';
      ctx.fillRect(p.x * CELL + 2, p.y * CELL + 2, CELL - 4, CELL - 4);
    });
  }, [snake, food]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-[__BG__] p-4">
      <div className="rounded-2xl bg-[__SURFACE__] p-4 ring-1 ring-[__BORDER__] shadow-2xl">
        <div className="mb-3 flex items-center justify-between gap-6 text-sm">
          <div className="text-[__FG__] font-semibold">Snake</div>
          <div className="flex gap-4 tabular-nums text-[__MUTED_FG__]">
            <span>Score: <span className="text-[__FG__] font-semibold">{score}</span></span>
            <span>Best: <span className="text-[__FG__] font-semibold">{best}</span></span>
          </div>
        </div>
        <div className="relative" style={{ width: COLS * CELL, height: ROWS * CELL }}>
          <canvas
            ref={canvasRef}
            width={COLS * CELL}
            height={ROWS * CELL}
            className="rounded-lg block"
          />
          {over && (
            <div className="absolute inset-0 flex flex-col items-center justify-center rounded-lg bg-[__BG__]/85 backdrop-blur-sm">
              <div className="text-2xl font-semibold text-[__FG__] mb-1">Game over</div>
              <div className="text-sm text-[__MUTED_FG__] mb-4">Score {score} · Best {best}</div>
              <button
                onClick={reset}
                className="rounded-full bg-[__PRIMARY__] px-5 py-2 text-sm font-medium text-[__PRIMARY_FG__] hover:bg-[__PRIMARY_HOVER__] inline-flex items-center gap-2"
              ><RotateCcw className="h-4 w-4" /> Restart</button>
            </div>
          )}
        </div>
        <div className="mt-3 flex items-center justify-between gap-2 text-xs text-[__MUTED_FG__]">
          <span>Arrow keys / WASD · Space pause · R restart</span>
          <div className="flex gap-2">
            <button
              onClick={() => setRunning((r) => !r)}
              disabled={over}
              className="rounded-md bg-[__SURFACE_2__] px-2 py-1 text-[__FG__] hover:bg-[__SURFACE_3__] disabled:opacity-40 inline-flex items-center gap-1"
            >
              {running ? <><Pause className="h-3 w-3" />Pause</> : <><Play className="h-3 w-3" />Play</>}
            </button>
            <button
              onClick={reset}
              className="rounded-md bg-[__SURFACE_2__] px-2 py-1 text-[__FG__] hover:bg-[__SURFACE_3__] inline-flex items-center gap-1"
            ><RotateCcw className="h-3 w-3" /> Reset</button>
          </div>
        </div>
      </div>
    </div>
  );
}
"""


_TICTACTOE_APP_TSX = r"""import { useMemo, useState } from 'react';
import { RotateCcw } from 'lucide-react';

type Mark = 'X' | 'O' | null;
const LINES = [
  [0,1,2], [3,4,5], [6,7,8],
  [0,3,6], [1,4,7], [2,5,8],
  [0,4,8], [2,4,6],
];

function winner(board: Mark[]): { mark: Mark; line: number[] } | null {
  for (const line of LINES) {
    const [a, b, c] = line;
    if (board[a] && board[a] === board[b] && board[a] === board[c]) {
      return { mark: board[a], line };
    }
  }
  return null;
}

export default function App() {
  const [board, setBoard] = useState<Mark[]>(() => Array(9).fill(null));
  const [turn, setTurn] = useState<'X' | 'O'>('X');
  const [scores, setScores] = useState({ X: 0, O: 0, draws: 0 });

  const result = winner(board);
  const isDraw = !result && board.every(Boolean);
  const finished = !!result || isDraw;

  function play(i: number) {
    if (finished || board[i]) return;
    const next = board.slice();
    next[i] = turn;
    setBoard(next);
    const w = winner(next);
    if (w?.mark) {
      setScores((s) => ({ ...s, [w.mark as 'X' | 'O']: s[w.mark as 'X' | 'O'] + 1 }));
    } else if (next.every(Boolean)) {
      setScores((s) => ({ ...s, draws: s.draws + 1 }));
    } else {
      setTurn(turn === 'X' ? 'O' : 'X');
    }
  }

  function reset() {
    setBoard(Array(9).fill(null));
    setTurn('X');
  }

  function newMatch() {
    reset();
    setScores({ X: 0, O: 0, draws: 0 });
  }

  const status = useMemo(() => {
    if (result?.mark) return `${result.mark} wins`;
    if (isDraw) return 'Draw';
    return `${turn} to play`;
  }, [result, isDraw, turn]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-[__BG__] p-4">
      <div className="w-full max-w-sm rounded-2xl bg-[__SURFACE__] p-6 ring-1 ring-[__BORDER__] shadow-2xl">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-lg font-semibold text-[__FG__]">Tic Tac Toe</h1>
          <button
            onClick={newMatch}
            className="rounded-md bg-[__SURFACE_2__] px-2 py-1 text-xs text-[__FG__] hover:bg-[__SURFACE_3__] inline-flex items-center gap-1"
          ><RotateCcw className="h-3 w-3" /> New match</button>
        </div>

        <div className="grid grid-cols-3 gap-2 mb-4">
          {board.map((cell, i) => {
            const inLine = result?.line.includes(i);
            const isX = cell === 'X';
            const isO = cell === 'O';
            return (
              <button
                key={i}
                onClick={() => play(i)}
                disabled={!!cell || finished}
                aria-label={`Cell ${i + 1}`}
                className={[
                  'aspect-square rounded-xl text-5xl font-semibold transition select-none',
                  'bg-[__SURFACE_2__] hover:bg-[__SURFACE_3__]',
                  'disabled:cursor-not-allowed',
                  inLine ? 'ring-2 ring-[__ACCENT__]' : '',
                  isX ? 'text-[__PRIMARY__]' : isO ? 'text-[__ACCENT__]' : 'text-[__FG__]',
                ].join(' ')}
              >{cell ?? ''}</button>
            );
          })}
        </div>

        <div className="flex items-center justify-between text-sm">
          <span className="text-[__FG__] font-medium">{status}</span>
          <button
            onClick={reset}
            disabled={!board.some(Boolean)}
            className="text-xs text-[__MUTED_FG__] hover:text-[__FG__] disabled:opacity-40"
          >Reset board</button>
        </div>

        <div className="mt-4 grid grid-cols-3 gap-2 text-center text-xs">
          <div className="rounded-lg bg-[__SURFACE_2__] py-2">
            <div className="text-[__PRIMARY__] font-semibold text-base">{scores.X}</div>
            <div className="text-[__MUTED_FG__]">X</div>
          </div>
          <div className="rounded-lg bg-[__SURFACE_2__] py-2">
            <div className="text-[__FG__] font-semibold text-base">{scores.draws}</div>
            <div className="text-[__MUTED_FG__]">Draws</div>
          </div>
          <div className="rounded-lg bg-[__SURFACE_2__] py-2">
            <div className="text-[__ACCENT__] font-semibold text-base">{scores.O}</div>
            <div className="text-[__MUTED_FG__]">O</div>
          </div>
        </div>
      </div>
    </div>
  );
}
"""


_PONG_APP_TSX = r"""import { useEffect, useRef, useState, useCallback } from 'react';
import { Play, Pause, RotateCcw } from 'lucide-react';

const W = 640;
const H = 380;
const PADDLE_W = 10;
const PADDLE_H = 70;
const BALL_R = 7;
const PADDLE_SPEED = 6;
const AI_SPEED = 4.2;

export default function App() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stateRef = useRef({
    py: H / 2 - PADDLE_H / 2,
    ay: H / 2 - PADDLE_H / 2,
    bx: W / 2,
    by: H / 2,
    bvx: 4,
    bvy: 2,
    keys: { up: false, down: false } as { up: boolean; down: boolean },
  });
  const [scores, setScores] = useState({ p: 0, a: 0 });
  const [running, setRunning] = useState(true);
  const [winner, setWinner] = useState<null | 'You' | 'AI'>(null);

  const serve = useCallback((dir: 1 | -1) => {
    const s = stateRef.current;
    s.bx = W / 2; s.by = H / 2;
    s.bvx = 4 * dir;
    s.bvy = (Math.random() * 4 - 2) || 2;
  }, []);

  const reset = useCallback(() => {
    setScores({ p: 0, a: 0 });
    setWinner(null);
    setRunning(true);
    serve(Math.random() < 0.5 ? 1 : -1);
  }, [serve]);

  // Input
  useEffect(() => {
    function onDown(e: KeyboardEvent) {
      const k = e.key.toLowerCase();
      if (k === 'arrowup' || k === 'w')   { stateRef.current.keys.up = true;   e.preventDefault(); }
      if (k === 'arrowdown' || k === 's') { stateRef.current.keys.down = true; e.preventDefault(); }
      if (k === ' ')                       { setRunning((r) => !r); e.preventDefault(); }
      if (k === 'r')                       { reset(); e.preventDefault(); }
    }
    function onUp(e: KeyboardEvent) {
      const k = e.key.toLowerCase();
      if (k === 'arrowup' || k === 'w')   stateRef.current.keys.up = false;
      if (k === 'arrowdown' || k === 's') stateRef.current.keys.down = false;
    }
    window.addEventListener('keydown', onDown);
    window.addEventListener('keyup', onUp);
    return () => {
      window.removeEventListener('keydown', onDown);
      window.removeEventListener('keyup', onUp);
    };
  }, [reset]);

  // Mouse control (canvas Y -> player paddle)
  useEffect(() => {
    const c = canvasRef.current; if (!c) return;
    function onMove(e: MouseEvent) {
      const c = canvasRef.current; if (!c) return;
      const r = c.getBoundingClientRect();
      const y = ((e.clientY - r.top) / r.height) * H - PADDLE_H / 2;
      stateRef.current.py = Math.max(0, Math.min(H - PADDLE_H, y));
    }
    c.addEventListener('mousemove', onMove);
    return () => c.removeEventListener('mousemove', onMove);
  }, []);

  // Main loop
  useEffect(() => {
    let raf = 0;
    function draw() {
      const c = canvasRef.current; if (!c) { raf = requestAnimationFrame(draw); return; }
      const ctx = c.getContext('2d'); if (!ctx) return;
      const s = stateRef.current;

      if (running && !winner) {
        if (s.keys.up)   s.py = Math.max(0, s.py - PADDLE_SPEED);
        if (s.keys.down) s.py = Math.min(H - PADDLE_H, s.py + PADDLE_SPEED);
        // AI: ease toward ball
        const target = s.by - PADDLE_H / 2;
        if (target < s.ay) s.ay = Math.max(0, s.ay - AI_SPEED);
        if (target > s.ay) s.ay = Math.min(H - PADDLE_H, s.ay + AI_SPEED);
        // Ball
        s.bx += s.bvx; s.by += s.bvy;
        if (s.by < BALL_R) { s.by = BALL_R; s.bvy *= -1; }
        if (s.by > H - BALL_R) { s.by = H - BALL_R; s.bvy *= -1; }
        // Paddle collisions
        if (s.bx - BALL_R < PADDLE_W && s.by > s.py && s.by < s.py + PADDLE_H && s.bvx < 0) {
          s.bvx = -s.bvx * 1.05;
          s.bvy += ((s.by - (s.py + PADDLE_H / 2)) / (PADDLE_H / 2)) * 2;
        }
        if (s.bx + BALL_R > W - PADDLE_W && s.by > s.ay && s.by < s.ay + PADDLE_H && s.bvx > 0) {
          s.bvx = -s.bvx * 1.05;
          s.bvy += ((s.by - (s.ay + PADDLE_H / 2)) / (PADDLE_H / 2)) * 2;
        }
        // Score
        if (s.bx < -10) {
          setScores((sc) => {
            const next = { ...sc, a: sc.a + 1 };
            if (next.a >= 7) setWinner('AI');
            return next;
          });
          serve(1);
        } else if (s.bx > W + 10) {
          setScores((sc) => {
            const next = { ...sc, p: sc.p + 1 };
            if (next.p >= 7) setWinner('You');
            return next;
          });
          serve(-1);
        }
      }

      // Render
      ctx.fillStyle = '__BG__';      ctx.fillRect(0, 0, W, H);
      ctx.strokeStyle = '__BORDER__'; ctx.setLineDash([6, 8]);
      ctx.beginPath(); ctx.moveTo(W / 2, 0); ctx.lineTo(W / 2, H); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = '__PRIMARY__'; ctx.fillRect(0, s.py, PADDLE_W, PADDLE_H);
      ctx.fillStyle = '__ACCENT__';  ctx.fillRect(W - PADDLE_W, s.ay, PADDLE_W, PADDLE_H);
      ctx.fillStyle = '__FG__';
      ctx.beginPath(); ctx.arc(s.bx, s.by, BALL_R, 0, Math.PI * 2); ctx.fill();

      raf = requestAnimationFrame(draw);
    }
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [running, winner, serve]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-[__BG__] p-4">
      <div className="rounded-2xl bg-[__SURFACE__] p-4 ring-1 ring-[__BORDER__] shadow-2xl">
        <div className="mb-3 flex items-center justify-between gap-6 text-sm">
          <div className="text-[__FG__] font-semibold">Pong</div>
          <div className="flex gap-4 tabular-nums text-[__MUTED_FG__]">
            <span>You: <span className="text-[__PRIMARY__] font-semibold">{scores.p}</span></span>
            <span>AI:  <span className="text-[__ACCENT__] font-semibold">{scores.a}</span></span>
            <span className="text-[__MUTED_FG__]">first to 7</span>
          </div>
        </div>
        <div className="relative" style={{ width: W, height: H }}>
          <canvas ref={canvasRef} width={W} height={H} className="rounded-lg block cursor-none" />
          {winner && (
            <div className="absolute inset-0 flex flex-col items-center justify-center rounded-lg bg-[__BG__]/85 backdrop-blur-sm">
              <div className="text-2xl font-semibold text-[__FG__] mb-1">{winner === 'You' ? 'You win' : 'AI wins'}</div>
              <div className="text-sm text-[__MUTED_FG__] mb-4">{scores.p} — {scores.a}</div>
              <button
                onClick={reset}
                className="rounded-full bg-[__PRIMARY__] px-5 py-2 text-sm font-medium text-[__PRIMARY_FG__] hover:bg-[__PRIMARY_HOVER__] inline-flex items-center gap-2"
              ><RotateCcw className="h-4 w-4" /> Rematch</button>
            </div>
          )}
        </div>
        <div className="mt-3 flex items-center justify-between gap-2 text-xs text-[__MUTED_FG__]">
          <span>Mouse or ↑↓ / W S · Space pause · R rematch</span>
          <div className="flex gap-2">
            <button
              onClick={() => setRunning((r) => !r)}
              disabled={!!winner}
              className="rounded-md bg-[__SURFACE_2__] px-2 py-1 text-[__FG__] hover:bg-[__SURFACE_3__] disabled:opacity-40 inline-flex items-center gap-1"
            >
              {running ? <><Pause className="h-3 w-3" />Pause</> : <><Play className="h-3 w-3" />Play</>}
            </button>
            <button
              onClick={reset}
              className="rounded-md bg-[__SURFACE_2__] px-2 py-1 text-[__FG__] hover:bg-[__SURFACE_3__] inline-flex items-center gap-1"
            ><RotateCcw className="h-3 w-3" /> Reset</button>
          </div>
        </div>
      </div>
    </div>
  );
}
"""


# ---------------------------------------------------------------------------
# String helpers
# ---------------------------------------------------------------------------

def _slugify(s: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "-" for c in s).strip("-")
    while "--" in out:
        out = out.replace("--", "-")
    return out


def _escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )
_SUDOKU_APP_TSX = r"""
import { useState } from 'react';

const initialBoard = [
  [5,3,'', '',7,'', '', '', ''],
  [6,'','', 1,9,5, '', '', ''],
  ['',9,8, '', '', '', '',6,''],

  [8,'','', '',6,'', '', '',3],
  [4,'','', 8,'',3, '', '',1],
  [7,'','', '',2,'', '', '',6],

  ['',6,'', '', '', '', 2,8,''],
  ['', '', '', 4,1,9, '', '',5],
  ['', '', '', '',8,'', '',7,9]
];

export default function App() {
  const [board, setBoard] = useState(initialBoard);

  const handleChange = (row: number, col: number, value: string) => {
    if (!/^[1-9]?$/.test(value)) return;

    const updated = board.map(r => [...r]);
    updated[row][col] = value === '' ? '' : Number(value);

    setBoard(updated);
  };

  return (
    <div className="min-h-screen bg-[#111] text-white flex flex-col items-center justify-center p-6">
      <h1 className="text-4xl font-bold mb-6">Sudoku</h1>

      <div className="grid grid-cols-9 gap-[2px] bg-white p-[2px]">
        {board.map((row, rowIndex) =>
          row.map((cell, colIndex) => (
            <input
              key={`${rowIndex}-${colIndex}`}
              value={cell}
              onChange={(e) =>
                handleChange(rowIndex, colIndex, e.target.value)
              }
              className="w-12 h-12 text-center text-xl bg-[#222] border border-gray-700"
              maxLength={1}
            />
          ))
        )}
      </div>
    </div>
  );
}
"""
_FUNCTIONAL_APP_PROMPT = r"""
Build a REAL interactive React application.

Requirements:
- DO NOT generate a landing page
- DO NOT generate testimonials
- DO NOT generate pricing sections
- DO NOT generate marketing sections
- Focus ONLY on functionality

The app must:
- be fully interactive
- use React state
- have working logic
- use modern Tailwind UI
- be responsive
- support keyboard/mouse interaction where appropriate

Structure:
- create reusable components
- separate logic cleanly
- avoid giant monolithic code where possible

Examples:
- games
- dashboards
- tools
- trackers
- CRUD apps
- editors
- productivity apps

Generate REAL functionality.
"""