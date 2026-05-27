"""Deterministic multi-file scaffolder for template-guided niche websites.

Used only when `template_intelligence.classify_and_plan()` returns a
TemplatePlan. Emits a true multi-page React + Vite + Tailwind + React Router
project (HashRouter, iframe-safe) so generated restaurants/cafes/bakeries
have a real navigation structure that users can click through inside Sandpack.

Lives next to (does NOT replace) `scaffold.scaffold_project`. The single-file
scaffolder remains the codepath for every prompt that doesn't trigger the
template intelligence engine.

Design tokens come from the existing DESIGN_MODES catalog via
`scaffold._index_css`, so palette/fonts/shadows behave identically to the
single-file output.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import TYPE_CHECKING

from .design_modes import get_design_mode
from .scaffold import _index_css as _scaffold_index_css
from .schemas import ContentPack, DesignSystem, FileSet, GeneratedFile, ProductBrief, TemplatePlan
from services.image_gen import generate_image_url

if TYPE_CHECKING:
    from services.brand_library import Brand


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def scaffold_multi_page_project(
    brief: ProductBrief,
    design: DesignSystem,
    content: ContentPack,
    plan: TemplatePlan,
    brand: "Brand | None" = None,
) -> FileSet:
    """Emit a multi-file project that maps every plan.pages entry to its own page module."""

    pages = plan.pages or brief.pages

    if not pages:
        # Defensive: empty plan should never reach here, but if it does, build a
        # minimal home-only project rather than crashing.
        from .schemas import PageSpec

        pages = [
            PageSpec(
                name="Home",
                route="/",
                sections=["hero"],
                purpose="Landing page",
            )
        ]

    strategy = getattr(plan, "layout_strategy", None)

    if strategy and strategy.page_graph:
        nav_items = strategy.page_graph
    else:
        nav_items = [
            {"name": "Home", "route": "/"},
        ]

    nav = {
    "header": [
        {
            "label": item["name"],
            "route": item["route"],
        }
        for item in nav_items
    ]
}

    files: list[GeneratedFile] = [
        GeneratedFile(path="package.json", content=_package_json(content)),
        GeneratedFile(path="tsconfig.json", content=_tsconfig()),
        GeneratedFile(path="public/index.html", content=_index_html(content)),
        GeneratedFile(path="src/index.tsx", content=_index_tsx()),
        GeneratedFile(path="src/styles.css", content=_scaffold_index_css(design)),
        GeneratedFile(path="src/lib/utils.ts", content=_utils_ts()),
        GeneratedFile(path="src/App.tsx", content=_app_tsx(page_routes, plan, content)),
        GeneratedFile(path="src/components/Layout.tsx", content=_layout_tsx()),
        GeneratedFile(path="src/components/Nav.tsx", content=_nav_tsx(nav, content)),
        GeneratedFile(path="src/components/Footer.tsx", content=_footer_tsx(nav, content)),
        GeneratedFile(path="src/data/site.ts", content=_site_data_ts(plan, content, data_pack, image_urls)),
    ]

    for page, module_code in zip(page_routes, page_modules):
        files.append(GeneratedFile(path=f"src/pages/{page['component']}.tsx", content=module_code))

    summary = (
        f"{content.brand_name or plan.template_label}: "
        f"{plan.category}/{plan.sub_niche or 'generic'} · "
        f"{len(page_routes)} pages · multi-page router"
    )
    return FileSet(files=files, entry="public/index.html", summary=summary)


# ---------------------------------------------------------------------------
# Page route normalization
# ---------------------------------------------------------------------------

def _normalize_routes(pages) -> list[dict]:
    out: list[dict] = []
    seen_components: set[str] = set()
    for spec in pages:
        route = (spec.route or "/").strip() or "/"
        name = (spec.name or "Page").strip() or "Page"
        component = _component_name_from_route(route, name)
        # Disambiguate collisions
        base = component
        idx = 1
        while component in seen_components:
            idx += 1
            component = f"{base}{idx}"
        seen_components.add(component)
        sections = [str(s) for s in (spec.sections or [])]
        out.append({
            "name": name,
            "route": route,
            "component": component,
            "sections": sections,
            "purpose": spec.purpose or "",
        })
    return out


def _component_name_from_route(route: str, name: str) -> str:
    if route in ("/", "", "/index"):
        return "Home"
    safe = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    if not safe:
        safe = re.sub(r"[^a-z0-9]+", " ", route.lower()).strip() or "page"
    parts = [p.capitalize() for p in safe.split() if p]
    return "".join(parts) or "Page"


# ---------------------------------------------------------------------------
# Navigation resolution
# ---------------------------------------------------------------------------

def _resolve_navigation(plan: TemplatePlan, content: ContentPack, pages: list) -> dict:
    """Prefer the manifest's navigation; fall back to header from pages."""
    nav = plan.navigation or {}
    header = nav.get("header") or []
    if not header:
        header = [
            {"label": p.name, "route": p.route}
            for p in pages
        ]
    page_routes = {(p.route or "/").strip() for p in pages}
    # Drop any nav entry pointing at a route we don't have (validate_routes
    # would otherwise warn, but we want zero dead links in deterministic mode).
    header = [
        {"label": str(item.get("label") or "").strip(),
         "route": str(item.get("route") or "/").strip()}
        for item in header
        if str(item.get("route") or "").strip() in page_routes
        and str(item.get("label") or "").strip()
    ]
    if not header:
        header = [{"label": p.name, "route": p.route} for p in pages]

    footer = nav.get("footer") or {}
    if not isinstance(footer, dict):
        footer = {}
    footer_normalized: dict[str, list[dict]] = {}
    for col, items in footer.items():
        if not isinstance(items, list):
            continue
        col_items = [
            {"label": str(it.get("label") or "").strip(),
             "route": str(it.get("route") or "/").strip()}
            for it in items
            if isinstance(it, dict)
            and str(it.get("route") or "").strip() in page_routes
            and str(it.get("label") or "").strip()
        ]
        if col_items:
            footer_normalized[col] = col_items
    if not footer_normalized:
        footer_normalized = {"Visit": list(header)}

    return {"header": header, "footer": footer_normalized}


# ---------------------------------------------------------------------------
# Image URL prebuilding
# ---------------------------------------------------------------------------

def _stable_seed(text: str) -> int:
    h = hashlib.md5(text.encode("utf-8")).hexdigest()
    return int(h[:7], 16)  # ~28 bits, comfortably in int range


def _parallel_image_urls(specs: list[tuple[str, str, int, int, int]]) -> dict[str, str]:
    """Fan out `generate_image_url(...)` calls across a thread pool.

    `specs` is a list of `(key, prompt, width, height, seed)` tuples. Returns
    a `{key: url}` dict preserving the input keys. The thread-pool size and
    behavior are configurable via env var `POLLINATIONS_FETCH_WORKERS`
    (default 8). Per-image timeout lives inside `services.image_gen` so a
    single stuck fetch can't block the whole batch beyond its own timeout.
    """
    out: dict[str, str] = {}
    if not specs:
        return out
    try:
        workers = max(1, int(os.getenv("POLLINATIONS_FETCH_WORKERS", "8")))
    except (TypeError, ValueError):
        workers = 8
    from concurrent.futures import ThreadPoolExecutor

    def _fetch(spec: tuple[str, str, int, int, int]) -> tuple[str, str]:
        key, prompt, w, h, seed = spec
        return key, generate_image_url(prompt, width=w, height=h, seed=seed)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for key, url in pool.map(_fetch, specs):
            out[key] = url
    return out


def _build_image_urls(plan: TemplatePlan) -> dict[str, str]:
    """Pre-render Pollinations URLs for every image_subject + every menu item.

    Stable per subject so a re-generation with the same plan produces the
    same images (no Sandpack thrash on hot reload). Fetched in parallel via
    `_parallel_image_urls` so 20+ images complete in seconds, not minutes.
    """
    specs: list[tuple[str, str, int, int, int]] = []
    seen: set[str] = set()
    for subject in plan.image_subjects:
        if subject in seen:
            continue
        specs.append((subject,
                      f"{subject}, professional photography, no text, no watermark",
                      1280, 720, _stable_seed(subject)))
        seen.add(subject)
    for item in plan.data_pack:
        subject = str(item.get("image_subject") or item.get("name") or "").strip()
        if subject and subject not in seen:
            specs.append((subject,
                          f"{subject}, food photography, top down, natural light, no text",
                          960, 720, _stable_seed(subject)))
            seen.add(subject)
    return _parallel_image_urls(specs)


# ---------------------------------------------------------------------------
# Static boilerplate
# ---------------------------------------------------------------------------

def _package_json(content: ContentPack) -> str:
    pkg = {
        "name": _slugify(content.brand_name) or "generated-site",
        "version": "0.0.1",
        "dependencies": {
            "react": "^18.3.1",
            "react-dom": "^18.3.1",
            "react-router-dom": "^6.26.0",
            "lucide-react": "^0.460.0",
            "sonner": "^1.5.0",
            "clsx": "^2.1.1",
            "tailwind-merge": "^2.5.0",
        },
        "main": "src/index.tsx",
    }
    return json.dumps(pkg, indent=2)


def _tsconfig() -> str:
    return json.dumps({
        "compilerOptions": {
            "target": "ES2020",
            "useDefineForClassFields": True,
            "lib": ["ES2020", "DOM", "DOM.Iterable"],
            "module": "ESNext",
            "skipLibCheck": True,
            "moduleResolution": "bundler",
            "allowImportingTsExtensions": True,
            "resolveJsonModule": True,
            "isolatedModules": True,
            "noEmit": True,
            "jsx": "react-jsx",
            "strict": False,
            "noUnusedLocals": False,
            "noUnusedParameters": False,
            "noFallthroughCasesInSwitch": True,
            "esModuleInterop": True,
            "allowSyntheticDefaultImports": True,
            "baseUrl": ".",
            "paths": {"@/*": ["src/*"]},
        },
        "include": ["src"],
    }, indent=2)


def _index_html(content: ContentPack) -> str:
    title = _escape_html(content.brand_name or "Generated Site")
    return (
        '<!doctype html>\n'
        '<html lang="en">\n'
        '  <head>\n'
        '    <meta charset="UTF-8" />\n'
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
        f'    <title>{title}</title>\n'
        '    <script src="https://cdn.tailwindcss.com"></script>\n'
        '    <script>\n'
        '      tailwind.config = {\n'
        '        theme: {\n'
        '          extend: {\n'
        '            colors: {\n'
        '              background: "hsl(var(--background))",\n'
        '              foreground: "hsl(var(--foreground))",\n'
        '              muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },\n'
        '              primary: { DEFAULT: "hsl(var(--primary))", foreground: "hsl(var(--primary-foreground))" },\n'
        '              accent: { DEFAULT: "hsl(var(--accent))", foreground: "hsl(var(--accent-foreground))" },\n'
        '              border: "hsl(var(--border))",\n'
        '              card: "hsl(var(--card))",\n'
        '            },\n'
        '            fontFamily: {\n'
        '              display: ["var(--font-display)"],\n'
        '              body: ["var(--font-body)"],\n'
        '              mono: ["var(--font-mono)"],\n'
        '            },\n'
        '            borderRadius: { DEFAULT: "var(--radius)" },\n'
        '          },\n'
        '        },\n'
        '      };\n'
        '    </script>\n'
        '  </head>\n'
        '  <body>\n'
        '    <div id="root"></div>\n'
        '  </body>\n'
        '</html>\n'
    )


def _index_tsx() -> str:
    # HashRouter — safe inside Sandpack's sandboxed iframe (no server routing
    # needed; navigation uses /#/menu style URLs).
    return """import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import { Toaster } from 'sonner';
import App from './App';
import './styles.css';

const root = createRoot(document.getElementById('root')!);
root.render(
  <>
    <HashRouter>
      <App />
    </HashRouter>
    <Toaster richColors position="top-right" />
  </>
);
"""


def _utils_ts() -> str:
    return """import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
"""


# ---------------------------------------------------------------------------
# App.tsx — Routes
# ---------------------------------------------------------------------------

def _app_tsx(pages: list[dict], plan: TemplatePlan, content: ContentPack) -> str:
    imports = "\n".join(
        f"import {p['component']} from './pages/{p['component']}';"
        for p in pages
    )
    routes = "\n        ".join(
        f"<Route path={json.dumps(p['route'])} element={{<{p['component']} />}} />"
        for p in pages
    )
    fallback_component = pages[0]["component"]
    return (
        "import { Routes, Route } from 'react-router-dom';\n"
        "import Layout from './components/Layout';\n"
        f"{imports}\n\n"
        "export default function App() {\n"
        "  return (\n"
        "    <Layout>\n"
        "      <Routes>\n"
        f"        {routes}\n"
        f"        <Route path=\"*\" element={{<{fallback_component} />}} />\n"
        "      </Routes>\n"
        "    </Layout>\n"
        "  );\n"
        "}\n"
    )


# ---------------------------------------------------------------------------
# Layout + Nav + Footer
# ---------------------------------------------------------------------------

def _layout_tsx() -> str:
    return """import { ReactNode } from 'react';
import Nav from './Nav';
import Footer from './Footer';

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background font-body text-foreground antialiased">
      <Nav />
      <main>{children}</main>
      <Footer />
    </div>
  );
}
"""


def _nav_tsx(nav: dict, content: ContentPack) -> str:
    header = nav.get("header") or []
    brand = content.brand_name or "Brand"
    primary_cta = content.primary_cta or "Reserve"
    nav_json = json.dumps(header, ensure_ascii=False)
    brand_json = json.dumps(brand, ensure_ascii=False)
    cta_json = json.dumps(primary_cta, ensure_ascii=False)
    return (
        "import { useState } from 'react';\n"
        "import { Link, useLocation, useNavigate } from 'react-router-dom';\n"
        "import { Menu as MenuIcon, X } from 'lucide-react';\n"
        "import { toast } from 'sonner';\n"
        "import { cn } from '../lib/utils';\n\n"
        f"const NAV: {{ label: string; route: string }}[] = {nav_json};\n"
        f"const BRAND: string = {brand_json};\n"
        f"const PRIMARY_CTA: string = {cta_json};\n\n"
        "export default function Nav() {\n"
        "  const [open, setOpen] = useState(false);\n"
        "  const { pathname } = useLocation();\n"
        "  const navigate = useNavigate();\n"
        "  const isActive = (route: string) => (route === '/' ? pathname === '/' : pathname.startsWith(route));\n"
        "  const ctaTarget = NAV.find((n) => /reservation/i.test(n.route))?.route\n"
        "    || NAV.find((n) => /contact/i.test(n.route))?.route\n"
        "    || '/';\n"
        "  return (\n"
        "    <header className=\"sticky top-0 z-50 border-b border-border bg-background/80 backdrop-blur-md\">\n"
        "      <div className=\"container mx-auto flex max-w-6xl items-center justify-between px-6 py-4\">\n"
        "        <Link to=\"/\" className=\"font-display text-lg font-bold tracking-tight\">{BRAND}</Link>\n"
        "        <nav className=\"hidden gap-6 md:flex\">\n"
        "          {NAV.map((n) => (\n"
        "            <Link\n"
        "              key={n.route}\n"
        "              to={n.route}\n"
        "              className={cn(\n"
        "                'text-sm transition-colors',\n"
        "                isActive(n.route) ? 'text-foreground font-medium' : 'text-muted-foreground hover:text-foreground',\n"
        "              )}\n"
        "            >\n"
        "              {n.label}\n"
        "            </Link>\n"
        "          ))}\n"
        "        </nav>\n"
        "        <div className=\"flex items-center gap-2\">\n"
        "          <button\n"
        "            onClick={() => { navigate(ctaTarget); toast.success('Booking ' + BRAND); }}\n"
        "            className=\"hidden md:inline-flex rounded-[var(--radius)] bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90\"\n"
        "          >\n"
        "            {PRIMARY_CTA}\n"
        "          </button>\n"
        "          <button\n"
        "            onClick={() => setOpen((v) => !v)}\n"
        "            className=\"rounded-md border border-border p-2 md:hidden\"\n"
        "            aria-label=\"Toggle menu\"\n"
        "          >\n"
        "            {open ? <X className=\"h-5 w-5\" /> : <MenuIcon className=\"h-5 w-5\" />}\n"
        "          </button>\n"
        "        </div>\n"
        "      </div>\n"
        "      {open && (\n"
        "        <div className=\"border-t border-border md:hidden\">\n"
        "          <nav className=\"container mx-auto flex max-w-6xl flex-col gap-3 px-6 py-4\">\n"
        "            {NAV.map((n) => (\n"
        "              <Link\n"
        "                key={n.route}\n"
        "                to={n.route}\n"
        "                onClick={() => setOpen(false)}\n"
        "                className={cn(\n"
        "                  'text-sm transition-colors',\n"
        "                  isActive(n.route) ? 'text-foreground font-medium' : 'text-muted-foreground hover:text-foreground',\n"
        "                )}\n"
        "              >\n"
        "                {n.label}\n"
        "              </Link>\n"
        "            ))}\n"
        "            <button\n"
        "              onClick={() => { setOpen(false); navigate(ctaTarget); toast.success('Booking ' + BRAND); }}\n"
        "              className=\"mt-2 rounded-[var(--radius)] bg-primary px-4 py-2 text-sm font-medium text-primary-foreground\"\n"
        "            >\n"
        "              {PRIMARY_CTA}\n"
        "            </button>\n"
        "          </nav>\n"
        "        </div>\n"
        "      )}\n"
        "    </header>\n"
        "  );\n"
        "}\n"
    )


def _footer_tsx(nav: dict, content: ContentPack) -> str:
    footer = nav.get("footer") or {}
    brand = content.brand_name or "Brand"
    tagline = content.tagline or ""
    return (
        "import { Link } from 'react-router-dom';\n\n"
        f"const FOOTER: Record<string, {{ label: string; route: string }}[]> = {json.dumps(footer, ensure_ascii=False)};\n"
        f"const BRAND: string = {json.dumps(brand, ensure_ascii=False)};\n"
        f"const TAGLINE: string = {json.dumps(tagline, ensure_ascii=False)};\n\n"
        "export default function Footer() {\n"
        "  const cols = Object.keys(FOOTER);\n"
        "  return (\n"
        "    <footer className=\"mt-24 border-t border-border bg-muted/20\">\n"
        "      <div className=\"container mx-auto max-w-6xl px-6 py-12\">\n"
        "        <div className=\"grid gap-8 md:grid-cols-4\">\n"
        "          <div>\n"
        "            <div className=\"font-display text-lg font-bold\">{BRAND}</div>\n"
        "            {TAGLINE && <p className=\"mt-2 max-w-xs text-sm text-muted-foreground\">{TAGLINE}</p>}\n"
        "          </div>\n"
        "          {cols.map((col) => (\n"
        "            <div key={col}>\n"
        "              <div className=\"mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground\">{col}</div>\n"
        "              <ul className=\"space-y-2\">\n"
        "                {FOOTER[col].map((item) => (\n"
        "                  <li key={item.route}>\n"
        "                    <Link to={item.route} className=\"text-sm text-muted-foreground hover:text-foreground\">{item.label}</Link>\n"
        "                  </li>\n"
        "                ))}\n"
        "              </ul>\n"
        "            </div>\n"
        "          ))}\n"
        "        </div>\n"
        "        <div className=\"mt-12 border-t border-border pt-6 text-xs text-muted-foreground\">\n"
        "          © {new Date().getFullYear()} {BRAND}. All rights reserved.\n"
        "        </div>\n"
        "      </div>\n"
        "    </footer>\n"
        "  );\n"
        "}\n"
    )


# ---------------------------------------------------------------------------
# src/data/site.ts — niche data + image URLs as one typed module
# ---------------------------------------------------------------------------

def _site_data_ts(
    plan: TemplatePlan,
    content: ContentPack,
    data_pack: list[dict],
    image_urls: dict[str, str],
) -> str:
    menu_items: list[dict] = []
    for item in data_pack:
        subject = str(item.get("image_subject") or item.get("name") or "").strip()
        menu_items.append({
            "name": str(item.get("name") or "").strip(),
            "price": str(item.get("price") or "").strip(),
            "category": str(item.get("category") or "Menu").strip(),
            "description": str(item.get("description") or "").strip(),
            "image": image_urls.get(subject, ""),
            "image_subject": subject,
        })
    gallery: list[dict] = []
    for subject in plan.image_subjects:
        gallery.append({
            "subject": subject,
            "image": image_urls.get(subject, ""),
        })

    site = {
        "brand": content.brand_name or plan.template_label,
        "tagline": content.tagline or "",
        "hero_headline": content.hero_headline or content.brand_name or plan.template_label,
        "hero_subhead": content.hero_subhead or "",
        "primary_cta": content.primary_cta or "Reserve",
        "secondary_cta": content.secondary_cta or "View Menu",
        "category": plan.category,
        "sub_niche": plan.sub_niche or "",
        "mood": list(plan.mood),
        "menu": menu_items,
        "gallery": gallery,
        "hero_image": (gallery[0]["image"] if gallery else ""),
        "hours": [
            {"day": "Mon – Thu", "time": "5:00 PM – 10:00 PM"},
            {"day": "Fri – Sat", "time": "5:00 PM – 11:00 PM"},
            {"day": "Sunday",     "time": "5:00 PM – 9:00 PM"},
        ],
        "address": "123 Lantern Street, Downtown",
        "phone": "(555) 123-4567",
        "email": _derive_email(content),
    }
    body = json.dumps(site, ensure_ascii=False, indent=2)
    return (
        "// Niche site data — derived deterministically from the template plan.\n"
        "// Do not hand-edit individual items; regenerate by re-running the builder.\n\n"
        "export type MenuItem = {\n"
        "  name: string; price: string; category: string;\n"
        "  description: string; image: string; image_subject: string;\n"
        "};\n"
        "export type GalleryItem = { subject: string; image: string };\n"
        "export type Hour = { day: string; time: string };\n\n"
        f"const SITE = {body} as const;\n\n"
        "export default SITE;\n"
        "export const MENU: MenuItem[] = SITE.menu as unknown as MenuItem[];\n"
        "export const GALLERY: GalleryItem[] = SITE.gallery as unknown as GalleryItem[];\n"
        "export const HOURS: Hour[] = SITE.hours as unknown as Hour[];\n"
    )


def _derive_email(content: ContentPack) -> str:
    slug = _slugify(content.brand_name) or "hello"
    return f"hello@{slug}.com"


# ---------------------------------------------------------------------------
# Page modules
# ---------------------------------------------------------------------------

def _page_module(
    page: dict,
    plan: TemplatePlan,
    content: ContentPack,
    data_pack: list[dict],
    image_urls: dict[str, str],
) -> str:
    component = page["component"]
    name = page["name"]
    purpose = page["purpose"]
    sections = page["sections"]

    if component == "Home":
        return _home_page(component, plan, content)
    if "menu" in name.lower():
        return _menu_page(component, name)
    if "reservation" in name.lower():
        return _reservations_page(component, name, content)
    if "gallery" in name.lower():
        return _gallery_page(component, name)
    if "contact" in name.lower():
        return _contact_page(component, name)
    if "about" in name.lower():
        return _about_page(component, name, plan, content)
    return _generic_page(component, name, purpose, sections)


def _page_header(component: str, name: str, eyebrow: str = "") -> str:
    eyebrow_block = (
        f"        <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{eyebrow}</p>\n"
        if eyebrow else ""
    )
    return (
        f"// {component} page — auto-generated.\n"
        "export default function " + component + "() {\n"
        "  return (\n"
        "    <section className=\"container mx-auto max-w-6xl px-6 py-20\">\n"
        "      <div className=\"mb-12\">\n"
        f"{eyebrow_block}"
        f"        <h1 className=\"font-display text-4xl font-bold tracking-tight md:text-5xl\">{name}</h1>\n"
        "      </div>\n"
    )


def _home_page(component: str, plan: TemplatePlan, content: ContentPack) -> str:
    tagline = (content.tagline or "").replace("'", "\\'")
    headline = content.hero_headline or content.brand_name or plan.template_label
    subhead = content.hero_subhead or ""
    return (
        "import { Link } from 'react-router-dom';\n"
        "import { ArrowRight } from 'lucide-react';\n"
        "import SITE, { MENU, GALLERY } from '../data/site';\n\n"
        "export default function Home() {\n"
        "  const featured = MENU.slice(0, 6);\n"
        "  const galleryStrip = GALLERY.slice(0, 4);\n"
        "  return (\n"
        "    <>\n"
        "      {/* HERO */}\n"
        "      <section className=\"relative overflow-hidden\">\n"
        "        {SITE.hero_image && (\n"
        "          <img\n"
        "            src={SITE.hero_image}\n"
        "            alt=\"\"\n"
        "            className=\"absolute inset-0 h-full w-full object-cover opacity-30\"\n"
        "          />\n"
        "        )}\n"
        "        <div className=\"relative container mx-auto max-w-6xl px-6 py-28 text-center md:py-36\">\n"
        f"          {{SITE.tagline && <p className=\"mb-4 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{{SITE.tagline}}</p>}}\n"
        "          <h1 className=\"mx-auto max-w-3xl animate-fade-up-1 font-display text-5xl font-bold leading-tight tracking-tight md:text-7xl\">\n"
        "            {SITE.hero_headline}\n"
        "          </h1>\n"
        "          {SITE.hero_subhead && (\n"
        "            <p className=\"mx-auto mt-6 max-w-2xl text-lg text-muted-foreground\">{SITE.hero_subhead}</p>\n"
        "          )}\n"
        "          <div className=\"mt-10 flex flex-wrap items-center justify-center gap-3\">\n"
        "            <Link\n"
        "              to=\"/menu\"\n"
        "              className=\"inline-flex items-center gap-2 rounded-[var(--radius)] bg-primary px-6 py-3 text-base font-medium text-primary-foreground transition-opacity hover:opacity-90\"\n"
        "            >\n"
        "              {SITE.secondary_cta}\n"
        "              <ArrowRight className=\"h-4 w-4\" />\n"
        "            </Link>\n"
        "            <Link\n"
        "              to=\"/reservations\"\n"
        "              className=\"inline-flex items-center gap-2 rounded-[var(--radius)] border border-border px-6 py-3 text-base font-medium transition-colors hover:bg-muted\"\n"
        "            >\n"
        "              {SITE.primary_cta}\n"
        "            </Link>\n"
        "          </div>\n"
        "        </div>\n"
        "      </section>\n\n"
        "      {/* SIGNATURE DISHES */}\n"
        "      {featured.length > 0 && (\n"
        "        <section className=\"container mx-auto max-w-6xl px-6 py-20\">\n"
        "          <div className=\"mb-12 text-center\">\n"
        "            <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">Signature</p>\n"
        "            <h2 className=\"font-display text-3xl font-bold tracking-tight md:text-4xl\">Plates we are known for</h2>\n"
        "          </div>\n"
        "          <div className=\"grid gap-6 md:grid-cols-2 lg:grid-cols-3\">\n"
        "            {featured.map((item) => (\n"
        "              <article key={item.name} className=\"overflow-hidden rounded-[var(--radius)] border border-border bg-card hover-lift transition-all hover:border-primary\">\n"
        "                {item.image && (\n"
        "                  <img src={item.image} alt={item.name} className=\"h-48 w-full object-cover\" loading=\"lazy\" />\n"
        "                )}\n"
        "                <div className=\"p-5\">\n"
        "                  <div className=\"flex items-baseline justify-between gap-3\">\n"
        "                    <h3 className=\"font-display text-lg font-semibold\">{item.name}</h3>\n"
        "                    <span className=\"text-sm font-medium text-primary\">{item.price}</span>\n"
        "                  </div>\n"
        "                  <p className=\"mt-1 text-xs uppercase tracking-wider text-muted-foreground\">{item.category}</p>\n"
        "                  {item.description && <p className=\"mt-3 text-sm text-muted-foreground\">{item.description}</p>}\n"
        "                </div>\n"
        "              </article>\n"
        "            ))}\n"
        "          </div>\n"
        "          <div className=\"mt-10 text-center\">\n"
        "            <Link to=\"/menu\" className=\"inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline\">\n"
        "              See the full menu <ArrowRight className=\"h-4 w-4\" />\n"
        "            </Link>\n"
        "          </div>\n"
        "        </section>\n"
        "      )}\n\n"
        "      {/* GALLERY STRIP */}\n"
        "      {galleryStrip.length > 0 && (\n"
        "        <section className=\"border-y border-border bg-muted/20 py-20\">\n"
        "          <div className=\"container mx-auto max-w-6xl px-6\">\n"
        "            <div className=\"grid gap-3 sm:grid-cols-2 lg:grid-cols-4\">\n"
        "              {galleryStrip.map((g) => (\n"
        "                <div key={g.subject} className=\"aspect-square overflow-hidden rounded-[var(--radius)]\">\n"
        "                  {g.image && (\n"
        "                    <img src={g.image} alt={g.subject} className=\"h-full w-full object-cover transition-transform duration-500 hover:scale-105\" loading=\"lazy\" />\n"
        "                  )}\n"
        "                </div>\n"
        "              ))}\n"
        "            </div>\n"
        "          </div>\n"
        "        </section>\n"
        "      )}\n\n"
        "      {/* RESERVATION CTA */}\n"
        "      <section className=\"container mx-auto max-w-4xl px-6 py-24 text-center\">\n"
        "        <h2 className=\"mx-auto max-w-xl font-display text-3xl font-bold tracking-tight md:text-4xl\">\n"
        "          Reserve a table\n"
        "        </h2>\n"
        "        <p className=\"mx-auto mt-3 max-w-md text-muted-foreground\">\n"
        "          We hold tables for parties of 1 to 8. Larger groups by request.\n"
        "        </p>\n"
        "        <Link\n"
        "          to=\"/reservations\"\n"
        "          className=\"mt-8 inline-flex items-center gap-2 rounded-[var(--radius)] bg-primary px-6 py-3 text-base font-medium text-primary-foreground transition-opacity hover:opacity-90\"\n"
        "        >\n"
        "          {SITE.primary_cta}\n"
        "          <ArrowRight className=\"h-4 w-4\" />\n"
        "        </Link>\n"
        "      </section>\n"
        "    </>\n"
        "  );\n"
        "}\n"
    )


def _menu_page(component: str, name: str) -> str:
    return (
        "import { useMemo, useState } from 'react';\n"
        "import { MENU } from '../data/site';\n\n"
        "export default function " + component + "() {\n"
        "  const categories = useMemo(() => {\n"
        "    const set = new Set<string>();\n"
        "    MENU.forEach((m) => set.add(m.category));\n"
        "    return ['All', ...Array.from(set)];\n"
        "  }, []);\n"
        "  const [active, setActive] = useState<string>('All');\n"
        "  const filtered = active === 'All' ? MENU : MENU.filter((m) => m.category === active);\n"
        "  return (\n"
        "    <section className=\"container mx-auto max-w-6xl px-6 py-20\">\n"
        "      <div className=\"mb-10\">\n"
        f"        <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{name}</p>\n"
        "        <h1 className=\"font-display text-4xl font-bold tracking-tight md:text-5xl\">A taste of the kitchen</h1>\n"
        "      </div>\n"
        "      <div className=\"mb-10 flex flex-wrap gap-2\">\n"
        "        {categories.map((c) => (\n"
        "          <button\n"
        "            key={c}\n"
        "            onClick={() => setActive(c)}\n"
        "            className={'rounded-full border px-4 py-2 text-sm transition-colors ' + (active === c ? 'border-primary bg-primary text-primary-foreground' : 'border-border hover:bg-muted')}\n"
        "          >\n"
        "            {c}\n"
        "          </button>\n"
        "        ))}\n"
        "      </div>\n"
        "      <div className=\"grid gap-6 md:grid-cols-2 lg:grid-cols-3\">\n"
        "        {filtered.map((item) => (\n"
        "          <article key={item.name} className=\"overflow-hidden rounded-[var(--radius)] border border-border bg-card hover-lift transition-all hover:border-primary\">\n"
        "            {item.image && (\n"
        "              <img src={item.image} alt={item.name} className=\"h-44 w-full object-cover\" loading=\"lazy\" />\n"
        "            )}\n"
        "            <div className=\"p-5\">\n"
        "              <div className=\"flex items-baseline justify-between gap-3\">\n"
        "                <h3 className=\"font-display text-lg font-semibold\">{item.name}</h3>\n"
        "                <span className=\"text-sm font-medium text-primary\">{item.price}</span>\n"
        "              </div>\n"
        "              <p className=\"mt-1 text-xs uppercase tracking-wider text-muted-foreground\">{item.category}</p>\n"
        "              {item.description && <p className=\"mt-3 text-sm text-muted-foreground\">{item.description}</p>}\n"
        "            </div>\n"
        "          </article>\n"
        "        ))}\n"
        "      </div>\n"
        "    </section>\n"
        "  );\n"
        "}\n"
    )


def _reservations_page(component: str, name: str, content: ContentPack) -> str:
    return (
        "import { FormEvent, useState } from 'react';\n"
        "import { toast } from 'sonner';\n"
        "import SITE from '../data/site';\n\n"
        "export default function " + component + "() {\n"
        "  const [name, setName] = useState('');\n"
        "  const [date, setDate] = useState('');\n"
        "  const [time, setTime] = useState('19:00');\n"
        "  const [party, setParty] = useState(2);\n"
        "  const [notes, setNotes] = useState('');\n"
        "  function onSubmit(e: FormEvent) {\n"
        "    e.preventDefault();\n"
        "    if (!name.trim() || !date) {\n"
        "      toast.error('Please enter your name and a date');\n"
        "      return;\n"
        "    }\n"
        "    toast.success(`Reservation requested for ${party} on ${date} at ${time}`);\n"
        "    setName(''); setNotes('');\n"
        "  }\n"
        "  return (\n"
        "    <section className=\"container mx-auto max-w-3xl px-6 py-20\">\n"
        f"      <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{name}</p>\n"
        "      <h1 className=\"font-display text-4xl font-bold tracking-tight md:text-5xl\">Book a table at {SITE.brand}</h1>\n"
        "      <p className=\"mt-4 text-muted-foreground\">We hold tables for 1 to 8 guests. Larger parties by request.</p>\n"
        "      <form onSubmit={onSubmit} className=\"mt-10 grid gap-5 rounded-[var(--radius)] border border-border bg-card p-8\">\n"
        "        <label className=\"text-sm\">\n"
        "          Name\n"
        "          <input value={name} onChange={(e) => setName(e.target.value)} required className=\"mt-2 w-full rounded-[var(--radius)] border border-border bg-background px-3 py-2 text-sm\" />\n"
        "        </label>\n"
        "        <div className=\"grid gap-5 md:grid-cols-3\">\n"
        "          <label className=\"text-sm\">\n"
        "            Date\n"
        "            <input type=\"date\" value={date} onChange={(e) => setDate(e.target.value)} required className=\"mt-2 w-full rounded-[var(--radius)] border border-border bg-background px-3 py-2 text-sm\" />\n"
        "          </label>\n"
        "          <label className=\"text-sm\">\n"
        "            Time\n"
        "            <input type=\"time\" value={time} onChange={(e) => setTime(e.target.value)} className=\"mt-2 w-full rounded-[var(--radius)] border border-border bg-background px-3 py-2 text-sm\" />\n"
        "          </label>\n"
        "          <label className=\"text-sm\">\n"
        "            Party size\n"
        "            <input type=\"number\" min={1} max={8} value={party} onChange={(e) => setParty(parseInt(e.target.value || '1', 10))} className=\"mt-2 w-full rounded-[var(--radius)] border border-border bg-background px-3 py-2 text-sm\" />\n"
        "          </label>\n"
        "        </div>\n"
        "        <label className=\"text-sm\">\n"
        "          Notes (allergies, occasion)\n"
        "          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} className=\"mt-2 w-full rounded-[var(--radius)] border border-border bg-background px-3 py-2 text-sm\" rows={3} />\n"
        "        </label>\n"
        "        <button type=\"submit\" className=\"justify-self-start rounded-[var(--radius)] bg-primary px-5 py-3 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90\">\n"
        "          Request reservation\n"
        "        </button>\n"
        "      </form>\n"
        "      <p className=\"mt-6 text-xs text-muted-foreground\">We confirm within 24 hours. Cancellations welcome up to 4 hours before your seating.</p>\n"
        "    </section>\n"
        "  );\n"
        "}\n"
    )


def _gallery_page(component: str, name: str) -> str:
    return (
        "import { GALLERY } from '../data/site';\n\n"
        "export default function " + component + "() {\n"
        "  return (\n"
        "    <section className=\"container mx-auto max-w-6xl px-6 py-20\">\n"
        "      <div className=\"mb-10\">\n"
        f"        <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{name}</p>\n"
        "        <h1 className=\"font-display text-4xl font-bold tracking-tight md:text-5xl\">Inside the room</h1>\n"
        "      </div>\n"
        "      <div className=\"grid gap-4 sm:grid-cols-2 lg:grid-cols-3\">\n"
        "        {GALLERY.map((g) => (\n"
        "          <figure key={g.subject} className=\"overflow-hidden rounded-[var(--radius)] border border-border\">\n"
        "            {g.image && <img src={g.image} alt={g.subject} className=\"h-72 w-full object-cover transition-transform duration-500 hover:scale-105\" loading=\"lazy\" />}\n"
        "            <figcaption className=\"px-4 py-3 text-xs text-muted-foreground capitalize\">{g.subject}</figcaption>\n"
        "          </figure>\n"
        "        ))}\n"
        "      </div>\n"
        "    </section>\n"
        "  );\n"
        "}\n"
    )


def _contact_page(component: str, name: str) -> str:
    return (
        "import { FormEvent, useState } from 'react';\n"
        "import { toast } from 'sonner';\n"
        "import { MapPin, Clock, Phone, Mail } from 'lucide-react';\n"
        "import SITE, { HOURS } from '../data/site';\n\n"
        "export default function " + component + "() {\n"
        "  const [name, setName] = useState('');\n"
        "  const [email, setEmail] = useState('');\n"
        "  const [message, setMessage] = useState('');\n"
        "  function onSubmit(e: FormEvent) {\n"
        "    e.preventDefault();\n"
        "    if (!name.trim() || !email.trim() || !message.trim()) {\n"
        "      toast.error('Please complete all fields');\n"
        "      return;\n"
        "    }\n"
        "    toast.success('Thanks! We will reply within one business day.');\n"
        "    setName(''); setEmail(''); setMessage('');\n"
        "  }\n"
        "  return (\n"
        "    <section className=\"container mx-auto max-w-6xl px-6 py-20\">\n"
        "      <div className=\"mb-10\">\n"
        f"        <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{name}</p>\n"
        "        <h1 className=\"font-display text-4xl font-bold tracking-tight md:text-5xl\">Visit {SITE.brand}</h1>\n"
        "      </div>\n"
        "      <div className=\"grid gap-10 md:grid-cols-2\">\n"
        "        <div className=\"space-y-6\">\n"
        "          <div className=\"flex items-start gap-3\">\n"
        "            <MapPin className=\"mt-0.5 h-5 w-5 text-primary\" />\n"
        "            <div>\n"
        "              <div className=\"font-medium\">Address</div>\n"
        "              <div className=\"text-sm text-muted-foreground\">{SITE.address}</div>\n"
        "            </div>\n"
        "          </div>\n"
        "          <div className=\"flex items-start gap-3\">\n"
        "            <Clock className=\"mt-0.5 h-5 w-5 text-primary\" />\n"
        "            <div>\n"
        "              <div className=\"font-medium\">Hours</div>\n"
        "              <ul className=\"mt-1 space-y-1 text-sm text-muted-foreground\">\n"
        "                {HOURS.map((h) => (\n"
        "                  <li key={h.day}><span className=\"font-medium text-foreground\">{h.day}</span> · {h.time}</li>\n"
        "                ))}\n"
        "              </ul>\n"
        "            </div>\n"
        "          </div>\n"
        "          <div className=\"flex items-start gap-3\">\n"
        "            <Phone className=\"mt-0.5 h-5 w-5 text-primary\" />\n"
        "            <div>\n"
        "              <div className=\"font-medium\">Phone</div>\n"
        "              <div className=\"text-sm text-muted-foreground\">{SITE.phone}</div>\n"
        "            </div>\n"
        "          </div>\n"
        "          <div className=\"flex items-start gap-3\">\n"
        "            <Mail className=\"mt-0.5 h-5 w-5 text-primary\" />\n"
        "            <div>\n"
        "              <div className=\"font-medium\">Email</div>\n"
        "              <div className=\"text-sm text-muted-foreground\">{SITE.email}</div>\n"
        "            </div>\n"
        "          </div>\n"
        "        </div>\n"
        "        <form onSubmit={onSubmit} className=\"space-y-4 rounded-[var(--radius)] border border-border bg-card p-6\">\n"
        "          <label className=\"block text-sm\">Name\n"
        "            <input value={name} onChange={(e) => setName(e.target.value)} className=\"mt-2 w-full rounded-[var(--radius)] border border-border bg-background px-3 py-2 text-sm\" />\n"
        "          </label>\n"
        "          <label className=\"block text-sm\">Email\n"
        "            <input type=\"email\" value={email} onChange={(e) => setEmail(e.target.value)} className=\"mt-2 w-full rounded-[var(--radius)] border border-border bg-background px-3 py-2 text-sm\" />\n"
        "          </label>\n"
        "          <label className=\"block text-sm\">Message\n"
        "            <textarea value={message} onChange={(e) => setMessage(e.target.value)} rows={4} className=\"mt-2 w-full rounded-[var(--radius)] border border-border bg-background px-3 py-2 text-sm\" />\n"
        "          </label>\n"
        "          <button type=\"submit\" className=\"rounded-[var(--radius)] bg-primary px-5 py-3 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90\">\n"
        "            Send message\n"
        "          </button>\n"
        "        </form>\n"
        "      </div>\n"
        "    </section>\n"
        "  );\n"
        "}\n"
    )


def _about_page(component: str, name: str, plan: TemplatePlan, content: ContentPack) -> str:
    mood_text = ", ".join(plan.mood[:3]) or "warm, traditional, modern"
    return (
        "import { GALLERY } from '../data/site';\n"
        "import SITE from '../data/site';\n\n"
        "export default function " + component + "() {\n"
        "  const portrait = GALLERY[1] || GALLERY[0];\n"
        "  return (\n"
        "    <section className=\"container mx-auto max-w-5xl px-6 py-20\">\n"
        "      <div className=\"mb-10\">\n"
        f"        <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{name}</p>\n"
        "        <h1 className=\"font-display text-4xl font-bold tracking-tight md:text-5xl\">The story behind {SITE.brand}</h1>\n"
        "      </div>\n"
        "      <div className=\"grid gap-10 md:grid-cols-2 md:items-center\">\n"
        "        <div className=\"space-y-5 text-muted-foreground\">\n"
        "          <p>\n"
        "            {SITE.brand} began with a simple idea: cook the food we grew up with, with the\n"
        "            ingredients we wish we had. Every plate, every pour, every season is built on that.\n"
        "          </p>\n"
        "          <p>\n"
        f"            Our kitchen is {mood_text}. We make most things from scratch, source from local farms\n"
        "            when we can, and keep the menu small enough that we can keep our hands on every dish.\n"
        "          </p>\n"
        "          <p>\n"
        "            We are open six nights a week. Some nights are quiet; some nights the room hums. We love\n"
        "            both. Come hungry — that is the only ask.\n"
        "          </p>\n"
        "        </div>\n"
        "        {portrait && (\n"
        "          <div className=\"overflow-hidden rounded-[var(--radius)] border border-border\">\n"
        "            <img src={portrait.image} alt={portrait.subject} className=\"h-full w-full object-cover\" loading=\"lazy\" />\n"
        "          </div>\n"
        "        )}\n"
        "      </div>\n"
        "    </section>\n"
        "  );\n"
        "}\n"
    )


def _generic_page(component: str, name: str, purpose: str, sections: list[str]) -> str:
    sections_blob = json.dumps(sections, ensure_ascii=False)
    purpose_safe = purpose.replace("'", "\\'") if purpose else ""
    purpose_block = (
        f"      <p className=\"text-muted-foreground\">{purpose_safe}</p>\n"
        if purpose else ""
    )
    return (
        f"// {component} — generic page, populated from manifest sections.\n"
        f"const SECTIONS: string[] = {sections_blob};\n\n"
        "export default function " + component + "() {\n"
        "  return (\n"
        "    <section className=\"container mx-auto max-w-4xl px-6 py-20\">\n"
        f"      <h1 className=\"mb-6 font-display text-4xl font-bold tracking-tight md:text-5xl\">{name}</h1>\n"
        f"{purpose_block}"
        "      {SECTIONS.length > 0 && (\n"
        "        <ul className=\"mt-10 space-y-3 text-sm text-muted-foreground\">\n"
        "          {SECTIONS.map((s) => (\n"
        "            <li key={s} className=\"rounded-[var(--radius)] border border-border bg-card p-4 capitalize\">\n"
        "              {s.replace(/-/g, ' ')}\n"
        "            </li>\n"
        "          ))}\n"
        "        </ul>\n"
        "      )}\n"
        "    </section>\n"
        "  );\n"
        "}\n"
    )


# ---------------------------------------------------------------------------
# Helpers
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


# ===========================================================================
# Open Lovable archetype scaffolders (SaaS / Portfolio / Ecommerce)
# ===========================================================================
#
# Each archetype shares the existing boilerplate emitters (HashRouter index,
# Layout, Footer, App.tsx route map, design-token CSS, package.json, etc.)
# and only overrides:
#   - the data module (`src/data/site.ts`)
#   - the per-page TSX modules
#   - the Nav (slightly — to use a niche-appropriate CTA route lookup)
#
# All deterministic. No LLM in this layer.


def scaffold_for_plan(
    brief: ProductBrief,
    design: DesignSystem,
    content: ContentPack,
    plan: TemplatePlan,
    brand: "Brand | None" = None,
) -> FileSet:
    """Dispatch to the right multi-page scaffolder for the plan's category.

    Existing restaurant behavior is byte-identical: when `plan.category`
    is "restaurant" we call the original `scaffold_multi_page_project`.
    """
    
    strategy = getattr(plan, "layout_strategy", None)

    # NEW: strategy-driven generation
    if strategy:

        visual_style = str(strategy.visual_style).lower()

        # cinematic/editorial/luxury
        if any(x in visual_style for x in [
            "editorial",
            "luxury",
            "cinematic",
            "royal",
        ]):
            return scaffold_editorial_project(
                brief,
                design,
                content,
                plan,
                strategy,
                brand=brand,
            )

        # soft romantic / beach / airy
        if any(x in visual_style for x in [
            "romantic",
            "beach",
            "airy",
            "soft",
        ]):
            return scaffold_romantic_project(
                brief,
                design,
                content,
                plan,
                strategy,
                brand=brand,
            )

        # dashboard/productivity
        if any(x in visual_style for x in [
            "dashboard",
            "productivity",
            "analytics",
        ]):
            return scaffold_dashboard_project(
                brief,
                design,
                content,
                plan,
                strategy,
                brand=brand,
            )

    # FALLBACKS (KEEP EXISTING)
    cat = (plan.category or "").lower()

    if cat == "saas":
        return scaffold_saas_page_project(
            brief,
            design,
            content,
            plan,
            brand=brand,
        )

    if cat == "portfolio":
        return scaffold_portfolio_page_project(
            brief,
            design,
            content,
            plan,
            brand=brand,
        )

    if cat == "ecommerce":
        return scaffold_ecommerce_page_project(
            brief,
            design,
            content,
            plan,
            brand=brand,
        )

    if cat == "healthcare":
        return scaffold_healthcare_page_project(
            brief,
            design,
            content,
            plan,
            brand=brand,
        )

    return scaffold_multi_page_project(
        brief,
        design,
        content,
        plan,
        brand=brand,
    )


# ---------------------------------------------------------------------------
# Archetype-friendly Nav (parameterized CTA route lookup)
# ---------------------------------------------------------------------------

def _archetype_nav_tsx(
    nav: dict,
    content: ContentPack,
    cta_route_keywords: list[str],
) -> str:
    """Like `_nav_tsx`, but the CTA target is configurable per-archetype.

    `cta_route_keywords` is a regex-fragment list searched (case-insensitive)
    against the nav routes; the first match wins. Falls back to '/'.
    The toast on click uses the primary_cta verbatim so we never say "Booking"
    for a SaaS or portfolio site.
    """
    header = nav.get("header") or []
    brand = content.brand_name or "Brand"
    primary_cta = content.primary_cta or "Get started"
    nav_json = json.dumps(header, ensure_ascii=False)
    brand_json = json.dumps(brand, ensure_ascii=False)
    cta_json = json.dumps(primary_cta, ensure_ascii=False)
    kw_json = json.dumps([k.lower() for k in cta_route_keywords], ensure_ascii=False)
    return (
        "import { useState } from 'react';\n"
        "import { Link, useLocation, useNavigate } from 'react-router-dom';\n"
        "import { Menu as MenuIcon, X } from 'lucide-react';\n"
        "import { toast } from 'sonner';\n"
        "import { cn } from '../lib/utils';\n\n"
        f"const NAV: {{ label: string; route: string }}[] = {nav_json};\n"
        f"const BRAND: string = {brand_json};\n"
        f"const PRIMARY_CTA: string = {cta_json};\n"
        f"const CTA_KEYWORDS: string[] = {kw_json};\n\n"
        "function pickCtaTarget() {\n"
        "  for (const kw of CTA_KEYWORDS) {\n"
        "    const hit = NAV.find((n) => n.route.toLowerCase().includes(kw));\n"
        "    if (hit) return hit.route;\n"
        "  }\n"
        "  return '/';\n"
        "}\n\n"
        "export default function Nav() {\n"
        "  const [open, setOpen] = useState(false);\n"
        "  const { pathname } = useLocation();\n"
        "  const navigate = useNavigate();\n"
        "  const isActive = (route: string) => (route === '/' ? pathname === '/' : pathname.startsWith(route));\n"
        "  const ctaTarget = pickCtaTarget();\n"
        "  return (\n"
        "    <header className=\"sticky top-0 z-50 border-b border-border bg-background/80 backdrop-blur-md\">\n"
        "      <div className=\"container mx-auto flex max-w-6xl items-center justify-between px-6 py-4\">\n"
        "        <Link to=\"/\" className=\"font-display text-lg font-bold tracking-tight\">{BRAND}</Link>\n"
        "        <nav className=\"hidden gap-6 md:flex\">\n"
        "          {NAV.map((n) => (\n"
        "            <Link\n"
        "              key={n.route}\n"
        "              to={n.route}\n"
        "              className={cn(\n"
        "                'text-sm transition-colors',\n"
        "                isActive(n.route) ? 'text-foreground font-medium' : 'text-muted-foreground hover:text-foreground',\n"
        "              )}\n"
        "            >\n"
        "              {n.label}\n"
        "            </Link>\n"
        "          ))}\n"
        "        </nav>\n"
        "        <div className=\"flex items-center gap-2\">\n"
        "          <button\n"
        "            onClick={() => { navigate(ctaTarget); toast.success(PRIMARY_CTA); }}\n"
        "            className=\"hidden md:inline-flex rounded-[var(--radius)] bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90\"\n"
        "          >\n"
        "            {PRIMARY_CTA}\n"
        "          </button>\n"
        "          <button\n"
        "            onClick={() => setOpen((v) => !v)}\n"
        "            className=\"rounded-md border border-border p-2 md:hidden\"\n"
        "            aria-label=\"Toggle menu\"\n"
        "          >\n"
        "            {open ? <X className=\"h-5 w-5\" /> : <MenuIcon className=\"h-5 w-5\" />}\n"
        "          </button>\n"
        "        </div>\n"
        "      </div>\n"
        "      {open && (\n"
        "        <div className=\"border-t border-border md:hidden\">\n"
        "          <nav className=\"container mx-auto flex max-w-6xl flex-col gap-3 px-6 py-4\">\n"
        "            {NAV.map((n) => (\n"
        "              <Link\n"
        "                key={n.route}\n"
        "                to={n.route}\n"
        "                onClick={() => setOpen(false)}\n"
        "                className={cn(\n"
        "                  'text-sm transition-colors',\n"
        "                  isActive(n.route) ? 'text-foreground font-medium' : 'text-muted-foreground hover:text-foreground',\n"
        "                )}\n"
        "              >\n"
        "                {n.label}\n"
        "              </Link>\n"
        "            ))}\n"
        "            <button\n"
        "              onClick={() => { setOpen(false); navigate(ctaTarget); toast.success(PRIMARY_CTA); }}\n"
        "              className=\"mt-2 rounded-[var(--radius)] bg-primary px-4 py-2 text-sm font-medium text-primary-foreground\"\n"
        "            >\n"
        "              {PRIMARY_CTA}\n"
        "            </button>\n"
        "          </nav>\n"
        "        </div>\n"
        "      )}\n"
        "    </header>\n"
        "  );\n"
        "}\n"
    )


# ---------------------------------------------------------------------------
# Helper: pre-built image URLs for archetype site.ts data modules
# ---------------------------------------------------------------------------

def _archetype_image_urls(plan: TemplatePlan, content: ContentPack) -> dict[str, str]:
    """Pre-render image URLs for image_subjects + pack item image subjects.

    Fetched in parallel via `_parallel_image_urls` so a 20-image archetype
    completes in seconds rather than blocking 60+ seconds sequentially.
    """
    specs: list[tuple[str, str, int, int, int]] = []
    seen: set[str] = set()
    for subject in plan.image_subjects:
        if subject in seen:
            continue
        specs.append((subject,
                      f"{subject}, professional photography, no text, no watermark",
                      1280, 720, _stable_seed(subject)))
        seen.add(subject)
    for item in plan.data_pack:
        subject = str(item.get("image_subject") or item.get("name") or item.get("title") or "").strip()
        if subject and subject not in seen:
            specs.append((subject,
                          f"{subject}, no text, no watermark",
                          960, 720, _stable_seed(subject)))
            seen.add(subject)
    return _parallel_image_urls(specs)


# ===========================================================================
# SaaS marketing archetype
# ===========================================================================

def scaffold_saas_page_project(
    brief: ProductBrief,
    design: DesignSystem,
    content: ContentPack,
    plan: TemplatePlan,
    brand: "Brand | None" = None,
) -> FileSet:
    pages = plan.pages or brief.pages
    if not pages:
        from .schemas import PageSpec
        pages = [PageSpec(name="Home", route="/", sections=["hero"], purpose="Landing page.")]

    nav = _resolve_navigation(plan, content, pages)
    image_urls = _archetype_image_urls(plan, content)
    page_routes = _normalize_routes(pages)
    data_ts = _saas_site_data_ts(plan, content, image_urls)

    files: list[GeneratedFile] = [
        GeneratedFile(path="package.json", content=_package_json(content)),
        GeneratedFile(path="tsconfig.json", content=_tsconfig()),
        GeneratedFile(path="public/index.html", content=_index_html(content)),
        GeneratedFile(path="src/index.tsx", content=_index_tsx()),
        GeneratedFile(path="src/styles.css", content=_scaffold_index_css(design)),
        GeneratedFile(path="src/lib/utils.ts", content=_utils_ts()),
        GeneratedFile(path="src/App.tsx", content=_app_tsx(page_routes, plan, content)),
        GeneratedFile(path="src/components/Layout.tsx", content=_layout_tsx()),
        GeneratedFile(path="src/components/Nav.tsx", content=_archetype_nav_tsx(
            nav, content, cta_route_keywords=["pricing", "start", "trial", "contact"],
        )),
        GeneratedFile(path="src/components/Footer.tsx", content=_footer_tsx(nav, content)),
        GeneratedFile(path="src/data/site.ts", content=data_ts),
    ]
    for page in page_routes:
        files.append(GeneratedFile(
            path=f"src/pages/{page['component']}.tsx",
            content=_saas_page_module(page),
        ))

    summary = (
        f"{content.brand_name or plan.template_label}: saas marketing · "
        f"{len(page_routes)} pages · multi-page router · open-lovable"
    )
    return FileSet(files=files, entry="public/index.html", summary=summary)


def _saas_site_data_ts(
    plan: TemplatePlan,
    content: ContentPack,
    image_urls: dict[str, str],
) -> str:
    from .content_catalog import get_pack
    features = plan.data_pack or get_pack("saas_features")
    plans_pack = get_pack("saas_plans")
    changelog_pack = get_pack("saas_changelog")
    feature_items = [
        {
            "title": str(f.get("title") or ""),
            "description": str(f.get("description") or ""),
            "icon": str(f.get("icon") or "Sparkles"),
            "image": image_urls.get(str(f.get("image_subject") or ""), ""),
        }
        for f in features
    ]
    site = {
        "brand": content.brand_name or plan.template_label,
        "tagline": content.tagline or "",
        "hero_headline": content.hero_headline or content.brand_name or plan.template_label,
        "hero_subhead": content.hero_subhead or "",
        "primary_cta": content.primary_cta or "Start free",
        "secondary_cta": content.secondary_cta or "View docs",
        "category": plan.category,
        "sub_niche": plan.sub_niche or "",
        "hero_image": (next(iter(image_urls.values()), "") if image_urls else ""),
        "logo_cloud": [
            "Stripe", "Notion", "Figma", "Vercel", "Linear", "Loom",
        ],
        "features": feature_items,
        "plans": plans_pack,
        "changelog": changelog_pack,
        "faqs": [
            {"question": "Is there a free trial?", "answer": "Yes — 14 days on the Team plan, no card required."},
            {"question": "Can I self-host?", "answer": "Yes. The single-binary distribution runs in your VPC."},
            {"question": "What's the SLA?", "answer": "99.99% on the Enterprise plan; 99.9% on Team."},
            {"question": "How does pricing work?", "answer": "Per-seat on Team. Custom for Enterprise."},
        ],
        "docs": [
            {"section": "Getting started", "links": ["Quickstart", "Install", "First project"]},
            {"section": "Guides",          "links": ["Workflows", "Permissions", "Webhooks"]},
            {"section": "Reference",       "links": ["REST API", "GraphQL", "CLI"]},
        ],
    }
    body = json.dumps(site, ensure_ascii=False, indent=2)
    return (
        "// SaaS site data — deterministic, derived from the Open Lovable plan.\n\n"
        "export type Feature = { title: string; description: string; icon: string; image: string };\n"
        "export type Plan = { name: string; price: string; period: string; description: string; features: string[]; cta_label: string; highlighted: boolean };\n"
        "export type ChangelogEntry = { date: string; title: string; body: string };\n"
        "export type Faq = { question: string; answer: string };\n"
        "export type DocsSection = { section: string; links: string[] };\n\n"
        f"const SITE = {body} as const;\n\n"
        "export default SITE;\n"
        "export const FEATURES: Feature[] = SITE.features as unknown as Feature[];\n"
        "export const PLANS: Plan[] = SITE.plans as unknown as Plan[];\n"
        "export const CHANGELOG: ChangelogEntry[] = SITE.changelog as unknown as ChangelogEntry[];\n"
        "export const FAQS: Faq[] = SITE.faqs as unknown as Faq[];\n"
        "export const DOCS: DocsSection[] = SITE.docs as unknown as DocsSection[];\n"
    )


def _saas_page_module(page: dict) -> str:
    comp = page["component"]
    name = page["name"]
    if comp == "Home":
        return _saas_home_tsx()
    lname = name.lower()
    if "feature" in lname:
        return _saas_features_tsx(comp, name)
    if "pricing" in lname:
        return _saas_pricing_tsx(comp, name)
    if "doc" in lname:
        return _saas_docs_tsx(comp, name)
    if "changelog" in lname:
        return _saas_changelog_tsx(comp, name)
    return _generic_page(comp, name, page.get("purpose", ""), page.get("sections", []))


def _saas_home_tsx() -> str:
    return (
        "import { Link } from 'react-router-dom';\n"
        "import { ArrowRight, Check } from 'lucide-react';\n"
        "import SITE, { FEATURES, PLANS } from '../data/site';\n\n"
        "export default function Home() {\n"
        "  const highlight = PLANS.find((p) => p.highlighted) || PLANS[0];\n"
        "  return (\n"
        "    <>\n"
        "      <section className=\"relative overflow-hidden\">\n"
        "        <div className=\"container mx-auto max-w-6xl px-6 py-28 text-center md:py-36\">\n"
        "          {SITE.tagline && <p className=\"mb-4 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{SITE.tagline}</p>}\n"
        "          <h1 className=\"mx-auto max-w-3xl animate-fade-up-1 font-display text-5xl font-bold leading-tight tracking-tight md:text-6xl\">{SITE.hero_headline}</h1>\n"
        "          {SITE.hero_subhead && <p className=\"mx-auto mt-6 max-w-2xl text-lg text-muted-foreground\">{SITE.hero_subhead}</p>}\n"
        "          <div className=\"mt-10 flex flex-wrap items-center justify-center gap-3\">\n"
        "            <Link to=\"/pricing\" className=\"inline-flex items-center gap-2 rounded-[var(--radius)] bg-primary px-6 py-3 text-base font-medium text-primary-foreground transition-opacity hover:opacity-90\">\n"
        "              {SITE.primary_cta} <ArrowRight className=\"h-4 w-4\" />\n"
        "            </Link>\n"
        "            <Link to=\"/docs\" className=\"inline-flex items-center gap-2 rounded-[var(--radius)] border border-border px-6 py-3 text-base font-medium transition-colors hover:bg-muted\">\n"
        "              {SITE.secondary_cta}\n"
        "            </Link>\n"
        "          </div>\n"
        "        </div>\n"
        "      </section>\n\n"
        "      {SITE.logo_cloud.length > 0 && (\n"
        "        <section className=\"border-y border-border bg-muted/20 py-10\">\n"
        "          <div className=\"container mx-auto max-w-6xl px-6\">\n"
        "            <p className=\"mb-6 text-center text-xs font-medium uppercase tracking-widest text-muted-foreground\">Teams shipping with {SITE.brand}</p>\n"
        "            <div className=\"flex flex-wrap items-center justify-center gap-x-10 gap-y-4 text-muted-foreground\">\n"
        "              {SITE.logo_cloud.map((l) => (\n"
        "                <span key={l} className=\"font-display text-lg opacity-70\">{l}</span>\n"
        "              ))}\n"
        "            </div>\n"
        "          </div>\n"
        "        </section>\n"
        "      )}\n\n"
        "      <section className=\"container mx-auto max-w-6xl px-6 py-20\">\n"
        "        <div className=\"mb-12 text-center\">\n"
        "          <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">Features</p>\n"
        "          <h2 className=\"font-display text-3xl font-bold tracking-tight md:text-4xl\">Built for serious teams</h2>\n"
        "        </div>\n"
        "        <div className=\"grid gap-6 md:grid-cols-2 lg:grid-cols-3\">\n"
        "          {FEATURES.slice(0, 6).map((f) => (\n"
        "            <div key={f.title} className=\"rounded-[var(--radius)] border border-border bg-card p-6 hover-lift transition-all hover:border-primary\">\n"
        "              <div className=\"mb-4 inline-flex h-10 w-10 items-center justify-center rounded-[var(--radius)] bg-primary/10 text-primary\">●</div>\n"
        "              <h3 className=\"mb-2 font-display text-lg font-semibold\">{f.title}</h3>\n"
        "              <p className=\"text-sm text-muted-foreground\">{f.description}</p>\n"
        "            </div>\n"
        "          ))}\n"
        "        </div>\n"
        "        <div className=\"mt-10 text-center\">\n"
        "          <Link to=\"/features\" className=\"inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline\">See all features <ArrowRight className=\"h-4 w-4\" /></Link>\n"
        "        </div>\n"
        "      </section>\n\n"
        "      {highlight && (\n"
        "        <section className=\"border-t border-border bg-muted/10 py-20\">\n"
        "          <div className=\"container mx-auto max-w-4xl px-6 text-center\">\n"
        "            <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">Popular plan</p>\n"
        "            <h2 className=\"font-display text-3xl font-bold tracking-tight md:text-4xl\">{highlight.name} · {highlight.price}<span className=\"text-base text-muted-foreground\">{highlight.period}</span></h2>\n"
        "            <p className=\"mx-auto mt-3 max-w-md text-muted-foreground\">{highlight.description}</p>\n"
        "            <ul className=\"mx-auto mt-8 grid max-w-xl gap-3 text-left text-sm sm:grid-cols-2\">\n"
        "              {highlight.features.map((f) => (\n"
        "                <li key={f} className=\"flex items-start gap-2\"><Check className=\"mt-0.5 h-4 w-4 flex-shrink-0 text-primary\" /><span>{f}</span></li>\n"
        "              ))}\n"
        "            </ul>\n"
        "            <Link to=\"/pricing\" className=\"mt-10 inline-flex items-center gap-2 rounded-[var(--radius)] bg-primary px-6 py-3 text-base font-medium text-primary-foreground transition-opacity hover:opacity-90\">\n"
        "              See full pricing <ArrowRight className=\"h-4 w-4\" />\n"
        "            </Link>\n"
        "          </div>\n"
        "        </section>\n"
        "      )}\n"
        "    </>\n"
        "  );\n"
        "}\n"
    )


def _saas_features_tsx(comp: str, name: str) -> str:
    return (
        "import { FEATURES } from '../data/site';\n\n"
        "export default function " + comp + "() {\n"
        "  return (\n"
        "    <section className=\"container mx-auto max-w-6xl px-6 py-20\">\n"
        f"      <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{name}</p>\n"
        "      <h1 className=\"font-display text-4xl font-bold tracking-tight md:text-5xl\">Everything in one place</h1>\n"
        "      <p className=\"mt-4 max-w-2xl text-muted-foreground\">A complete look at what ships in every workspace.</p>\n"
        "      <div className=\"mt-12 grid gap-6 md:grid-cols-2 lg:grid-cols-3\">\n"
        "        {FEATURES.map((f) => (\n"
        "          <article key={f.title} className=\"overflow-hidden rounded-[var(--radius)] border border-border bg-card hover-lift transition-all hover:border-primary\">\n"
        "            {f.image && <img src={f.image} alt={f.title} className=\"h-40 w-full object-cover opacity-90\" loading=\"lazy\" />}\n"
        "            <div className=\"p-6\">\n"
        "              <h3 className=\"font-display text-lg font-semibold\">{f.title}</h3>\n"
        "              <p className=\"mt-2 text-sm text-muted-foreground\">{f.description}</p>\n"
        "            </div>\n"
        "          </article>\n"
        "        ))}\n"
        "      </div>\n"
        "    </section>\n"
        "  );\n"
        "}\n"
    )


def _saas_pricing_tsx(comp: str, name: str) -> str:
    return (
        "import { useState } from 'react';\n"
        "import { Check } from 'lucide-react';\n"
        "import { toast } from 'sonner';\n"
        "import { PLANS, FAQS } from '../data/site';\n"
        "import { cn } from '../lib/utils';\n\n"
        "export default function " + comp + "() {\n"
        "  const [openIdx, setOpenIdx] = useState<number | null>(null);\n"
        "  return (\n"
        "    <section className=\"container mx-auto max-w-6xl px-6 py-20\">\n"
        f"      <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{name}</p>\n"
        "      <h1 className=\"font-display text-4xl font-bold tracking-tight md:text-5xl\">Pricing for every team</h1>\n"
        "      <p className=\"mt-4 max-w-2xl text-muted-foreground\">Start free. Upgrade when you grow.</p>\n"
        "      <div className=\"mt-12 grid gap-6 md:grid-cols-3\">\n"
        "        {PLANS.map((p) => (\n"
        "          <div key={p.name} className={cn('rounded-[var(--radius)] border bg-card p-8', p.highlighted ? 'border-primary shadow-lg ring-1 ring-primary' : 'border-border')}>\n"
        "            {p.highlighted && (<div className=\"mb-4 inline-flex rounded-full bg-primary px-3 py-1 text-xs font-medium text-primary-foreground\">Most popular</div>)}\n"
        "            <h3 className=\"font-display text-xl font-semibold\">{p.name}</h3>\n"
        "            <p className=\"mt-1 text-sm text-muted-foreground\">{p.description}</p>\n"
        "            <div className=\"mt-6 flex items-baseline gap-1\">\n"
        "              <span className=\"font-display text-4xl font-bold\">{p.price}</span>\n"
        "              {p.period && <span className=\"text-sm text-muted-foreground\">{p.period}</span>}\n"
        "            </div>\n"
        "            <button onClick={() => toast.success('Selected ' + p.name)} className={cn('mt-6 w-full rounded-[var(--radius)] px-4 py-3 text-sm font-medium transition-opacity', p.highlighted ? 'bg-primary text-primary-foreground hover:opacity-90' : 'border border-border hover:bg-muted')}>\n"
        "              {p.cta_label}\n"
        "            </button>\n"
        "            <ul className=\"mt-8 space-y-3\">\n"
        "              {p.features.map((f) => (\n"
        "                <li key={f} className=\"flex items-start gap-2 text-sm\"><Check className=\"mt-0.5 h-4 w-4 flex-shrink-0 text-primary\" /><span>{f}</span></li>\n"
        "              ))}\n"
        "            </ul>\n"
        "          </div>\n"
        "        ))}\n"
        "      </div>\n"
        "      {FAQS.length > 0 && (\n"
        "        <div className=\"mt-20\">\n"
        "          <h2 className=\"mb-8 font-display text-3xl font-bold tracking-tight\">Questions</h2>\n"
        "          <div className=\"space-y-3\">\n"
        "            {FAQS.map((f, i) => (\n"
        "              <div key={i} className=\"rounded-[var(--radius)] border border-border bg-card\">\n"
        "                <button onClick={() => setOpenIdx((c) => (c === i ? null : i))} className=\"flex w-full items-center justify-between gap-4 px-5 py-4 text-left text-sm font-medium hover:bg-muted/40\">\n"
        "                  <span>{f.question}</span>\n"
        "                  <span className=\"text-xs text-muted-foreground\">{openIdx === i ? '−' : '+'}</span>\n"
        "                </button>\n"
        "                {openIdx === i && (\n"
        "                  <div className=\"border-t border-border px-5 py-4 text-sm text-muted-foreground\">{f.answer}</div>\n"
        "                )}\n"
        "              </div>\n"
        "            ))}\n"
        "          </div>\n"
        "        </div>\n"
        "      )}\n"
        "    </section>\n"
        "  );\n"
        "}\n"
    )


def _saas_docs_tsx(comp: str, name: str) -> str:
    return (
        "import { useState } from 'react';\n"
        "import { DOCS } from '../data/site';\n"
        "import { cn } from '../lib/utils';\n\n"
        "export default function " + comp + "() {\n"
        "  const allLinks = DOCS.flatMap((s) => s.links);\n"
        "  const [active, setActive] = useState<string>(allLinks[0] || 'Quickstart');\n"
        "  return (\n"
        "    <section className=\"container mx-auto max-w-6xl px-6 py-20\">\n"
        f"      <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{name}</p>\n"
        "      <h1 className=\"font-display text-4xl font-bold tracking-tight md:text-5xl\">Documentation</h1>\n"
        "      <div className=\"mt-10 grid gap-10 md:grid-cols-[220px_1fr]\">\n"
        "        <aside>\n"
        "          {DOCS.map((s) => (\n"
        "            <div key={s.section} className=\"mb-6\">\n"
        "              <div className=\"mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground\">{s.section}</div>\n"
        "              <ul className=\"space-y-1\">\n"
        "                {s.links.map((l) => (\n"
        "                  <li key={l}>\n"
        "                    <button onClick={() => setActive(l)} className={cn('w-full rounded px-2 py-1 text-left text-sm transition-colors', active === l ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-muted hover:text-foreground')}>{l}</button>\n"
        "                  </li>\n"
        "                ))}\n"
        "              </ul>\n"
        "            </div>\n"
        "          ))}\n"
        "        </aside>\n"
        "        <article className=\"prose-sm max-w-none\">\n"
        "          <h2 className=\"mb-4 font-display text-2xl font-semibold\">{active}</h2>\n"
        "          <p className=\"text-muted-foreground\">This is a placeholder doc page rendered from the site data. Replace the body with real content via the data module at <code className=\"text-xs\">src/data/site.ts</code>.</p>\n"
        "          <pre className=\"mt-6 overflow-x-auto rounded-[var(--radius)] border border-border bg-muted p-4 text-xs\"><code>{'// Example\\nimport client from \"./client\";\\n\\nawait client.run({ project: \"acme\" });'}</code></pre>\n"
        "        </article>\n"
        "      </div>\n"
        "    </section>\n"
        "  );\n"
        "}\n"
    )


def _saas_changelog_tsx(comp: str, name: str) -> str:
    return (
        "import { CHANGELOG } from '../data/site';\n\n"
        "export default function " + comp + "() {\n"
        "  return (\n"
        "    <section className=\"container mx-auto max-w-3xl px-6 py-20\">\n"
        f"      <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{name}</p>\n"
        "      <h1 className=\"font-display text-4xl font-bold tracking-tight md:text-5xl\">What's new</h1>\n"
        "      <ol className=\"mt-12 space-y-10\">\n"
        "        {CHANGELOG.map((c) => (\n"
        "          <li key={c.date + c.title} className=\"border-l-2 border-border pl-6\">\n"
        "            <div className=\"text-xs font-medium uppercase tracking-wider text-muted-foreground\">{c.date}</div>\n"
        "            <h3 className=\"mt-1 font-display text-lg font-semibold\">{c.title}</h3>\n"
        "            <p className=\"mt-2 text-sm text-muted-foreground\">{c.body}</p>\n"
        "          </li>\n"
        "        ))}\n"
        "      </ol>\n"
        "    </section>\n"
        "  );\n"
        "}\n"
    )


# ===========================================================================
# Portfolio archetype
# ===========================================================================

def scaffold_portfolio_page_project(
    brief: ProductBrief,
    design: DesignSystem,
    content: ContentPack,
    plan: TemplatePlan,
    brand: "Brand | None" = None,
) -> FileSet:
    pages = plan.pages or brief.pages
    if not pages:
        from .schemas import PageSpec
        pages = [PageSpec(name="Home", route="/", sections=["hero"], purpose="Landing page.")]

    nav = _resolve_navigation(plan, content, pages)
    image_urls = _archetype_image_urls(plan, content)
    page_routes = _normalize_routes(pages)
    data_ts = _portfolio_site_data_ts(plan, content, image_urls)

    files: list[GeneratedFile] = [
        GeneratedFile(path="package.json", content=_package_json(content)),
        GeneratedFile(path="tsconfig.json", content=_tsconfig()),
        GeneratedFile(path="public/index.html", content=_index_html(content)),
        GeneratedFile(path="src/index.tsx", content=_index_tsx()),
        GeneratedFile(path="src/styles.css", content=_scaffold_index_css(design)),
        GeneratedFile(path="src/lib/utils.ts", content=_utils_ts()),
        GeneratedFile(path="src/App.tsx", content=_app_tsx(page_routes, plan, content)),
        GeneratedFile(path="src/components/Layout.tsx", content=_layout_tsx()),
        GeneratedFile(path="src/components/Nav.tsx", content=_archetype_nav_tsx(
            nav, content, cta_route_keywords=["contact", "work"],
        )),
        GeneratedFile(path="src/components/Footer.tsx", content=_footer_tsx(nav, content)),
        GeneratedFile(path="src/data/site.ts", content=data_ts),
    ]
    for page in page_routes:
        files.append(GeneratedFile(
            path=f"src/pages/{page['component']}.tsx",
            content=_portfolio_page_module(page),
        ))

    summary = (
        f"{content.brand_name or plan.template_label}: portfolio · "
        f"{len(page_routes)} pages · multi-page router · open-lovable"
    )
    return FileSet(files=files, entry="public/index.html", summary=summary)


def _portfolio_site_data_ts(
    plan: TemplatePlan,
    content: ContentPack,
    image_urls: dict[str, str],
) -> str:
    from .content_catalog import get_pack
    projects = plan.data_pack or get_pack("portfolio_projects")
    journal = get_pack("portfolio_journal")
    skills = get_pack("portfolio_skills")
    project_items = [
        {
            "title": str(p.get("title") or ""),
            "role": str(p.get("role") or ""),
            "year": str(p.get("year") or ""),
            "tags": [str(t) for t in (p.get("tags") or [])],
            "summary": str(p.get("summary") or ""),
            "image": image_urls.get(str(p.get("image_subject") or ""), ""),
        }
        for p in projects
    ]
    site = {
        "brand": content.brand_name or plan.template_label,
        "tagline": content.tagline or "Independent product design and engineering",
        "hero_headline": content.hero_headline or content.brand_name or plan.template_label,
        "hero_subhead": content.hero_subhead or "A quiet practice making considered software and brand work.",
        "primary_cta": content.primary_cta or "Get in touch",
        "secondary_cta": content.secondary_cta or "View work",
        "category": plan.category,
        "sub_niche": plan.sub_niche or "",
        "hero_image": (next(iter(image_urls.values()), "") if image_urls else ""),
        "projects": project_items,
        "journal": journal,
        "skills": skills,
        "bio": [
            "I design and build products that have to work in the real world — for regulated industries, for teams under pressure, for users who don't have time to learn another tool.",
            "Most recently I've focused on design systems and tooling that lets small teams move at large-team speed.",
            "Outside of work: typography, climbing, and rebuilding furniture badly.",
        ],
        "socials": [
            {"label": "Email",    "url": "mailto:hello@example.com"},
            {"label": "GitHub",   "url": "https://github.com/"},
            {"label": "Bluesky",  "url": "https://bsky.app/"},
            {"label": "Read.cv",  "url": "https://read.cv/"},
        ],
    }
    body = json.dumps(site, ensure_ascii=False, indent=2)
    return (
        "// Portfolio site data — deterministic, derived from the Open Lovable plan.\n\n"
        "export type Project = { title: string; role: string; year: string; tags: string[]; summary: string; image: string };\n"
        "export type JournalEntry = { date: string; title: string; summary: string; minutes: number };\n"
        "export type Skill = { label: string; level: string };\n"
        "export type Social = { label: string; url: string };\n\n"
        f"const SITE = {body} as const;\n\n"
        "export default SITE;\n"
        "export const PROJECTS: Project[] = SITE.projects as unknown as Project[];\n"
        "export const JOURNAL: JournalEntry[] = SITE.journal as unknown as JournalEntry[];\n"
        "export const SKILLS: Skill[] = SITE.skills as unknown as Skill[];\n"
        "export const SOCIALS: Social[] = SITE.socials as unknown as Social[];\n"
        "export const BIO: string[] = SITE.bio as unknown as string[];\n"
    )


def _portfolio_page_module(page: dict) -> str:
    comp = page["component"]
    name = page["name"]
    lname = name.lower()
    if comp == "Home":
        return _portfolio_home_tsx()
    if "work" in lname:
        return _portfolio_work_tsx(comp, name)
    if "about" in lname:
        return _portfolio_about_tsx(comp, name)
    if "journal" in lname or "blog" in lname:
        return _portfolio_journal_tsx(comp, name)
    if "contact" in lname:
        return _portfolio_contact_tsx(comp, name)
    return _generic_page(comp, name, page.get("purpose", ""), page.get("sections", []))


def _portfolio_home_tsx() -> str:
    return (
        "import { Link } from 'react-router-dom';\n"
        "import { ArrowRight } from 'lucide-react';\n"
        "import SITE, { PROJECTS } from '../data/site';\n\n"
        "export default function Home() {\n"
        "  const featured = PROJECTS.slice(0, 4);\n"
        "  return (\n"
        "    <>\n"
        "      <section className=\"container mx-auto max-w-5xl px-6 py-24 md:py-36\">\n"
        "        {SITE.tagline && <p className=\"mb-4 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{SITE.tagline}</p>}\n"
        "        <h1 className=\"max-w-3xl animate-fade-up-1 font-display text-5xl font-bold leading-tight tracking-tight md:text-7xl\">{SITE.hero_headline}</h1>\n"
        "        {SITE.hero_subhead && <p className=\"mt-6 max-w-2xl text-lg text-muted-foreground\">{SITE.hero_subhead}</p>}\n"
        "        <div className=\"mt-10 flex flex-wrap items-center gap-3\">\n"
        "          <Link to=\"/work\" className=\"inline-flex items-center gap-2 rounded-[var(--radius)] bg-primary px-6 py-3 text-base font-medium text-primary-foreground transition-opacity hover:opacity-90\">{SITE.secondary_cta} <ArrowRight className=\"h-4 w-4\" /></Link>\n"
        "          <Link to=\"/contact\" className=\"inline-flex items-center gap-2 rounded-[var(--radius)] border border-border px-6 py-3 text-base font-medium transition-colors hover:bg-muted\">{SITE.primary_cta}</Link>\n"
        "        </div>\n"
        "      </section>\n\n"
        "      <section className=\"container mx-auto max-w-6xl px-6 py-16\">\n"
        "        <div className=\"mb-10 flex items-end justify-between\">\n"
        "          <h2 className=\"font-display text-3xl font-bold tracking-tight md:text-4xl\">Selected work</h2>\n"
        "          <Link to=\"/work\" className=\"text-sm font-medium text-primary hover:underline\">All projects →</Link>\n"
        "        </div>\n"
        "        <div className=\"grid gap-8 md:grid-cols-2\">\n"
        "          {featured.map((p) => (\n"
        "            <article key={p.title} className=\"group\">\n"
        "              {p.image && <div className=\"mb-4 overflow-hidden rounded-[var(--radius)] border border-border\"><img src={p.image} alt={p.title} className=\"h-72 w-full object-cover transition-transform duration-500 group-hover:scale-105\" loading=\"lazy\" /></div>}\n"
        "              <div className=\"flex items-baseline justify-between gap-3\">\n"
        "                <h3 className=\"font-display text-xl font-semibold\">{p.title}</h3>\n"
        "                <span className=\"text-xs text-muted-foreground\">{p.year}</span>\n"
        "              </div>\n"
        "              <p className=\"mt-1 text-sm text-muted-foreground\">{p.role}</p>\n"
        "              <p className=\"mt-3 text-sm\">{p.summary}</p>\n"
        "            </article>\n"
        "          ))}\n"
        "        </div>\n"
        "      </section>\n"
        "    </>\n"
        "  );\n"
        "}\n"
    )


def _portfolio_work_tsx(comp: str, name: str) -> str:
    return (
        "import { PROJECTS } from '../data/site';\n\n"
        "export default function " + comp + "() {\n"
        "  return (\n"
        "    <section className=\"container mx-auto max-w-6xl px-6 py-20\">\n"
        f"      <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{name}</p>\n"
        "      <h1 className=\"font-display text-4xl font-bold tracking-tight md:text-5xl\">Projects</h1>\n"
        "      <div className=\"mt-12 space-y-16\">\n"
        "        {PROJECTS.map((p) => (\n"
        "          <article key={p.title} className=\"grid gap-8 md:grid-cols-[1fr_2fr] md:items-start\">\n"
        "            <div>\n"
        "              <h2 className=\"font-display text-2xl font-semibold\">{p.title}</h2>\n"
        "              <p className=\"mt-1 text-sm text-muted-foreground\">{p.role} · {p.year}</p>\n"
        "              <div className=\"mt-3 flex flex-wrap gap-2\">\n"
        "                {p.tags.map((t) => (\n"
        "                  <span key={t} className=\"rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground\">{t}</span>\n"
        "                ))}\n"
        "              </div>\n"
        "              <p className=\"mt-4 text-sm\">{p.summary}</p>\n"
        "            </div>\n"
        "            {p.image && (\n"
        "              <div className=\"overflow-hidden rounded-[var(--radius)] border border-border\">\n"
        "                <img src={p.image} alt={p.title} className=\"h-80 w-full object-cover\" loading=\"lazy\" />\n"
        "              </div>\n"
        "            )}\n"
        "          </article>\n"
        "        ))}\n"
        "      </div>\n"
        "    </section>\n"
        "  );\n"
        "}\n"
    )


def _portfolio_about_tsx(comp: str, name: str) -> str:
    return (
        "import { BIO, SKILLS } from '../data/site';\n\n"
        "export default function " + comp + "() {\n"
        "  return (\n"
        "    <section className=\"container mx-auto max-w-3xl px-6 py-20\">\n"
        f"      <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{name}</p>\n"
        "      <h1 className=\"font-display text-4xl font-bold tracking-tight md:text-5xl\">About</h1>\n"
        "      <div className=\"mt-10 space-y-5 text-muted-foreground\">\n"
        "        {BIO.map((p, i) => (<p key={i}>{p}</p>))}\n"
        "      </div>\n"
        "      <h2 className=\"mt-16 font-display text-xl font-semibold\">Skills</h2>\n"
        "      <div className=\"mt-4 flex flex-wrap gap-2\">\n"
        "        {SKILLS.map((s) => (\n"
        "          <span key={s.label} className=\"rounded-full border border-border bg-card px-3 py-1 text-xs\">\n"
        "            <span className=\"font-medium\">{s.label}</span>\n"
        "            <span className=\"ml-2 text-muted-foreground\">{s.level}</span>\n"
        "          </span>\n"
        "        ))}\n"
        "      </div>\n"
        "    </section>\n"
        "  );\n"
        "}\n"
    )


def _portfolio_journal_tsx(comp: str, name: str) -> str:
    return (
        "import { JOURNAL } from '../data/site';\n\n"
        "export default function " + comp + "() {\n"
        "  return (\n"
        "    <section className=\"container mx-auto max-w-3xl px-6 py-20\">\n"
        f"      <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{name}</p>\n"
        "      <h1 className=\"font-display text-4xl font-bold tracking-tight md:text-5xl\">Journal</h1>\n"
        "      <ul className=\"mt-12 space-y-8\">\n"
        "        {JOURNAL.map((j) => (\n"
        "          <li key={j.date + j.title} className=\"border-b border-border pb-8 last:border-0\">\n"
        "            <div className=\"text-xs font-medium uppercase tracking-wider text-muted-foreground\">{j.date} · {j.minutes} min read</div>\n"
        "            <h2 className=\"mt-2 font-display text-xl font-semibold\">{j.title}</h2>\n"
        "            <p className=\"mt-2 text-sm text-muted-foreground\">{j.summary}</p>\n"
        "          </li>\n"
        "        ))}\n"
        "      </ul>\n"
        "    </section>\n"
        "  );\n"
        "}\n"
    )


def _portfolio_contact_tsx(comp: str, name: str) -> str:
    return (
        "import { FormEvent, useState } from 'react';\n"
        "import { toast } from 'sonner';\n"
        "import { SOCIALS } from '../data/site';\n\n"
        "export default function " + comp + "() {\n"
        "  const [email, setEmail] = useState('');\n"
        "  const [message, setMessage] = useState('');\n"
        "  function onSubmit(e: FormEvent) {\n"
        "    e.preventDefault();\n"
        "    if (!email.trim() || !message.trim()) { toast.error('Please add an email and message'); return; }\n"
        "    toast.success('Thanks — replying within a few days.');\n"
        "    setEmail(''); setMessage('');\n"
        "  }\n"
        "  return (\n"
        "    <section className=\"container mx-auto max-w-3xl px-6 py-20\">\n"
        f"      <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{name}</p>\n"
        "      <h1 className=\"font-display text-4xl font-bold tracking-tight md:text-5xl\">Get in touch</h1>\n"
        "      <p className=\"mt-4 text-muted-foreground\">For project enquiries, collaborations, or a quiet hello.</p>\n"
        "      <form onSubmit={onSubmit} className=\"mt-10 space-y-4 rounded-[var(--radius)] border border-border bg-card p-6\">\n"
        "        <label className=\"block text-sm\">Email\n"
        "          <input type=\"email\" value={email} onChange={(e) => setEmail(e.target.value)} className=\"mt-2 w-full rounded-[var(--radius)] border border-border bg-background px-3 py-2 text-sm\" />\n"
        "        </label>\n"
        "        <label className=\"block text-sm\">Message\n"
        "          <textarea value={message} onChange={(e) => setMessage(e.target.value)} rows={5} className=\"mt-2 w-full rounded-[var(--radius)] border border-border bg-background px-3 py-2 text-sm\" />\n"
        "        </label>\n"
        "        <button type=\"submit\" className=\"rounded-[var(--radius)] bg-primary px-5 py-3 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90\">Send</button>\n"
        "      </form>\n"
        "      <ul className=\"mt-10 flex flex-wrap gap-x-6 gap-y-2 text-sm text-muted-foreground\">\n"
        "        {SOCIALS.map((s) => (\n"
        "          <li key={s.label}><a href={s.url} className=\"hover:text-foreground\">{s.label} →</a></li>\n"
        "        ))}\n"
        "      </ul>\n"
        "    </section>\n"
        "  );\n"
        "}\n"
    )


# ===========================================================================
# Ecommerce archetype
# ===========================================================================

def scaffold_ecommerce_page_project(
    brief: ProductBrief,
    design: DesignSystem,
    content: ContentPack,
    plan: TemplatePlan,
    brand: "Brand | None" = None,
) -> FileSet:
    pages = plan.pages or brief.pages
    if not pages:
        from .schemas import PageSpec
        pages = [PageSpec(name="Home", route="/", sections=["hero"], purpose="Landing page.")]

    nav = _resolve_navigation(plan, content, pages)
    image_urls = _archetype_image_urls(plan, content)
    page_routes = _normalize_routes(pages)
    data_ts = _ecommerce_site_data_ts(plan, content, image_urls)

    files: list[GeneratedFile] = [
        GeneratedFile(path="package.json", content=_package_json(content)),
        GeneratedFile(path="tsconfig.json", content=_tsconfig()),
        GeneratedFile(path="public/index.html", content=_index_html(content)),
        GeneratedFile(path="src/index.tsx", content=_index_tsx()),
        GeneratedFile(path="src/styles.css", content=_scaffold_index_css(design)),
        GeneratedFile(path="src/lib/utils.ts", content=_utils_ts()),
        # Custom App.tsx wraps everything in CartProvider so useCart() works
        # in every page module without each page importing the provider.
        GeneratedFile(path="src/App.tsx", content=_ecommerce_app_tsx(page_routes)),
        GeneratedFile(path="src/components/Layout.tsx", content=_layout_tsx()),
        GeneratedFile(path="src/components/Nav.tsx", content=_archetype_nav_tsx(
            nav, content, cta_route_keywords=["cart", "shop", "checkout"],
        )),
        GeneratedFile(path="src/components/Footer.tsx", content=_footer_tsx(nav, content)),
        GeneratedFile(path="src/data/site.ts", content=data_ts),
        GeneratedFile(path="src/context/CartContext.tsx", content=_cart_context_tsx()),
    ]
    for page in page_routes:
        files.append(GeneratedFile(
            path=f"src/pages/{page['component']}.tsx",
            content=_ecommerce_page_module(page),
        ))

    summary = (
        f"{content.brand_name or plan.template_label}: ecommerce · "
        f"{len(page_routes)} pages · multi-page router · open-lovable"
    )
    return FileSet(files=files, entry="public/index.html", summary=summary)


def _ecommerce_app_tsx(pages: list[dict]) -> str:
    """App.tsx that wraps Routes in CartProvider so useCart() is always available."""
    imports = "\n".join(
        f"import {p['component']} from './pages/{p['component']}';"
        for p in pages
    )
    routes = "\n          ".join(
        f"<Route path={json.dumps(p['route'])} element={{<{p['component']} />}} />"
        for p in pages
    )
    fallback = pages[0]["component"]
    return (
        "import { Routes, Route } from 'react-router-dom';\n"
        "import Layout from './components/Layout';\n"
        "import { CartProvider } from './context/CartContext';\n"
        f"{imports}\n\n"
        "export default function App() {\n"
        "  return (\n"
        "    <CartProvider>\n"
        "      <Layout>\n"
        "        <Routes>\n"
        f"          {routes}\n"
        f"          <Route path=\"*\" element={{<{fallback} />}} />\n"
        "        </Routes>\n"
        "      </Layout>\n"
        "    </CartProvider>\n"
        "  );\n"
        "}\n"
    )


def _ecommerce_site_data_ts(
    plan: TemplatePlan,
    content: ContentPack,
    image_urls: dict[str, str],
) -> str:
    from .content_catalog import get_pack
    products_pack = plan.data_pack or get_pack("fashion_products")
    products = [
        {
            "id": _slugify(str(p.get("name") or f"item-{i}")) or f"item-{i}",
            "name": str(p.get("name") or ""),
            "price": str(p.get("price") or ""),
            "category": str(p.get("category") or "Catalog"),
            "sizes": [str(s) for s in (p.get("sizes") or [])],
            "image": image_urls.get(str(p.get("image_subject") or p.get("name") or ""), ""),
        }
        for i, p in enumerate(products_pack)
    ]
    lookbook = [{"subject": s, "image": image_urls.get(s, "")} for s in plan.image_subjects]
    site = {
        "brand": content.brand_name or plan.template_label,
        "tagline": content.tagline or "Considered pieces, made to last.",
        "hero_headline": content.hero_headline or content.brand_name or plan.template_label,
        "hero_subhead": content.hero_subhead or "A small atelier, two seasonal collections a year.",
        "primary_cta": content.primary_cta or "Shop the collection",
        "secondary_cta": content.secondary_cta or "View lookbook",
        "category": plan.category,
        "sub_niche": plan.sub_niche or "",
        "hero_image": (next(iter(image_urls.values()), "") if image_urls else ""),
        "products": products,
        "lookbook": lookbook,
        "press": [
            {"outlet": "Magazine A", "quote": "Quietly assured."},
            {"outlet": "Outlet B",   "quote": "A welcome counterpoint to fast fashion."},
            {"outlet": "Outlet C",   "quote": "Pieces that age well."},
        ],
        "story": [
            "We started in a small studio with a single sewing machine and a long-running argument about hems.",
            "Today we work with two family-run mills in Portugal and a finisher in Lisbon. The collection stays small on purpose.",
        ],
    }
    body = json.dumps(site, ensure_ascii=False, indent=2)
    return (
        "// Ecommerce site data — deterministic, derived from the Open Lovable plan.\n\n"
        "export type Product = { id: string; name: string; price: string; category: string; sizes: string[]; image: string };\n"
        "export type LookbookEntry = { subject: string; image: string };\n"
        "export type PressMention = { outlet: string; quote: string };\n\n"
        f"const SITE = {body} as const;\n\n"
        "export default SITE;\n"
        "export const PRODUCTS: Product[] = SITE.products as unknown as Product[];\n"
        "export const LOOKBOOK: LookbookEntry[] = SITE.lookbook as unknown as LookbookEntry[];\n"
        "export const PRESS: PressMention[] = SITE.press as unknown as PressMention[];\n"
        "export const STORY: string[] = SITE.story as unknown as string[];\n"
    )


def _cart_context_tsx() -> str:
    return """import { createContext, useContext, useMemo, useState, ReactNode } from 'react';
import type { Product } from '../data/site';

export type CartItem = { product: Product; qty: number };

type CartContextValue = {
  items: CartItem[];
  add: (p: Product) => void;
  remove: (id: string) => void;
  setQty: (id: string, qty: number) => void;
  clear: () => void;
  count: number;
  totalText: string;
};

const CartContext = createContext<CartContextValue | null>(null);

function priceToNumber(price: string): number {
  const m = price.replace(/[^0-9.]/g, '');
  const n = parseFloat(m);
  return Number.isFinite(n) ? n : 0;
}

export function CartProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<CartItem[]>([]);
  const value = useMemo<CartContextValue>(() => ({
    items,
    add: (p) => setItems((prev) => {
      const i = prev.findIndex((x) => x.product.id === p.id);
      if (i >= 0) {
        const next = [...prev];
        next[i] = { ...next[i], qty: next[i].qty + 1 };
        return next;
      }
      return [...prev, { product: p, qty: 1 }];
    }),
    remove: (id) => setItems((prev) => prev.filter((x) => x.product.id !== id)),
    setQty: (id, qty) => setItems((prev) => prev.map((x) => x.product.id === id ? { ...x, qty: Math.max(1, qty) } : x)),
    clear: () => setItems([]),
    count: items.reduce((s, x) => s + x.qty, 0),
    totalText: '$' + items.reduce((s, x) => s + priceToNumber(x.product.price) * x.qty, 0).toFixed(2),
  }), [items]);
  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart() {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error('useCart must be inside CartProvider');
  return ctx;
}
"""


def _ecommerce_page_module(page: dict) -> str:
    comp = page["component"]
    name = page["name"]
    lname = name.lower()
    if comp == "Home":
        return _ecommerce_home_tsx()
    if "shop" in lname:
        return _ecommerce_shop_tsx(comp, name)
    if "product" in lname:
        return _ecommerce_product_tsx(comp, name)
    if "cart" in lname:
        return _ecommerce_cart_tsx(comp, name)
    if "lookbook" in lname:
        return _ecommerce_lookbook_tsx(comp, name)
    if "about" in lname:
        return _ecommerce_about_tsx(comp, name)
    return _generic_page(comp, name, page.get("purpose", ""), page.get("sections", []))


def _ecommerce_home_tsx() -> str:
    return (
        "import { Link } from 'react-router-dom';\n"
        "import { ArrowRight } from 'lucide-react';\n"
        "import SITE, { PRODUCTS, PRESS } from '../data/site';\n\n"
        "export default function Home() {\n"
        "  const featured = PRODUCTS.slice(0, 4);\n"
        "  return (\n"
        "    <>\n"
        "      <section className=\"relative overflow-hidden\">\n"
        "        {SITE.hero_image && (<img src={SITE.hero_image} alt=\"\" className=\"absolute inset-0 h-full w-full object-cover opacity-25\" />)}\n"
        "        <div className=\"relative container mx-auto max-w-6xl px-6 py-32 text-center\">\n"
        "          {SITE.tagline && <p className=\"mb-4 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{SITE.tagline}</p>}\n"
        "          <h1 className=\"mx-auto max-w-3xl animate-fade-up-1 font-display text-5xl font-bold leading-tight tracking-tight md:text-7xl\">{SITE.hero_headline}</h1>\n"
        "          {SITE.hero_subhead && <p className=\"mx-auto mt-6 max-w-2xl text-lg text-muted-foreground\">{SITE.hero_subhead}</p>}\n"
        "          <div className=\"mt-10 flex flex-wrap items-center justify-center gap-3\">\n"
        "            <Link to=\"/shop\" className=\"inline-flex items-center gap-2 rounded-[var(--radius)] bg-primary px-6 py-3 text-base font-medium text-primary-foreground transition-opacity hover:opacity-90\">{SITE.primary_cta} <ArrowRight className=\"h-4 w-4\" /></Link>\n"
        "            <Link to=\"/lookbook\" className=\"inline-flex items-center gap-2 rounded-[var(--radius)] border border-border px-6 py-3 text-base font-medium transition-colors hover:bg-muted\">{SITE.secondary_cta}</Link>\n"
        "          </div>\n"
        "        </div>\n"
        "      </section>\n\n"
        "      <section className=\"container mx-auto max-w-6xl px-6 py-20\">\n"
        "        <div className=\"mb-10 flex items-end justify-between\">\n"
        "          <h2 className=\"font-display text-3xl font-bold tracking-tight md:text-4xl\">Featured collection</h2>\n"
        "          <Link to=\"/shop\" className=\"text-sm font-medium text-primary hover:underline\">All pieces →</Link>\n"
        "        </div>\n"
        "        <div className=\"grid gap-6 sm:grid-cols-2 lg:grid-cols-4\">\n"
        "          {featured.map((p) => (\n"
        "            <Link key={p.id} to=\"/product\" className=\"group block\">\n"
        "              {p.image && <div className=\"mb-3 aspect-[3/4] overflow-hidden rounded-[var(--radius)] border border-border\"><img src={p.image} alt={p.name} className=\"h-full w-full object-cover transition-transform duration-500 group-hover:scale-105\" loading=\"lazy\" /></div>}\n"
        "              <div className=\"flex items-baseline justify-between gap-3\">\n"
        "                <h3 className=\"text-sm font-medium\">{p.name}</h3>\n"
        "                <span className=\"text-sm text-muted-foreground\">{p.price}</span>\n"
        "              </div>\n"
        "            </Link>\n"
        "          ))}\n"
        "        </div>\n"
        "      </section>\n\n"
        "      {PRESS.length > 0 && (\n"
        "        <section className=\"border-y border-border bg-muted/20 py-16\">\n"
        "          <div className=\"container mx-auto max-w-6xl px-6\">\n"
        "            <div className=\"grid gap-8 md:grid-cols-3\">\n"
        "              {PRESS.map((p) => (\n"
        "                <figure key={p.outlet} className=\"text-center\">\n"
        "                  <blockquote className=\"font-display text-xl italic\">&ldquo;{p.quote}&rdquo;</blockquote>\n"
        "                  <figcaption className=\"mt-3 text-xs font-medium uppercase tracking-wider text-muted-foreground\">— {p.outlet}</figcaption>\n"
        "                </figure>\n"
        "              ))}\n"
        "            </div>\n"
        "          </div>\n"
        "        </section>\n"
        "      )}\n"
        "    </>\n"
        "  );\n"
        "}\n"
    )


def _ecommerce_shop_tsx(comp: str, name: str) -> str:
    return (
        "import { useMemo, useState } from 'react';\n"
        "import { toast } from 'sonner';\n"
        "import { PRODUCTS } from '../data/site';\n"
        "import { useCart } from '../context/CartContext';\n\n"
        "export default function " + comp + "() {\n"
        "  const cart = useCart();\n"
        "  const categories = useMemo(() => {\n"
        "    const s = new Set<string>();\n"
        "    PRODUCTS.forEach((p) => s.add(p.category));\n"
        "    return ['All', ...Array.from(s)];\n"
        "  }, []);\n"
        "  const [active, setActive] = useState<string>('All');\n"
        "  const items = active === 'All' ? PRODUCTS : PRODUCTS.filter((p) => p.category === active);\n"
        "  return (\n"
        "    <section className=\"container mx-auto max-w-6xl px-6 py-20\">\n"
        f"      <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{name}</p>\n"
        "      <h1 className=\"font-display text-4xl font-bold tracking-tight md:text-5xl\">Shop the collection</h1>\n"
        "      <div className=\"mt-8 flex flex-wrap gap-2\">\n"
        "        {categories.map((c) => (\n"
        "          <button key={c} onClick={() => setActive(c)} className={'rounded-full border px-4 py-2 text-sm transition-colors ' + (active === c ? 'border-primary bg-primary text-primary-foreground' : 'border-border hover:bg-muted')}>{c}</button>\n"
        "        ))}\n"
        "      </div>\n"
        "      <div className=\"mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3\">\n"
        "        {items.map((p) => (\n"
        "          <article key={p.id} className=\"group overflow-hidden rounded-[var(--radius)] border border-border bg-card\">\n"
        "            {p.image && <div className=\"aspect-[4/5] overflow-hidden\"><img src={p.image} alt={p.name} className=\"h-full w-full object-cover transition-transform duration-500 group-hover:scale-105\" loading=\"lazy\" /></div>}\n"
        "            <div className=\"p-5\">\n"
        "              <div className=\"flex items-baseline justify-between gap-3\">\n"
        "                <h3 className=\"font-display text-base font-semibold\">{p.name}</h3>\n"
        "                <span className=\"text-sm font-medium text-primary\">{p.price}</span>\n"
        "              </div>\n"
        "              <p className=\"mt-1 text-xs uppercase tracking-wider text-muted-foreground\">{p.category}</p>\n"
        "              <button onClick={() => { cart.add(p); toast.success(p.name + ' added to cart'); }} className=\"mt-4 w-full rounded-[var(--radius)] border border-border px-3 py-2 text-sm font-medium transition-colors hover:bg-primary hover:text-primary-foreground\">\n"
        "                Add to cart\n"
        "              </button>\n"
        "            </div>\n"
        "          </article>\n"
        "        ))}\n"
        "      </div>\n"
        "    </section>\n"
        "  );\n"
        "}\n"
    )


def _ecommerce_product_tsx(comp: str, name: str) -> str:
    return (
        "import { useState } from 'react';\n"
        "import { toast } from 'sonner';\n"
        "import { Link } from 'react-router-dom';\n"
        "import { PRODUCTS } from '../data/site';\n"
        "import { useCart } from '../context/CartContext';\n\n"
        "export default function " + comp + "() {\n"
        "  const product = PRODUCTS[0];\n"
        "  const cart = useCart();\n"
        "  const [size, setSize] = useState<string>(product?.sizes?.[0] || 'One size');\n"
        "  if (!product) return <p className=\"container mx-auto max-w-6xl px-6 py-20 text-muted-foreground\">No products yet.</p>;\n"
        "  return (\n"
        "    <section className=\"container mx-auto max-w-6xl px-6 py-20\">\n"
        f"      <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{name}</p>\n"
        "      <div className=\"grid gap-10 md:grid-cols-2\">\n"
        "        {product.image && (<div className=\"overflow-hidden rounded-[var(--radius)] border border-border\"><img src={product.image} alt={product.name} className=\"h-full w-full object-cover\" loading=\"lazy\" /></div>)}\n"
        "        <div>\n"
        "          <p className=\"text-xs uppercase tracking-wider text-muted-foreground\">{product.category}</p>\n"
        "          <h1 className=\"mt-2 font-display text-4xl font-bold tracking-tight\">{product.name}</h1>\n"
        "          <p className=\"mt-3 text-2xl font-medium text-primary\">{product.price}</p>\n"
        "          {product.sizes.length > 0 && (\n"
        "            <div className=\"mt-8\">\n"
        "              <div className=\"mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground\">Size</div>\n"
        "              <div className=\"flex flex-wrap gap-2\">\n"
        "                {product.sizes.map((s) => (\n"
        "                  <button key={s} onClick={() => setSize(s)} className={'rounded-[var(--radius)] border px-4 py-2 text-sm transition-colors ' + (size === s ? 'border-primary bg-primary text-primary-foreground' : 'border-border hover:bg-muted')}>{s}</button>\n"
        "                ))}\n"
        "              </div>\n"
        "            </div>\n"
        "          )}\n"
        "          <button onClick={() => { cart.add(product); toast.success(product.name + ' added to cart'); }} className=\"mt-10 w-full rounded-[var(--radius)] bg-primary px-5 py-3 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 md:w-auto\">\n"
        "            Add to cart\n"
        "          </button>\n"
        "          <Link to=\"/cart\" className=\"ml-3 inline-block text-sm font-medium text-primary hover:underline\">View cart ({cart.count})</Link>\n"
        "        </div>\n"
        "      </div>\n"
        "    </section>\n"
        "  );\n"
        "}\n"
    )


def _ecommerce_cart_tsx(comp: str, name: str) -> str:
    return (
        "import { toast } from 'sonner';\n"
        "import { Link } from 'react-router-dom';\n"
        "import { useCart } from '../context/CartContext';\n\n"
        "export default function " + comp + "() {\n"
        "  const cart = useCart();\n"
        "  function checkout() {\n"
        "    if (cart.items.length === 0) { toast.error('Your cart is empty'); return; }\n"
        "    toast.success('Order placed · ' + cart.totalText);\n"
        "    cart.clear();\n"
        "  }\n"
        "  return (\n"
        "    <section className=\"container mx-auto max-w-3xl px-6 py-20\">\n"
        f"      <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{name}</p>\n"
        "      <h1 className=\"font-display text-4xl font-bold tracking-tight md:text-5xl\">Your bag</h1>\n"
        "      {cart.items.length === 0 ? (\n"
        "        <p className=\"mt-10 text-muted-foreground\">Your bag is empty. <Link to=\"/shop\" className=\"text-primary hover:underline\">Browse the shop →</Link></p>\n"
        "      ) : (\n"
        "        <>\n"
        "          <ul className=\"mt-10 divide-y divide-border rounded-[var(--radius)] border border-border bg-card\">\n"
        "            {cart.items.map((it) => (\n"
        "              <li key={it.product.id} className=\"flex items-center gap-4 p-4\">\n"
        "                {it.product.image && <img src={it.product.image} alt={it.product.name} className=\"h-20 w-16 rounded-[var(--radius)] object-cover\" />}\n"
        "                <div className=\"flex-1\">\n"
        "                  <div className=\"flex items-baseline justify-between gap-3\">\n"
        "                    <div className=\"text-sm font-medium\">{it.product.name}</div>\n"
        "                    <div className=\"text-sm\">{it.product.price}</div>\n"
        "                  </div>\n"
        "                  <div className=\"mt-2 flex items-center gap-3 text-sm\">\n"
        "                    <button onClick={() => cart.setQty(it.product.id, it.qty - 1)} className=\"rounded border border-border px-2\">−</button>\n"
        "                    <span className=\"w-6 text-center\">{it.qty}</span>\n"
        "                    <button onClick={() => cart.setQty(it.product.id, it.qty + 1)} className=\"rounded border border-border px-2\">+</button>\n"
        "                    <button onClick={() => cart.remove(it.product.id)} className=\"ml-auto text-xs text-muted-foreground hover:text-foreground\">Remove</button>\n"
        "                  </div>\n"
        "                </div>\n"
        "              </li>\n"
        "            ))}\n"
        "          </ul>\n"
        "          <div className=\"mt-8 flex items-center justify-between border-t border-border pt-6\">\n"
        "            <div className=\"text-sm text-muted-foreground\">Subtotal</div>\n"
        "            <div className=\"font-display text-2xl font-semibold\">{cart.totalText}</div>\n"
        "          </div>\n"
        "          <button onClick={checkout} className=\"mt-8 w-full rounded-[var(--radius)] bg-primary px-5 py-3 text-base font-medium text-primary-foreground transition-opacity hover:opacity-90\">Check out</button>\n"
        "        </>\n"
        "      )}\n"
        "    </section>\n"
        "  );\n"
        "}\n"
    )


def _ecommerce_lookbook_tsx(comp: str, name: str) -> str:
    return (
        "import { LOOKBOOK } from '../data/site';\n\n"
        "export default function " + comp + "() {\n"
        "  return (\n"
        "    <section className=\"container mx-auto max-w-6xl px-6 py-20\">\n"
        f"      <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{name}</p>\n"
        "      <h1 className=\"font-display text-4xl font-bold tracking-tight md:text-5xl\">Lookbook</h1>\n"
        "      <div className=\"mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3\">\n"
        "        {LOOKBOOK.map((l) => (\n"
        "          <figure key={l.subject} className=\"overflow-hidden rounded-[var(--radius)] border border-border\">\n"
        "            {l.image && <img src={l.image} alt={l.subject} className=\"h-80 w-full object-cover transition-transform duration-500 hover:scale-105\" loading=\"lazy\" />}\n"
        "            <figcaption className=\"px-4 py-3 text-xs text-muted-foreground capitalize\">{l.subject}</figcaption>\n"
        "          </figure>\n"
        "        ))}\n"
        "      </div>\n"
        "    </section>\n"
        "  );\n"
        "}\n"
    )


def _ecommerce_about_tsx(comp: str, name: str) -> str:
    return (
        "import SITE, { STORY } from '../data/site';\n\n"
        "export default function " + comp + "() {\n"
        "  return (\n"
        "    <section className=\"container mx-auto max-w-3xl px-6 py-20\">\n"
        f"      <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{name}</p>\n"
        "      <h1 className=\"font-display text-4xl font-bold tracking-tight md:text-5xl\">The story behind {SITE.brand}</h1>\n"
        "      <div className=\"mt-10 space-y-5 text-muted-foreground\">\n"
        "        {STORY.map((p, i) => (<p key={i}>{p}</p>))}\n"
        "      </div>\n"
        "    </section>\n"
        "  );\n"
        "}\n"
    )


# ===========================================================================
# Healthcare archetype
# ===========================================================================

def scaffold_healthcare_page_project(
    brief: ProductBrief,
    design: DesignSystem,
    content: ContentPack,
    plan: TemplatePlan,
    brand: "Brand | None" = None,
) -> FileSet:
    pages = plan.pages or brief.pages
    if not pages:
        from .schemas import PageSpec
        pages = [PageSpec(name="Home", route="/", sections=["hero"], purpose="Landing page.")]

    nav = _resolve_navigation(plan, content, pages)
    image_urls = _archetype_image_urls(plan, content)
    page_routes = _normalize_routes(pages)
    data_ts = _healthcare_site_data_ts(plan, content, image_urls)

    files: list[GeneratedFile] = [
        GeneratedFile(path="package.json", content=_package_json(content)),
        GeneratedFile(path="tsconfig.json", content=_tsconfig()),
        GeneratedFile(path="public/index.html", content=_index_html(content)),
        GeneratedFile(path="src/index.tsx", content=_index_tsx()),
        GeneratedFile(path="src/styles.css", content=_scaffold_index_css(design)),
        GeneratedFile(path="src/lib/utils.ts", content=_utils_ts()),
        GeneratedFile(path="src/App.tsx", content=_app_tsx(page_routes, plan, content)),
        GeneratedFile(path="src/components/Layout.tsx", content=_layout_tsx()),
        GeneratedFile(path="src/components/Nav.tsx", content=_archetype_nav_tsx(
            nav, content, cta_route_keywords=["booking", "appointment", "contact"],
        )),
        GeneratedFile(path="src/components/Footer.tsx", content=_footer_tsx(nav, content)),
        GeneratedFile(path="src/data/site.ts", content=data_ts),
    ]
    for page in page_routes:
        files.append(GeneratedFile(
            path=f"src/pages/{page['component']}.tsx",
            content=_healthcare_page_module(page),
        ))

    summary = (
        f"{content.brand_name or plan.template_label}: healthcare · "
        f"{len(page_routes)} pages · multi-page router · open-lovable"
    )
    return FileSet(files=files, entry="public/index.html", summary=summary)


def _healthcare_site_data_ts(
    plan: TemplatePlan,
    content: ContentPack,
    image_urls: dict[str, str],
) -> str:
    from .content_catalog import get_pack
    services_pack = plan.data_pack or get_pack("healthcare_services")
    doctors_pack = get_pack("healthcare_doctors")
    testimonials_pack = get_pack("healthcare_testimonials")
    services = [
        {
            "title": str(s.get("title") or ""),
            "description": str(s.get("description") or ""),
            "icon": str(s.get("icon") or "Heart"),
            "image": image_urls.get(str(s.get("image_subject") or ""), ""),
        }
        for s in services_pack
    ]
    doctors = [
        {
            "name": str(d.get("name") or ""),
            "role": str(d.get("role") or ""),
            "credentials": str(d.get("credentials") or ""),
            "bio": str(d.get("bio") or ""),
            "image": image_urls.get(str(d.get("image_subject") or d.get("name") or ""), ""),
        }
        for d in doctors_pack
    ]
    site = {
        "brand": content.brand_name or plan.template_label,
        "tagline": content.tagline or "Care that listens",
        "hero_headline": content.hero_headline or content.brand_name or plan.template_label,
        "hero_subhead": content.hero_subhead or "Modern, evidence-based care for you and the people who depend on you.",
        "primary_cta": content.primary_cta or "Book an appointment",
        "secondary_cta": content.secondary_cta or "Meet the team",
        "category": plan.category,
        "sub_niche": plan.sub_niche or "",
        "hero_image": (next(iter(image_urls.values()), "") if image_urls else ""),
        "services": services,
        "doctors": doctors,
        "testimonials": testimonials_pack,
        "hours": [
            {"day": "Mon – Fri", "time": "8:00 AM – 6:00 PM"},
            {"day": "Saturday",       "time": "9:00 AM – 1:00 PM"},
            {"day": "Sunday",         "time": "Closed (telehealth available)"},
        ],
        "address": "215 Cedar Avenue, Suite 300",
        "phone": "(555) 234-1100",
        "email": _derive_healthcare_email(content),
        "mission": [
            "We exist because the simple act of being heard by a clinician shouldn't be rare.",
            "Our practice is small on purpose. Every clinician here picks up their own messages, knows their patients by name, and books enough time per visit to actually listen.",
            "We use modern tools — secure messaging, telehealth, online booking — because they remove friction, not because they're trendy.",
        ],
        "values": [
            {"label": "Listen first", "body": "Every visit starts with the patient's story, not a checklist."},
            {"label": "Plain language", "body": "We explain in words, not jargon. You leave knowing what's next."},
            {"label": "Same-day access", "body": "Same-day visits or telehealth for anything that can't wait."},
            {"label": "No surprise bills", "body": "Prices are posted. Insurance is verified before you book."},
        ],
    }
    body = json.dumps(site, ensure_ascii=False, indent=2)
    return (
        "// Healthcare site data — deterministic, from the Open Lovable plan.\n\n"
        "export type Service = { title: string; description: string; icon: string; image: string };\n"
        "export type Doctor = { name: string; role: string; credentials: string; bio: string; image: string };\n"
        "export type Testimonial = { quote: string; author: string; role: string };\n"
        "export type Hour = { day: string; time: string };\n"
        "export type Value = { label: string; body: string };\n\n"
        f"const SITE = {body} as const;\n\n"
        "export default SITE;\n"
        "export const SERVICES: Service[] = SITE.services as unknown as Service[];\n"
        "export const DOCTORS: Doctor[] = SITE.doctors as unknown as Doctor[];\n"
        "export const TESTIMONIALS: Testimonial[] = SITE.testimonials as unknown as Testimonial[];\n"
        "export const HOURS: Hour[] = SITE.hours as unknown as Hour[];\n"
        "export const MISSION: string[] = SITE.mission as unknown as string[];\n"
        "export const VALUES: Value[] = SITE.values as unknown as Value[];\n"
    )


def _derive_healthcare_email(content: ContentPack) -> str:
    slug = _slugify(content.brand_name) or "hello"
    return f"hello@{slug}.health"


def _healthcare_page_module(page: dict) -> str:
    comp = page["component"]
    name = page["name"]
    lname = name.lower()
    if comp == "Home":
        return _healthcare_home_tsx()
    if "service" in lname:
        return _healthcare_services_tsx(comp, name)
    if "doctor" in lname or "team" in lname:
        return _healthcare_doctors_tsx(comp, name)
    if "booking" in lname or "appointment" in lname:
        return _healthcare_booking_tsx(comp, name)
    if "about" in lname:
        return _healthcare_about_tsx(comp, name)
    if "contact" in lname:
        return _contact_page(comp, name)
    return _generic_page(comp, name, page.get("purpose", ""), page.get("sections", []))


def _healthcare_home_tsx() -> str:
    return (
        "import { Link } from 'react-router-dom';\n"
        "import { ArrowRight, Calendar } from 'lucide-react';\n"
        "import SITE, { SERVICES, DOCTORS, TESTIMONIALS } from '../data/site';\n\n"
        "export default function Home() {\n"
        "  const featuredServices = SERVICES.slice(0, 6);\n"
        "  const featuredDoctors = DOCTORS.slice(0, 4);\n"
        "  return (\n"
        "    <>\n"
        "      <section className=\"relative overflow-hidden\">\n"
        "        {SITE.hero_image && (<img src={SITE.hero_image} alt=\"\" aria-hidden className=\"pointer-events-none absolute inset-0 h-full w-full object-cover opacity-25\" />)}\n"
        "        <div aria-hidden className=\"pointer-events-none absolute inset-0\" style={{ background: 'radial-gradient(60% 50% at 50% 0%, hsl(var(--primary) / 0.18), transparent 70%)' }} />\n"
        "        <div className=\"relative container mx-auto max-w-6xl px-6 py-28 text-center md:py-36\">\n"
        "          <p className=\"mb-4 animate-fade-up text-sm font-medium uppercase tracking-widest text-muted-foreground\">{SITE.tagline}</p>\n"
        "          <h1 className=\"mx-auto max-w-3xl animate-fade-up-1 font-display text-5xl font-bold leading-tight tracking-tight md:text-7xl\">{SITE.hero_headline}</h1>\n"
        "          <p className=\"mx-auto mt-6 max-w-2xl animate-fade-up-2 text-lg text-muted-foreground\">{SITE.hero_subhead}</p>\n"
        "          <div className=\"mt-10 flex flex-wrap items-center justify-center gap-3 animate-fade-up-3\">\n"
        "            <Link to=\"/booking\" className=\"inline-flex items-center gap-2 rounded-[var(--radius)] bg-primary px-6 py-3 text-base font-medium text-primary-foreground transition-all hover:opacity-90 hover:shadow-lifted\">\n"
        "              <Calendar className=\"h-4 w-4\" /> {SITE.primary_cta}\n"
        "            </Link>\n"
        "            <Link to=\"/doctors\" className=\"inline-flex items-center gap-2 rounded-[var(--radius)] border border-border bg-card/70 px-6 py-3 text-base font-medium backdrop-blur transition-colors hover:bg-muted\">\n"
        "              {SITE.secondary_cta} <ArrowRight className=\"h-4 w-4\" />\n"
        "            </Link>\n"
        "          </div>\n"
        "        </div>\n"
        "      </section>\n\n"
        "      <section className=\"container mx-auto max-w-6xl px-6 py-20\">\n"
        "        <div className=\"mb-12 text-center\">\n"
        "          <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">Services</p>\n"
        "          <h2 className=\"font-display text-3xl font-bold tracking-tight md:text-4xl\">Care under one roof</h2>\n"
        "        </div>\n"
        "        <div className=\"grid gap-6 md:grid-cols-2 lg:grid-cols-3\">\n"
        "          {featuredServices.map((s) => (\n"
        "            <article key={s.title} className=\"hover-lift overflow-hidden rounded-[var(--radius)] border border-border bg-card transition-all hover:border-primary\">\n"
        "              {s.image && <img src={s.image} alt={s.title} className=\"h-40 w-full object-cover opacity-90\" loading=\"lazy\" />}\n"
        "              <div className=\"p-6\">\n"
        "                <h3 className=\"font-display text-lg font-semibold\">{s.title}</h3>\n"
        "                <p className=\"mt-2 text-sm text-muted-foreground\">{s.description}</p>\n"
        "              </div>\n"
        "            </article>\n"
        "          ))}\n"
        "        </div>\n"
        "        <div className=\"mt-10 text-center\">\n"
        "          <Link to=\"/services\" className=\"inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline\">All services <ArrowRight className=\"h-4 w-4\" /></Link>\n"
        "        </div>\n"
        "      </section>\n\n"
        "      {featuredDoctors.length > 0 && (\n"
        "        <section className=\"border-y border-border bg-muted/20 py-20\">\n"
        "          <div className=\"container mx-auto max-w-6xl px-6\">\n"
        "            <div className=\"mb-10 flex items-end justify-between\">\n"
        "              <h2 className=\"font-display text-3xl font-bold tracking-tight md:text-4xl\">Meet your care team</h2>\n"
        "              <Link to=\"/doctors\" className=\"text-sm font-medium text-primary hover:underline\">All clinicians →</Link>\n"
        "            </div>\n"
        "            <div className=\"grid gap-6 sm:grid-cols-2 lg:grid-cols-4\">\n"
        "              {featuredDoctors.map((d) => (\n"
        "                <article key={d.name} className=\"hover-lift overflow-hidden rounded-[var(--radius)] border border-border bg-card transition-all hover:border-primary\">\n"
        "                  {d.image && <img src={d.image} alt={d.name} className=\"h-56 w-full object-cover\" loading=\"lazy\" />}\n"
        "                  <div className=\"p-5\">\n"
        "                    <h3 className=\"font-display text-base font-semibold\">{d.name}</h3>\n"
        "                    <p className=\"mt-1 text-xs uppercase tracking-wider text-muted-foreground\">{d.role}</p>\n"
        "                  </div>\n"
        "                </article>\n"
        "              ))}\n"
        "            </div>\n"
        "          </div>\n"
        "        </section>\n"
        "      )}\n\n"
        "      {TESTIMONIALS.length > 0 && (\n"
        "        <section className=\"container mx-auto max-w-5xl px-6 py-20\">\n"
        "          <div className=\"grid gap-6 md:grid-cols-3\">\n"
        "            {TESTIMONIALS.map((t) => (\n"
        "              <figure key={t.author} className=\"hover-lift rounded-[var(--radius)] border border-border bg-card p-6 transition-all hover:border-primary\">\n"
        "                <blockquote className=\"font-display text-lg leading-relaxed\">“{t.quote}”</blockquote>\n"
        "                <figcaption className=\"mt-4 border-t border-border pt-4 text-sm text-muted-foreground\">— {t.author}, {t.role}</figcaption>\n"
        "              </figure>\n"
        "            ))}\n"
        "          </div>\n"
        "        </section>\n"
        "      )}\n\n"
        "      <section className=\"container mx-auto max-w-4xl px-6 py-24 text-center\">\n"
        "        <h2 className=\"mx-auto max-w-xl font-display text-3xl font-bold tracking-tight md:text-4xl\">Ready to book?</h2>\n"
        "        <p className=\"mx-auto mt-3 max-w-md text-muted-foreground\">Same-day visits are usually available. Insurance verified before you confirm.</p>\n"
        "        <Link to=\"/booking\" className=\"mt-8 inline-flex items-center gap-2 rounded-[var(--radius)] bg-primary px-6 py-3 text-base font-medium text-primary-foreground transition-all hover:opacity-90 hover:shadow-lifted\">\n"
        "          {SITE.primary_cta} <ArrowRight className=\"h-4 w-4\" />\n"
        "        </Link>\n"
        "      </section>\n"
        "    </>\n"
        "  );\n"
        "}\n"
    )


def _healthcare_services_tsx(comp: str, name: str) -> str:
    return (
        "import { SERVICES } from '../data/site';\n\n"
        "export default function " + comp + "() {\n"
        "  return (\n"
        "    <section className=\"container mx-auto max-w-6xl px-6 py-20\">\n"
        f"      <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{name}</p>\n"
        "      <h1 className=\"font-display text-4xl font-bold tracking-tight md:text-5xl\">Care under one roof</h1>\n"
        "      <p className=\"mt-4 max-w-2xl text-muted-foreground\">Every service line is staffed by clinicians who actually have time to talk.</p>\n"
        "      <div className=\"mt-12 grid gap-6 md:grid-cols-2 lg:grid-cols-3\">\n"
        "        {SERVICES.map((s) => (\n"
        "          <article key={s.title} className=\"hover-lift overflow-hidden rounded-[var(--radius)] border border-border bg-card transition-all hover:border-primary\">\n"
        "            {s.image && <img src={s.image} alt={s.title} className=\"h-40 w-full object-cover opacity-90\" loading=\"lazy\" />}\n"
        "            <div className=\"p-6\">\n"
        "              <h3 className=\"font-display text-lg font-semibold\">{s.title}</h3>\n"
        "              <p className=\"mt-2 text-sm text-muted-foreground\">{s.description}</p>\n"
        "            </div>\n"
        "          </article>\n"
        "        ))}\n"
        "      </div>\n"
        "    </section>\n"
        "  );\n"
        "}\n"
    )


def _healthcare_doctors_tsx(comp: str, name: str) -> str:
    return (
        "import { DOCTORS } from '../data/site';\n\n"
        "export default function " + comp + "() {\n"
        "  return (\n"
        "    <section className=\"container mx-auto max-w-6xl px-6 py-20\">\n"
        f"      <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{name}</p>\n"
        "      <h1 className=\"font-display text-4xl font-bold tracking-tight md:text-5xl\">Meet your care team</h1>\n"
        "      <p className=\"mt-4 max-w-2xl text-muted-foreground\">A small group of clinicians who pick up their own messages and remember your name.</p>\n"
        "      <div className=\"mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3\">\n"
        "        {DOCTORS.map((d) => (\n"
        "          <article key={d.name} className=\"hover-lift overflow-hidden rounded-[var(--radius)] border border-border bg-card transition-all hover:border-primary\">\n"
        "            {d.image && <img src={d.image} alt={d.name} className=\"h-64 w-full object-cover\" loading=\"lazy\" />}\n"
        "            <div className=\"p-5\">\n"
        "              <h3 className=\"font-display text-lg font-semibold\">{d.name}</h3>\n"
        "              <p className=\"mt-1 text-xs uppercase tracking-wider text-muted-foreground\">{d.role} · {d.credentials}</p>\n"
        "              <p className=\"mt-3 text-sm text-muted-foreground\">{d.bio}</p>\n"
        "            </div>\n"
        "          </article>\n"
        "        ))}\n"
        "      </div>\n"
        "    </section>\n"
        "  );\n"
        "}\n"
    )


def _healthcare_booking_tsx(comp: str, name: str) -> str:
    return (
        "import { FormEvent, useState } from 'react';\n"
        "import { toast } from 'sonner';\n"
        "import SITE, { DOCTORS } from '../data/site';\n\n"
        "export default function " + comp + "() {\n"
        "  const [patient, setPatient] = useState('');\n"
        "  const [email, setEmail] = useState('');\n"
        "  const [date, setDate] = useState('');\n"
        "  const [time, setTime] = useState('09:00');\n"
        "  const [doctor, setDoctor] = useState<string>(DOCTORS[0]?.name || '');\n"
        "  const [reason, setReason] = useState('');\n"
        "  function onSubmit(e: FormEvent) {\n"
        "    e.preventDefault();\n"
        "    if (!patient.trim() || !email.trim() || !date) { toast.error('Please complete name, email, and date.'); return; }\n"
        "    toast.success(`Appointment requested with ${doctor || 'next available'} on ${date} at ${time}`);\n"
        "    setPatient(''); setEmail(''); setReason('');\n"
        "  }\n"
        "  return (\n"
        "    <section className=\"container mx-auto max-w-3xl px-6 py-20\">\n"
        f"      <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{name}</p>\n"
        "      <h1 className=\"font-display text-4xl font-bold tracking-tight md:text-5xl\">Book an appointment at {SITE.brand}</h1>\n"
        "      <p className=\"mt-4 text-muted-foreground\">We confirm requests within one business hour. Telehealth slots are usually same-day.</p>\n"
        "      <form onSubmit={onSubmit} className=\"mt-10 grid gap-5 rounded-[var(--radius)] border border-border bg-card p-8\">\n"
        "        <div className=\"grid gap-5 md:grid-cols-2\">\n"
        "          <label className=\"text-sm\">Full name\n"
        "            <input value={patient} onChange={(e) => setPatient(e.target.value)} required className=\"mt-2 w-full rounded-[var(--radius)] border border-border bg-background px-3 py-2 text-sm\" />\n"
        "          </label>\n"
        "          <label className=\"text-sm\">Email\n"
        "            <input type=\"email\" value={email} onChange={(e) => setEmail(e.target.value)} required className=\"mt-2 w-full rounded-[var(--radius)] border border-border bg-background px-3 py-2 text-sm\" />\n"
        "          </label>\n"
        "        </div>\n"
        "        <div className=\"grid gap-5 md:grid-cols-3\">\n"
        "          <label className=\"text-sm\">Date\n"
        "            <input type=\"date\" value={date} onChange={(e) => setDate(e.target.value)} required className=\"mt-2 w-full rounded-[var(--radius)] border border-border bg-background px-3 py-2 text-sm\" />\n"
        "          </label>\n"
        "          <label className=\"text-sm\">Time\n"
        "            <input type=\"time\" value={time} onChange={(e) => setTime(e.target.value)} className=\"mt-2 w-full rounded-[var(--radius)] border border-border bg-background px-3 py-2 text-sm\" />\n"
        "          </label>\n"
        "          <label className=\"text-sm\">Clinician\n"
        "            <select value={doctor} onChange={(e) => setDoctor(e.target.value)} className=\"mt-2 w-full rounded-[var(--radius)] border border-border bg-background px-3 py-2 text-sm\">\n"
        "              <option value=\"\">Next available</option>\n"
        "              {DOCTORS.map((d) => (<option key={d.name} value={d.name}>{d.name} — {d.role}</option>))}\n"
        "            </select>\n"
        "          </label>\n"
        "        </div>\n"
        "        <label className=\"text-sm\">Reason for visit\n"
        "          <textarea value={reason} onChange={(e) => setReason(e.target.value)} className=\"mt-2 w-full rounded-[var(--radius)] border border-border bg-background px-3 py-2 text-sm\" rows={3} />\n"
        "        </label>\n"
        "        <button type=\"submit\" className=\"justify-self-start rounded-[var(--radius)] bg-primary px-5 py-3 text-sm font-medium text-primary-foreground transition-all hover:opacity-90 hover:shadow-lifted\">\n"
        "          Request appointment\n"
        "        </button>\n"
        "      </form>\n"
        "      <p className=\"mt-6 text-xs text-muted-foreground\">This is a request, not a confirmed booking. We will call or email to confirm.</p>\n"
        "    </section>\n"
        "  );\n"
        "}\n"
    )


def _healthcare_about_tsx(comp: str, name: str) -> str:
    return (
        "import SITE, { MISSION, VALUES } from '../data/site';\n\n"
        "export default function " + comp + "() {\n"
        "  return (\n"
        "    <section className=\"container mx-auto max-w-4xl px-6 py-20\">\n"
        f"      <p className=\"mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground\">{name}</p>\n"
        "      <h1 className=\"font-display text-4xl font-bold tracking-tight md:text-5xl\">Care that listens, at {SITE.brand}</h1>\n"
        "      <div className=\"mt-10 space-y-5 text-muted-foreground\">\n"
        "        {MISSION.map((p, i) => (<p key={i}>{p}</p>))}\n"
        "      </div>\n"
        "      <h2 className=\"mt-16 font-display text-2xl font-semibold\">What we stand for</h2>\n"
        "      <div className=\"mt-6 grid gap-5 sm:grid-cols-2\">\n"
        "        {VALUES.map((v) => (\n"
        "          <div key={v.label} className=\"hover-lift rounded-[var(--radius)] border border-border bg-card p-6 transition-all hover:border-primary\">\n"
        "            <h3 className=\"font-display text-base font-semibold\">{v.label}</h3>\n"
        "            <p className=\"mt-2 text-sm text-muted-foreground\">{v.body}</p>\n"
        "          </div>\n"
        "        ))}\n"
        "      </div>\n"
        "    </section>\n"
        "  );\n"
        "}\n"
    )
def scaffold_editorial_project(
    brief,
    design,
    content,
    plan,
    strategy,
    brand=None,
):
    return scaffold_multi_page_project(
        brief,
        design,
        content,
        plan,
        brand=brand,
    )


def scaffold_romantic_project(
    brief,
    design,
    content,
    plan,
    strategy,
    brand=None,
):
    return scaffold_multi_page_project(
        brief,
        design,
        content,
        plan,
        brand=brand,
    )


def scaffold_dashboard_project(
    brief,
    design,
    content,
    plan,
    strategy,
    brand=None,
):
    return scaffold_multi_page_project(
        brief,
        design,
        content,
        plan,
        brand=brand,
    )