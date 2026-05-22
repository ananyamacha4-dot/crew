"""App-type registry — the spine of the prompt router.

The Brief agent classifies a user request into one of these app types. The
manager then routes to a category-specific engineer prompt that ENFORCES the
right structure (no "testimonials" on a game, no "hero" on a dashboard).

Each entry defines:
  - label              human-readable name
  - description        what this category IS, used by the classifier
  - primary_layout     one-liner the engineer reads to know the shell
  - primary_screen_goal default goal the screen must accomplish
  - required_blocks    UI blocks the engineer MUST include
  - forbidden_blocks   UI blocks the engineer MUST NOT include
  - engineer_directive the category-specific system prompt injected into codegen
"""

from __future__ import annotations

from typing import Literal

AppType = Literal[
    "landing",
    "dashboard",
    "game",
    "portfolio",
    "ecommerce",
    "admin",
    "chat",
    "productivity",
    "tool",
    "mobile-app",
    "editor",
    "social",
]

ALL_APP_TYPES: list[AppType] = [
    "landing",
    "dashboard",
    "game",
    "portfolio",
    "ecommerce",
    "admin",
    "chat",
    "productivity",
    "tool",
    "mobile-app",
    "editor",
    "social",
]


APP_TYPE_REGISTRY: dict[str, dict] = {
    # -----------------------------------------------------------------
    "landing": {
        "label": "Marketing landing page",
        "description": (
            "A marketing site whose job is to convert a visitor. Hero, features, "
            "social proof, pricing, FAQ, CTA, footer. Examples: 'a landing page "
            "for a coffee shop', 'thrift store website for kids costumes', "
            "'product launch site for an AI assistant'."
        ),
        "primary_layout": "hero -> features -> testimonials -> pricing -> faq -> cta -> footer",
        "primary_screen_goal": "Convert a visitor by communicating the value prop and providing a clear CTA.",
        "required_blocks": ["hero", "features-grid", "cta-band", "footer"],
        "forbidden_blocks": [
            "sidebar-nav", "topbar-app", "stat-cards", "data-table",
            "chart-panel", "chat-window", "game-canvas",
        ],
        "engineer_directive": (
            "Build a marketing landing page. Use the standard sections from the "
            "ContentPack (hero, features, testimonials, pricing, faq, cta-band, "
            "footer). Mobile-first responsive. No app-shell elements."
        ),
    },

    # -----------------------------------------------------------------
    "dashboard": {
        "label": "Data dashboard",
        "description": (
            "An app shell that shows data at a glance. Left sidebar + topbar + "
            "main area with stat cards, charts, and tables. Examples: 'sales "
            "dashboard', 'analytics for my SaaS', 'admin overview', 'crypto "
            "portfolio tracker'."
        ),
        "primary_layout": "sidebar nav | topbar | stat-cards row | chart panel | data table",
        "primary_screen_goal": "Show key metrics at a glance, drillable into a detail table.",
        "required_blocks": ["sidebar-nav", "topbar", "stat-cards", "chart-panel", "data-table"],
        "forbidden_blocks": [
            "hero", "features-grid", "testimonials", "pricing-table", "faq",
            "cta-band", "newsletter", "blog-grid",
        ],
        "engineer_directive": (
            "Build a DATA DASHBOARD app shell. Single page, no router needed. "
            "Left sidebar (4-6 nav items, current page highlighted). Topbar with "
            "page title + user avatar. Main area: 3-4 stat cards in a row "
            "(label, value, delta % with up/down icon), then ONE chart panel "
            "(use plain SVG bars/lines — no chart libraries), then a data table "
            "(8-12 rows of REALISTIC sample data: order ids, names, status badges, "
            "amounts, dates). Status badges use semantic colors. Make rows "
            "hoverable. NO hero, NO marketing copy, NO testimonials, NO pricing."
        ),
    },

    # -----------------------------------------------------------------
    "game": {
        "label": "Browser game",
        "description": (
            "An interactive game playable in the browser. Examples: 'snake "
            "game', '2048', 'tetris', 'tic tac toe', 'memory match', 'whack "
            "a mole', 'pong'."
        ),
        "primary_layout": "centered game canvas + score + controls + restart",
        "primary_screen_goal": "Playable game from page load — no menus blocking play.",
        "required_blocks": ["game-canvas", "score-display", "restart-button"],
        "forbidden_blocks": [
            "hero", "features-grid", "testimonials", "pricing-table", "faq",
            "cta-band", "footer", "newsletter", "blog-grid", "sidebar-nav",
        ],
        "engineer_directive": (
            "Build a WORKING BROWSER GAME in a single React file. Game must be "
            "playable immediately on page load — no splash screen, no marketing. "
            "State management: useState for board/score/gameOver. Game loop: "
            "useEffect + setInterval (cleanup on unmount) OR requestAnimationFrame. "
            "Keyboard input: useEffect + window.addEventListener('keydown'), "
            "remove listener on cleanup. Show score in a corner. Show 'Game Over' "
            "overlay with restart button when applicable. Use Tailwind grid for the "
            "board if cell-based. NO landing page elements. NO testimonials. "
            "NO pricing. NO marketing copy of any kind."
        ),
    },

    # -----------------------------------------------------------------
    "portfolio": {
        "label": "Personal portfolio",
        "description": (
            "A personal portfolio site — bio, project showcase, skills, contact. "
            "Examples: 'portfolio for a designer', 'developer portfolio', "
            "'photographer portfolio'."
        ),
        "primary_layout": "intro/bio -> project grid -> skills -> contact",
        "primary_screen_goal": "Showcase work and let visitors get in touch.",
        "required_blocks": ["bio-intro", "project-grid", "contact-block"],
        "forbidden_blocks": [
            "pricing-table", "testimonials", "sidebar-nav", "stat-cards",
            "data-table", "chart-panel", "newsletter",
        ],
        "engineer_directive": (
            "Build a PERSONAL PORTFOLIO. Top: a bold intro with name, role, and "
            "one-sentence pitch. Then a grid of 4-6 project cards (image "
            "placeholder, title, short description, tech tags, link). Then a "
            "skills section (chips/badges). Then a contact section (email + "
            "social links — wire onClick to toast or window.location). Use "
            "subtle motion on hover. NO pricing. NO testimonials. NO faq."
        ),
    },

    # -----------------------------------------------------------------
    "ecommerce": {
        "label": "Ecommerce storefront",
        "description": (
            "A product listing / store. Examples: 'sneaker store', 'art prints "
            "shop', 'plant store with cart'."
        ),
        "primary_layout": "filters sidebar | product grid + cart drawer",
        "primary_screen_goal": "Browse products, add to cart.",
        "required_blocks": ["product-grid", "cart-drawer", "filters"],
        "forbidden_blocks": [
            "testimonials", "blog-grid", "stat-cards", "chart-panel",
            "data-table", "newsletter",
        ],
        "engineer_directive": (
            "Build an ECOMMERCE storefront. Topbar with brand + cart icon (badge "
            "shows count). Optional left filters (category, price). Main: grid "
            "of 8-12 product cards (image placeholder, name, price, 'Add to "
            "cart' button). Cart drawer slides in from right when icon clicked, "
            "shows added items with quantity +/- and remove, total. Use useState "
            "for cart, items dictionary. NO marketing hero. NO testimonials. "
            "NO pricing tiers."
        ),
    },

    # -----------------------------------------------------------------
    "admin": {
        "label": "Admin panel",
        "description": (
            "An internal-tool admin shell with tables, filters, CRUD. Examples: "
            "'user management panel', 'order admin', 'CMS admin'."
        ),
        "primary_layout": "sidebar nav | topbar | filters + data table + row actions",
        "primary_screen_goal": "List, filter, and act on records.",
        "required_blocks": ["sidebar-nav", "data-table", "row-actions", "filters"],
        "forbidden_blocks": [
            "hero", "features-grid", "testimonials", "pricing-table", "faq",
            "cta-band", "blog-grid", "newsletter",
        ],
        "engineer_directive": (
            "Build an ADMIN PANEL. Left sidebar (5-7 sections like Users, Orders, "
            "Products, Settings — current page active). Topbar with breadcrumb + "
            "search. Main: filter bar (search input, status dropdown, date range), "
            "then a data table with 10-15 rows of realistic records (id, name, "
            "status badge, role/category, last-active date, row actions menu "
            "with Edit/Delete). Selection checkboxes + bulk action bar. NO "
            "landing page elements at all."
        ),
    },

    # -----------------------------------------------------------------
    "chat": {
        "label": "Chat / messaging",
        "description": (
            "A real-time-feeling chat interface. Examples: 'team chat app', "
            "'whatsapp clone', 'discord-style chat'."
        ),
        "primary_layout": "conversations sidebar | message thread | input bar",
        "primary_screen_goal": "Read messages and reply.",
        "required_blocks": ["conversations-sidebar", "message-thread", "input-bar"],
        "forbidden_blocks": [
            "hero", "features-grid", "testimonials", "pricing-table", "faq",
            "cta-band", "blog-grid",
        ],
        "engineer_directive": (
            "Build a CHAT INTERFACE. Three columns on desktop: left sidebar "
            "(conversation list, ~6 entries with avatar, name, last-message "
            "preview, time, unread badge), middle (message thread with bubbles "
            "left/right based on sender, timestamps, ~12 sample messages between "
            "two users), right (optional contact info panel — or skip). Bottom "
            "of middle: input bar with placeholder, send button. useState for "
            "messages, append on send. Use scroll-to-bottom on new message. "
            "NO landing-page elements."
        ),
    },

    # -----------------------------------------------------------------
    "productivity": {
        "label": "Productivity app",
        "description": (
            "A todo / kanban / notes / habit-tracker style app. Examples: 'todo "
            "list', 'kanban board', 'pomodoro timer', 'habit tracker'."
        ),
        "primary_layout": "task list or kanban columns + add input",
        "primary_screen_goal": "Add, organize, and complete tasks.",
        "required_blocks": ["task-list-or-board", "add-input"],
        "forbidden_blocks": [
            "hero", "testimonials", "pricing-table", "faq", "cta-band",
            "blog-grid", "newsletter",
        ],
        "engineer_directive": (
            "Build a PRODUCTIVITY APP. Single screen. Title at top. If a kanban: "
            "3-4 columns (To do, In progress, Done), draggable cards (or "
            "click-to-move buttons if drag is too complex). If a list: add input "
            "at top, list of items with checkbox + delete, filter chips (All / "
            "Active / Done). useState for items array. NO hero, NO testimonials, "
            "NO marketing."
        ),
    },

    # -----------------------------------------------------------------
    "tool": {
        "label": "Single-purpose utility tool",
        "description": (
            "A focused utility that does ONE thing. Examples: 'calculator', "
            "'unit converter', 'color picker', 'json formatter', 'qr generator', "
            "'password generator', 'markdown previewer'."
        ),
        "primary_layout": "centered tool UI — input + output + controls",
        "primary_screen_goal": "Let the user perform the tool's function immediately.",
        "required_blocks": ["tool-ui"],
        "forbidden_blocks": [
            "hero", "features-grid", "testimonials", "pricing-table", "faq",
            "cta-band", "blog-grid", "newsletter", "footer",
        ],
        "engineer_directive": (
            "Build a SINGLE-PURPOSE UTILITY TOOL. The tool's UI is the page — "
            "there is NO marketing wrapper. Center the tool with reasonable max "
            "width (e.g., max-w-md or max-w-2xl). Tool must be FULLY FUNCTIONAL: "
            "if calculator → working button grid + display + operations + memory; "
            "if converter → input field + unit dropdowns + live result; if color "
            "picker → sliders + hex output + copy button. State via useState. "
            "NO testimonials. NO pricing. NO landing-page elements. NO 'features' "
            "section. Just the tool."
        ),
    },

    # -----------------------------------------------------------------
    "mobile-app": {
        "label": "Mobile-style UI",
        "description": (
            "A phone-shaped UI showing a mobile app. Examples: 'instagram clone', "
            "'banking app UI', 'fitness tracker app'."
        ),
        "primary_layout": "phone frame (centered, ~390px wide) with status bar + content + bottom tab bar",
        "primary_screen_goal": "Show a mobile app screen at phone size.",
        "required_blocks": ["phone-frame", "status-bar", "bottom-tab-bar"],
        "forbidden_blocks": [
            "hero", "testimonials", "pricing-table", "faq", "cta-band",
            "blog-grid", "newsletter", "sidebar-nav",
        ],
        "engineer_directive": (
            "Build a MOBILE-STYLE UI inside a phone frame. Outer container: "
            "centered, max-w-[390px] (iPhone size), rounded-[2.5rem] border with "
            "thick bezel, mx-auto, my-8. Inside: fake status bar (9:41, signal, "
            "battery), then a tab-based content area (use useState for active "
            "tab), then bottom tab bar with 4-5 icons. Content depends on app "
            "(feed cards, profile, transactions, etc.) NO desktop landing-page "
            "elements."
        ),
    },

    # -----------------------------------------------------------------
    "editor": {
        "label": "Code/text editor",
        "description": (
            "An IDE or text-editor style UI. Examples: 'code editor', "
            "'markdown editor with live preview', 'notepad'."
        ),
        "primary_layout": "file tree | editor pane | optional preview/output pane",
        "primary_screen_goal": "Edit content and see the result.",
        "required_blocks": ["editor-pane"],
        "forbidden_blocks": [
            "hero", "features-grid", "testimonials", "pricing-table", "faq",
            "cta-band", "blog-grid",
        ],
        "engineer_directive": (
            "Build an EDITOR-STYLE UI. Optional left: file tree (collapsible, "
            "current file highlighted). Center: a textarea or contenteditable "
            "div styled monospace, line-numbered if possible. Right: live "
            "preview of the content (rendered markdown / formatted JSON / etc.) "
            "or hide if not relevant. Topbar: file name + save indicator. "
            "useState for content. NO marketing elements."
        ),
    },

    # -----------------------------------------------------------------
    "social": {
        "label": "Social platform",
        "description": (
            "A feed-based social app. Examples: 'twitter clone', 'instagram-"
            "style feed', 'reddit clone'."
        ),
        "primary_layout": "left nav | center feed | right trends/suggestions",
        "primary_screen_goal": "Browse a feed and engage with posts.",
        "required_blocks": ["feed", "compose-input"],
        "forbidden_blocks": [
            "hero", "features-grid", "testimonials", "pricing-table", "faq",
            "cta-band", "newsletter",
        ],
        "engineer_directive": (
            "Build a SOCIAL FEED UI. Three columns on desktop: left nav "
            "(Home, Explore, Notifications, Messages, Profile), center feed "
            "(compose box at top, then 8-12 sample posts with avatar, name, "
            "handle, time, body, like/reply/repost actions with counts that "
            "update on click), right column (trends or who-to-follow widget). "
            "useState for like counts and post composition. NO landing-page "
            "elements."
        ),
    },
}


# ---------------------------------------------------------------------------
# Per-category palette hints. The engineer reads these to bias color choices.
# These pair with the archetype's palette (DesignSystem) — these are FEEL hints,
# not literal hex codes.
# ---------------------------------------------------------------------------

PALETTE_HINTS: dict[str, str] = {
    "landing": "Match the chosen archetype's palette. Modern SaaS feel.",
    "dashboard": "slate/zinc neutral base + a single saturated accent (sky / emerald / violet). Tight contrast.",
    "game": "Deep neutral background (zinc-900 / slate-950) with NEON accent (cyan / lime / fuchsia). Glow on score and active cells.",
    "portfolio": "Restrained neutral (warm white OR off-black) with a single signature accent. Editorial typography weight.",
    "ecommerce": "Clean white/cream base, sharp neutrals, ONE brand color for CTAs and badges. Premium feel — no rainbow.",
    "admin": "Functional grey palette (zinc / slate). Semantic colors only for status (emerald / amber / rose).",
    "chat": "Cool neutral (slate / zinc) with one brand accent for the user's own message bubbles. Quiet, focused.",
    "productivity": "Slate + blue + violet — calm productivity palette. Subtle gradients permitted on hero blocks only.",
    "tool": "Either a moody dark theme (zinc-900 + electric blue/purple) or a clean light theme. Commit to ONE.",
    "mobile-app": "Vivid but harmonious — neutral phone bezel, a saturated brand accent for tab bar / primary actions.",
    "editor": "Dark code-editor palette: deep slate/zinc + one warm accent (amber / coral) for cursor/selection.",
    "social": "Light or dark, but with a single high-contrast brand accent for like/follow buttons.",
}


# ---------------------------------------------------------------------------
# Design quality directive. Injected into EVERY engineer prompt regardless of
# category. This is the "premium feel" guardrail.
# ---------------------------------------------------------------------------

DESIGN_QUALITY_RULES = """\
DESIGN QUALITY — non-negotiable. The output must FEEL premium, not student-tier.

Aspire to: Linear · Vercel · Raycast · Stripe · Notion · Apple.
NOT: generic Bootstrap, plain HTML, Times New Roman, wireframe vibes.

VISUAL HIERARCHY:
  - Big headings use font-display + tracking-tight + font-bold or font-semibold.
  - Secondary text is text-muted-foreground, smaller (text-sm).
  - Generous vertical rhythm: py-12 / py-20 between sections.
  - Container max-w-6xl with px-6 inside.

COMPONENTS:
  - All interactive elements have a visible hover state.
  - Buttons: rounded (use rounded utility), padding-y >= py-2.5, padding-x >= px-4,
    transition-opacity or transition-colors.
  - Cards: rounded, border (border-border), bg-card, padding p-6+, hover:border-primary.
  - Inputs: bordered, focus:ring, focused outline.
  - Use shadow-sm / shadow-md sparingly on cards that should "float".

MOTION (subtle only):
  - transition-colors / transition-opacity on hover.
  - Optional fade-in on initial load using opacity-0 -> opacity-100 with delay.
  - NEVER animate every element.

LAYOUT:
  - Use grid + flex thoughtfully — no awkward stacking.
  - Avoid huge empty white areas: fill with secondary content or rebalance.
  - Mobile-first: layouts must work at 375px.

FORBIDDEN:
  - Default unstyled buttons (use border / bg-primary / hover state).
  - Plain centered single-column layout for non-tool apps.
  - text-black on bg-white without justification.
  - Arbitrary hex codes — use the design tokens (bg-primary, text-foreground, etc.).
  - Three identical-looking cards with no visual differentiation.

The result should look like a real funded startup, not a tutorial demo."""


def get_app_type(name: str) -> dict:
    """Return the registry entry, falling back to landing for unknown types."""
    return APP_TYPE_REGISTRY.get(name, APP_TYPE_REGISTRY["landing"])


def app_type_classifier_catalog() -> str:
    """Compact text block for the Brief agent's classifier."""
    lines = ["AVAILABLE APP TYPES (pick exactly one):"]
    for key, info in APP_TYPE_REGISTRY.items():
        lines.append(f"  - {key}: {info['description']}")
    return "\n".join(lines)
