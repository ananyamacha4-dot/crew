"""Deterministic project scaffolder.

Generates a complete, runnable single-file React + Vite + TypeScript + Tailwind
project from a brief + design system + content pack. No LLM in this stage —
Llama can't reliably produce a multi-file React project that compiles, so we
template the boilerplate and inject the LLM's content into a known-good App.tsx.

Output: 10 files that ALWAYS render in Sandpack.
"""

from __future__ import annotations

import json

from .archetypes import get_archetype
from .design_modes import design_mode_for_app_type, get_design_mode
from .schemas import ContentPack, DesignSystem, FileSet, GeneratedFile, ProductBrief


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def scaffold_project(
    brief: ProductBrief,
    design: DesignSystem,
    content: ContentPack,
) -> FileSet:
    """Full landing-page project: boilerplate + the template-rendered landing App.tsx."""
    files = scaffold_boilerplate(content, design).files + [
        GeneratedFile(path="src/App.tsx", content=_app_tsx(brief, design, content)),
    ]
    summary = (
        f"{content.brand_name}: {brief.app_type or brief.product_type} · "
        f"{design.archetype} · {len(content.features)} features, "
        f"{len(content.testimonials)} testimonials, {len(content.pricing_tiers)} pricing tiers"
    )
    return FileSet(files=files, entry="public/index.html", summary=summary)


def scaffold_boilerplate(content: ContentPack, design: DesignSystem) -> FileSet:
    """Boilerplate ONLY — everything except src/App.tsx. Used by the non-landing
    pipeline: the LLM-generated App.tsx is layered on top of these files."""
    files: list[GeneratedFile] = [
        GeneratedFile(path="package.json", content=_package_json(content)),
        GeneratedFile(path="tsconfig.json", content=_tsconfig()),
        GeneratedFile(path="public/index.html", content=_index_html(content, design)),
        GeneratedFile(path="src/index.tsx", content=_index_tsx()),
        GeneratedFile(path="src/styles.css", content=_index_css(design)),
        GeneratedFile(path="src/lib/utils.ts", content=_utils_ts()),
    ]
    return FileSet(files=files, entry="public/index.html", summary="boilerplate")


def design_tokens_block(design: DesignSystem) -> str:
    """Human-readable summary of available design tokens, for the engineer prompt."""
    mode = get_design_mode(design.design_mode)
    return (
        "AVAILABLE TAILWIND COLOR TOKENS (wired to the design — use these,\n"
        "NEVER hardcode hex codes):\n"
        "  bg-background  bg-card  bg-muted  bg-primary  bg-accent\n"
        "  text-foreground  text-muted-foreground  text-primary\n"
        "  text-primary-foreground  text-accent-foreground\n"
        "  border-border  border-primary  border-accent\n"
        "  font-display  font-body  font-mono\n"
        "  rounded (uses design radius)  rounded-full  rounded-none\n"
        "  Opacity modifiers: bg-primary/10, bg-accent/20, border-border/50, etc.\n\n"
        "PREMIUM UTILITY CLASSES (defined in styles.css — reference by class name):\n"
        "  gradient-text   - text with the brand gradient applied\n"
        "  gradient-bg     - element bg with the brand gradient\n"
        "  glass           - frosted glass background (backdrop-blur + semi-transparent)\n"
        "  shadow-soft     - layered medium shadow\n"
        "  shadow-lifted   - deeper shadow, for floating/important elements\n"
        "  glow            - brand-color glow (use sparingly: hero CTA, active stat)\n"
        "  hover-lift      - translate-y up + bigger shadow on hover\n"
        "  hover-glow      - brand glow on hover\n"
        "  grid-pattern    - subtle grid background (bg for hero)\n"
        "  dot-pattern     - subtle dot background\n"
        "  surface-1       - bg-card + border, base elevated surface\n"
        "  surface-2       - bg-muted + border, secondary surface\n"
        "  animate-fade-up - entrance animation (use on hero/section enter)\n"
        "  animate-fade-up-1 / -2 / -3 - staggered fade-up (use on a series)\n\n"
        f"DESIGN MODE: {design.design_mode} ({mode['label']})\n"
        f"  feel: {mode['feel']}\n"
        f"  shadow_style: {mode['shadow_style']}\n"
        f"  animation_style: {mode['animation_style']}"
    )


# ---------------------------------------------------------------------------
# Static boilerplate
# ---------------------------------------------------------------------------

def _package_json(content: ContentPack) -> str:
    # Sandpack's react-ts template uses an in-browser bundler — only runtime
    # deps matter. Tailwind comes via Play CDN; no PostCSS, no Vite, no Rollup.
    pkg = {
        "name": _slugify(content.brand_name) or "generated-app",
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


def _index_html(content: ContentPack, design: DesignSystem) -> str:
    title = _escape_html(content.brand_name or "Generated App")
    # Tailwind Play CDN keeps the preview bundle-free. The inline `tailwind.config`
    # block wires our CSS custom properties (--primary, --background, etc.) into
    # the Tailwind theme so `bg-primary` / `text-foreground` etc. resolve.
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
    return """import { createRoot } from 'react-dom/client';
import { Toaster } from 'sonner';
import App from './App';
import './styles.css';

const root = createRoot(document.getElementById('root')!);
root.render(
  <>
    <App />
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
# Design-driven CSS variables
# ---------------------------------------------------------------------------

def _index_css(design: DesignSystem) -> str:
    mode = get_design_mode(design.design_mode)
    p = mode["palette"]
    fonts = mode["fonts"]
    radius = mode["radius"]
    shadow_style = mode.get("shadow_style", "soft-layered")
    gradient_primary = mode.get("gradient_primary", "")

    # Shadow definitions per style — these become the --shadow-* CSS vars.
    shadow_presets = {
        "flat": {
            "sm": "0 1px 0 hsl(var(--border))",
            "md": "0 1px 2px hsl(var(--border))",
            "lg": "0 2px 4px hsl(var(--border))",
            "glow": "0 0 0 0 transparent",
        },
        "subtle-paper": {
            "sm": "0 1px 2px rgba(0,0,0,0.04)",
            "md": "0 4px 12px rgba(0,0,0,0.06)",
            "lg": "0 10px 30px rgba(0,0,0,0.08)",
            "glow": "0 0 0 0 transparent",
        },
        "soft-layered": {
            "sm": "0 1px 2px rgba(0,0,0,0.06), 0 1px 1px rgba(0,0,0,0.04)",
            "md": "0 4px 12px rgba(0,0,0,0.08), 0 2px 4px rgba(0,0,0,0.04)",
            "lg": "0 24px 48px -12px rgba(0,0,0,0.18), 0 8px 16px -8px rgba(0,0,0,0.10)",
            "glow": "0 0 32px -8px hsl(var(--primary) / 0.45)",
        },
        "neon-glow": {
            "sm": "0 0 12px -2px hsl(var(--primary) / 0.4)",
            "md": "0 0 24px -4px hsl(var(--primary) / 0.55), 0 0 60px -16px hsl(var(--accent) / 0.45)",
            "lg": "0 0 48px -8px hsl(var(--primary) / 0.7), 0 0 100px -20px hsl(var(--accent) / 0.55)",
            "glow": "0 0 32px hsl(var(--primary) / 0.6), 0 0 64px hsl(var(--accent) / 0.35)",
        },
    }
    sh = shadow_presets.get(shadow_style, shadow_presets["soft-layered"])

    return (
        "/* ---------- DESIGN TOKENS ---------- */\n"
        f"/* design_mode: {design.design_mode} ({mode['label']}) */\n"
        ":root {\n"
        f"  --background: {p['background']};\n"
        f"  --foreground: {p['foreground']};\n"
        f"  --muted: {p['muted']};\n"
        f"  --muted-foreground: {p['muted_foreground']};\n"
        f"  --card: {p['card']};\n"
        f"  --border: {p['border']};\n"
        f"  --primary: {p['primary']};\n"
        f"  --primary-foreground: {p['primary_foreground']};\n"
        f"  --accent: {p['accent']};\n"
        f"  --accent-foreground: {p['accent_foreground']};\n"
        f"  --radius: {radius};\n"
        f"  --font-display: {fonts['display']};\n"
        f"  --font-body: {fonts['body']};\n"
        f"  --font-mono: {fonts['mono']};\n"
        f"  --shadow-sm: {sh['sm']};\n"
        f"  --shadow-md: {sh['md']};\n"
        f"  --shadow-lg: {sh['lg']};\n"
        f"  --shadow-glow: {sh['glow']};\n"
        f"  --gradient-primary: {gradient_primary};\n"
        "}\n\n"
        "/* ---------- BASE ---------- */\n"
        "html { scroll-behavior: smooth; }\n"
        "body {\n"
        "  font-family: var(--font-body);\n"
        "  background: hsl(var(--background));\n"
        "  color: hsl(var(--foreground));\n"
        "  -webkit-font-smoothing: antialiased;\n"
        "  -moz-osx-font-smoothing: grayscale;\n"
        "}\n"
        "h1, h2, h3, h4 { font-family: var(--font-display); letter-spacing: -0.02em; }\n"
        "code, pre { font-family: var(--font-mono); }\n\n"
        "/* ---------- PREMIUM UTILITY CLASSES ---------- */\n"
        "/* The Engineer agent references these by name — DO NOT remove. */\n\n"
        ".gradient-text {\n"
        "  background-image: var(--gradient-primary);\n"
        "  -webkit-background-clip: text;\n"
        "  background-clip: text;\n"
        "  color: transparent;\n"
        "}\n\n"
        ".gradient-bg { background-image: var(--gradient-primary); }\n\n"
        ".glass {\n"
        "  background: hsl(var(--card) / 0.6);\n"
        "  backdrop-filter: blur(16px) saturate(180%);\n"
        "  -webkit-backdrop-filter: blur(16px) saturate(180%);\n"
        "  border: 1px solid hsl(var(--border) / 0.5);\n"
        "}\n\n"
        ".shadow-soft { box-shadow: var(--shadow-md); }\n"
        ".shadow-lifted { box-shadow: var(--shadow-lg); }\n"
        ".glow { box-shadow: var(--shadow-glow); }\n\n"
        ".hover-lift {\n"
        "  transition: transform 200ms ease, box-shadow 200ms ease;\n"
        "}\n"
        ".hover-lift:hover {\n"
        "  transform: translateY(-2px);\n"
        "  box-shadow: var(--shadow-lg);\n"
        "}\n\n"
        ".hover-glow {\n"
        "  transition: box-shadow 220ms ease;\n"
        "}\n"
        ".hover-glow:hover { box-shadow: var(--shadow-glow); }\n\n"
        ".grid-pattern {\n"
        "  background-image:\n"
        "    linear-gradient(hsl(var(--border) / 0.6) 1px, transparent 1px),\n"
        "    linear-gradient(90deg, hsl(var(--border) / 0.6) 1px, transparent 1px);\n"
        "  background-size: 32px 32px;\n"
        "}\n\n"
        ".dot-pattern {\n"
        "  background-image: radial-gradient(hsl(var(--border)) 1px, transparent 1px);\n"
        "  background-size: 20px 20px;\n"
        "}\n\n"
        ".surface-1 { background: hsl(var(--card)); border: 1px solid hsl(var(--border)); }\n"
        ".surface-2 { background: hsl(var(--muted)); border: 1px solid hsl(var(--border)); }\n\n"
        "/* Scrollbar polish */\n"
        "::-webkit-scrollbar { width: 10px; height: 10px; }\n"
        "::-webkit-scrollbar-track { background: hsl(var(--background)); }\n"
        "::-webkit-scrollbar-thumb {\n"
        "  background: hsl(var(--border));\n"
        "  border-radius: 999px;\n"
        "  border: 2px solid hsl(var(--background));\n"
        "}\n"
        "::-webkit-scrollbar-thumb:hover { background: hsl(var(--muted-foreground) / 0.4); }\n\n"
        "/* Focus rings */\n"
        "*:focus-visible {\n"
        "  outline: 2px solid hsl(var(--primary) / 0.6);\n"
        "  outline-offset: 2px;\n"
        "  border-radius: var(--radius);\n"
        "}\n\n"
        "/* Subtle entrance animation reusable by engineer */\n"
        "@keyframes fade-up {\n"
        "  from { opacity: 0; transform: translateY(8px); }\n"
        "  to { opacity: 1; transform: translateY(0); }\n"
        "}\n"
        ".animate-fade-up { animation: fade-up 500ms ease both; }\n"
        ".animate-fade-up-1 { animation: fade-up 500ms 80ms ease both; }\n"
        ".animate-fade-up-2 { animation: fade-up 500ms 160ms ease both; }\n"
        ".animate-fade-up-3 { animation: fade-up 500ms 240ms ease both; }\n"
    )


# ---------------------------------------------------------------------------
# App.tsx — single-file React component, populated from ContentPack
#
# Implementation note: we build this as a regular string with PLACEHOLDER
# tokens like __BRAND__, __FEATURES__ etc., then run .replace() to inject
# the JSON-stringified ContentPack values. Avoids the f-string / JSX brace
# nightmare entirely.
# ---------------------------------------------------------------------------

_APP_TSX_TEMPLATE = """import { useState } from 'react';
import {
  Sparkles, Zap, Check, ArrowRight, ArrowLeft, ArrowUpRight,
  ChevronRight, ChevronDown, ChevronUp, Menu, X, Plus, Minus,
  Star, Heart, Shield, ShieldCheck, Mail, Send, MessageSquare,
  Phone, Calendar, Clock, MapPin, Globe, Home as HomeIcon,
  User, Users, Lock, Unlock, Search, Settings, Bell,
  Code, Code2, Terminal, Cpu, Database, Cloud, Github,
  ShoppingCart, ShoppingBag, CreditCard, DollarSign, Tag,
  BarChart3, LineChart, PieChart, TrendingUp, Activity, Eye,
  Rocket, Target, Award, Trophy, Flame, Gauge,
  Sun, Moon, Palette, Layers, LayoutGrid, Layout,
  Brain, Lightbulb, Coffee, Book, BookOpen, Briefcase,
  Quote, Filter, Download, Upload, Share2, ExternalLink,
  Camera, Image as ImageIcon, Video, Music, Play, Pause,
} from 'lucide-react';
import { toast } from 'sonner';
import { cn } from './lib/utils';

const ICON_MAP: Record<string, any> = {
  Sparkles, Zap, Check, ArrowRight, ArrowLeft, ArrowUpRight,
  ChevronRight, ChevronDown, ChevronUp, Menu, X, Plus, Minus,
  Star, Heart, Shield, ShieldCheck, Mail, Send, MessageSquare,
  Phone, Calendar, Clock, MapPin, Globe, Home: HomeIcon,
  User, Users, Lock, Unlock, Search, Settings, Bell,
  Code, Code2, Terminal, Cpu, Database, Cloud, Github,
  ShoppingCart, ShoppingBag, CreditCard, DollarSign, Tag,
  BarChart3, LineChart, PieChart, TrendingUp, Activity, Eye,
  Rocket, Target, Award, Trophy, Flame, Gauge,
  Sun, Moon, Palette, Layers, LayoutGrid, Layout,
  Brain, Lightbulb, Coffee, Book, BookOpen, Briefcase,
  Quote, Filter, Download, Upload, Share2, ExternalLink,
  Camera, Image: ImageIcon, Video, Music, Play, Pause,
};

const BRAND: string = __BRAND__;
const TAGLINE: string = __TAGLINE__;
const HEADLINE: string = __HEADLINE__;
const SUBHEAD: string = __SUBHEAD__;
const PRIMARY_CTA: string = __PRIMARY_CTA__;
const SECONDARY_CTA: string | null = __SECONDARY_CTA__;
const NAV: { label: string; route: string }[] = __NAV__;
const FEATURES: { title: string; description: string; icon: string }[] = __FEATURES__;
const TESTIMONIALS: { quote: string; author: string; role: string; company: string }[] = __TESTIMONIALS__;
const PRICING: { name: string; price: string; period: string; description: string; features: string[]; cta_label: string; highlighted: boolean }[] = __PRICING__;
const FAQS: { question: string; answer: string }[] = __FAQS__;
const FOOTER_LINKS: Record<string, { label: string; route: string }[]> = __FOOTER_LINKS__;
const SECTIONS_ENABLED: Record<string, boolean> = __SECTIONS_ENABLED__;

function Icon({ name, className }: { name: string; className?: string }) {
  const Cmp = ICON_MAP[name] || Sparkles;
  return <Cmp className={className} aria-hidden />;
}

function scrollToId(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
}

function handleNav(item: { label: string; route: string }, onClose?: () => void) {
  return (e: React.MouseEvent) => {
    if (item.route.startsWith('#')) {
      e.preventDefault();
      scrollToId(item.route.slice(1));
    }
    onClose?.();
  };
}

function Header() {
  const [open, setOpen] = useState(false);
  return (
    <header className="sticky top-0 z-50 border-b border-border bg-background/80 backdrop-blur-md">
      <div className="container mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <a
          href="#top"
          onClick={(e) => { e.preventDefault(); window.scrollTo({ top: 0, behavior: 'smooth' }); }}
          className="font-display text-lg font-bold tracking-tight"
        >
          {BRAND}
        </a>
        <nav className="hidden gap-6 md:flex">
          {NAV.map((n) => (
            <a key={n.route} href={n.route} onClick={handleNav(n)} className="text-sm text-muted-foreground hover:text-foreground transition-colors">
              {n.label}
            </a>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <button
            onClick={() => toast.success('Welcome to ' + BRAND)}
            className="hidden md:inline-flex rounded-[var(--radius)] bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
          >
            {PRIMARY_CTA}
          </button>
          <button
            onClick={() => setOpen((v) => !v)}
            className="rounded-md border border-border p-2 md:hidden"
            aria-label="Toggle menu"
          >
            <Icon name={open ? 'X' : 'Menu'} className="h-5 w-5" />
          </button>
        </div>
      </div>
      {open && (
        <div className="border-t border-border md:hidden">
          <nav className="container mx-auto flex max-w-6xl flex-col gap-3 px-6 py-4">
            {NAV.map((n) => (
              <a
                key={n.route}
                href={n.route}
                onClick={handleNav(n, () => setOpen(false))}
                className="text-sm text-muted-foreground hover:text-foreground transition-colors"
              >
                {n.label}
              </a>
            ))}
            <button
              onClick={() => { setOpen(false); toast.success('Welcome to ' + BRAND); }}
              className="mt-2 rounded-[var(--radius)] bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
            >
              {PRIMARY_CTA}
            </button>
          </nav>
        </div>
      )}
    </header>
  );
}

function Hero() {
  return (
    <section id="hero" className="container mx-auto max-w-6xl px-6 py-24 text-center md:py-32">
      {TAGLINE && <p className="mb-4 text-sm font-medium uppercase tracking-widest text-muted-foreground">{TAGLINE}</p>}
      <h1 className="mx-auto max-w-3xl font-display text-4xl font-bold leading-tight tracking-tight md:text-6xl">
        {HEADLINE}
      </h1>
      <p className="mx-auto mt-6 max-w-2xl text-lg text-muted-foreground">
        {SUBHEAD}
      </p>
      <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
        <button
          onClick={() => {
            const id = FEATURES.length ? 'features' : (PRICING.length ? 'pricing' : 'cta');
            scrollToId(id);
          }}
          className="inline-flex items-center gap-2 rounded-[var(--radius)] bg-primary px-6 py-3 text-base font-medium text-primary-foreground transition-opacity hover:opacity-90"
        >
          {PRIMARY_CTA}
          <Icon name="ArrowRight" className="h-4 w-4" />
        </button>
        {SECONDARY_CTA && (
          <button
            onClick={() => scrollToId('faq')}
            className="inline-flex items-center gap-2 rounded-[var(--radius)] border border-border px-6 py-3 text-base font-medium transition-colors hover:bg-muted"
          >
            {SECONDARY_CTA}
          </button>
        )}
      </div>
    </section>
  );
}

function FeatureGrid() {
  if (FEATURES.length === 0) return null;
  return (
    <section id="features" className="container mx-auto max-w-6xl px-6 py-20">
      <div className="mx-auto mb-12 max-w-2xl text-center">
        <h2 className="font-display text-3xl font-bold tracking-tight md:text-4xl">Features</h2>
        <p className="mt-3 text-muted-foreground">Built for {BRAND}.</p>
      </div>
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map((f, i) => (
          <div key={i} className="rounded-[var(--radius)] border border-border bg-card p-6 transition-colors hover:border-primary">
            <div className="mb-4 inline-flex h-10 w-10 items-center justify-center rounded-[var(--radius)] bg-primary/10 text-primary">
              <Icon name={f.icon} className="h-5 w-5" />
            </div>
            <h3 className="mb-2 font-display text-lg font-semibold">{f.title}</h3>
            <p className="text-sm text-muted-foreground">{f.description}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function Testimonials() {
  if (TESTIMONIALS.length === 0) return null;
  return (
    <section id="testimonials" className="border-y border-border bg-muted/30 py-20">
      <div className="container mx-auto max-w-6xl px-6">
        <h2 className="mb-12 text-center font-display text-3xl font-bold tracking-tight md:text-4xl">
          Loved by teams everywhere
        </h2>
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {TESTIMONIALS.map((t, i) => (
            <figure key={i} className="rounded-[var(--radius)] border border-border bg-card p-6">
              <Icon name="Quote" className="mb-4 h-5 w-5 text-muted-foreground" />
              <blockquote className="text-sm leading-relaxed">&ldquo;{t.quote}&rdquo;</blockquote>
              <figcaption className="mt-4 border-t border-border pt-4">
                <div className="font-semibold">{t.author}</div>
                <div className="text-xs text-muted-foreground">{t.role} · {t.company}</div>
              </figcaption>
            </figure>
          ))}
        </div>
      </div>
    </section>
  );
}

function Pricing() {
  if (PRICING.length === 0) return null;
  return (
    <section id="pricing" className="container mx-auto max-w-6xl px-6 py-20">
      <div className="mx-auto mb-12 max-w-2xl text-center">
        <h2 className="font-display text-3xl font-bold tracking-tight md:text-4xl">Simple pricing</h2>
        <p className="mt-3 text-muted-foreground">Choose the plan that fits.</p>
      </div>
      <div className="grid gap-6 md:grid-cols-3">
        {PRICING.map((p, i) => (
          <div
            key={i}
            className={cn(
              'rounded-[var(--radius)] border bg-card p-8',
              p.highlighted ? 'border-primary shadow-lg ring-1 ring-primary' : 'border-border'
            )}
          >
            {p.highlighted && (
              <div className="mb-4 inline-flex rounded-full bg-primary px-3 py-1 text-xs font-medium text-primary-foreground">
                Most popular
              </div>
            )}
            <h3 className="font-display text-xl font-semibold">{p.name}</h3>
            <p className="mt-1 text-sm text-muted-foreground">{p.description}</p>
            <div className="mt-6 flex items-baseline gap-1">
              <span className="font-display text-4xl font-bold">{p.price}</span>
              {p.period && <span className="text-sm text-muted-foreground">{p.period}</span>}
            </div>
            <button
              onClick={() => toast.success('Selected ' + p.name)}
              className={cn(
                'mt-6 w-full rounded-[var(--radius)] px-4 py-3 text-sm font-medium transition-opacity',
                p.highlighted
                  ? 'bg-primary text-primary-foreground hover:opacity-90'
                  : 'border border-border hover:bg-muted'
              )}
            >
              {p.cta_label}
            </button>
            <ul className="mt-8 space-y-3">
              {p.features.map((feat, j) => (
                <li key={j} className="flex items-start gap-2 text-sm">
                  <Icon name="Check" className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary" />
                  <span>{feat}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}

function Faq() {
  const [openIdx, setOpenIdx] = useState<number | null>(null);
  if (FAQS.length === 0) return null;
  return (
    <section id="faq" className="container mx-auto max-w-3xl px-6 py-20">
      <h2 className="mb-12 text-center font-display text-3xl font-bold tracking-tight md:text-4xl">
        Frequently asked questions
      </h2>
      <div className="space-y-3">
        {FAQS.map((f, i) => (
          <div key={i} className="rounded-[var(--radius)] border border-border bg-card">
            <button
              onClick={() => setOpenIdx((cur) => (cur === i ? null : i))}
              className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left text-sm font-medium hover:bg-muted/40"
            >
              <span>{f.question}</span>
              <Icon name={openIdx === i ? 'Minus' : 'Plus'} className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
            </button>
            {openIdx === i && (
              <div className="border-t border-border px-5 py-4 text-sm text-muted-foreground">
                {f.answer}
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function CtaBand() {
  return (
    <section id="cta" className="container mx-auto max-w-4xl px-6 py-20">
      <div className="rounded-[var(--radius)] border border-border bg-card p-12 text-center">
        <h2 className="mx-auto max-w-xl font-display text-3xl font-bold tracking-tight md:text-4xl">
          Ready when you are
        </h2>
        <p className="mx-auto mt-3 max-w-md text-muted-foreground">
          {SUBHEAD}
        </p>
        <button
          onClick={() => toast.success('Welcome to ' + BRAND)}
          className="mt-8 inline-flex items-center gap-2 rounded-[var(--radius)] bg-primary px-6 py-3 text-base font-medium text-primary-foreground transition-opacity hover:opacity-90"
        >
          {PRIMARY_CTA}
          <Icon name="ArrowRight" className="h-4 w-4" />
        </button>
      </div>
    </section>
  );
}

function Footer() {
  const cols = Object.keys(FOOTER_LINKS);
  return (
    <footer className="border-t border-border bg-muted/20">
      <div className="container mx-auto max-w-6xl px-6 py-12">
        <div className="grid gap-8 md:grid-cols-4">
          <div>
            <div className="font-display text-lg font-bold">{BRAND}</div>
            {TAGLINE && <p className="mt-2 max-w-xs text-sm text-muted-foreground">{TAGLINE}</p>}
          </div>
          {cols.map((col) => (
            <div key={col}>
              <div className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {col}
              </div>
              <ul className="space-y-2">
                {FOOTER_LINKS[col].map((item) => (
                  <li key={item.route}>
                    <a
                      href={item.route}
                      onClick={handleNav(item)}
                      className="text-sm text-muted-foreground hover:text-foreground"
                    >
                      {item.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="mt-12 border-t border-border pt-6 text-xs text-muted-foreground">
          © {new Date().getFullYear()} {BRAND}. All rights reserved.
        </div>
      </div>
    </footer>
  );
}

export default function App() {
  return (
    <div id="top" className="min-h-screen bg-background font-body text-foreground antialiased">
      <Header />
      <main>
        {SECTIONS_ENABLED['hero'] && <Hero />}
        {SECTIONS_ENABLED['features-grid'] && <FeatureGrid />}
        {SECTIONS_ENABLED['testimonials'] && <Testimonials />}
        {SECTIONS_ENABLED['pricing-table'] && <Pricing />}
        {SECTIONS_ENABLED['faq'] && <Faq />}
        {SECTIONS_ENABLED['cta-band'] && <CtaBand />}
      </main>
      <Footer />
    </div>
  );
}
"""


def _app_tsx(
    brief: ProductBrief,
    design: DesignSystem,
    content: ContentPack,
) -> str:
    sections_present = _all_sections(brief)
    if not sections_present:
        sections_present = {"hero", "features-grid", "testimonials", "pricing-table", "faq", "cta-band", "footer"}
    sections_enabled = {
        s: (s in sections_present)
        for s in ("hero", "features-grid", "testimonials", "pricing-table", "faq", "cta-band")
    }

    nav = content.nav_items or []
    features = content.features or []
    testimonials = content.testimonials or []
    pricing = content.pricing_tiers or []
    faqs = content.faqs or []
    footer_links = content.footer_links or {}

    substitutions = {
        "__BRAND__": json.dumps(content.brand_name or "Brand"),
        "__TAGLINE__": json.dumps(content.tagline or ""),
        "__HEADLINE__": json.dumps(content.hero_headline or content.brand_name or "Welcome"),
        "__SUBHEAD__": json.dumps(content.hero_subhead or content.tagline or ""),
        "__PRIMARY_CTA__": json.dumps(content.primary_cta or "Get started"),
        "__SECONDARY_CTA__": json.dumps(content.secondary_cta) if content.secondary_cta else "null",
        "__NAV__": json.dumps([{"label": n.label, "route": n.route} for n in nav], ensure_ascii=False),
        "__FEATURES__": json.dumps(
            [{"title": f.title, "description": f.description, "icon": f.icon} for f in features],
            ensure_ascii=False,
        ),
        "__TESTIMONIALS__": json.dumps(
            [
                {"quote": t.quote, "author": t.author, "role": t.role, "company": t.company}
                for t in testimonials
            ],
            ensure_ascii=False,
        ),
        "__PRICING__": json.dumps(
            [
                {
                    "name": p.name,
                    "price": p.price,
                    "period": p.period,
                    "description": p.description,
                    "features": list(p.features),
                    "cta_label": p.cta_label,
                    "highlighted": p.highlighted,
                }
                for p in pricing
            ],
            ensure_ascii=False,
        ),
        "__FAQS__": json.dumps(
            [{"question": q.question, "answer": q.answer} for q in faqs],
            ensure_ascii=False,
        ),
        "__FOOTER_LINKS__": json.dumps(
            {
                col: [{"label": n.label, "route": n.route} for n in items]
                for col, items in footer_links.items()
            },
            ensure_ascii=False,
        ),
        "__SECTIONS_ENABLED__": json.dumps(sections_enabled),
    }

    out = _APP_TSX_TEMPLATE
    for token, value in substitutions.items():
        out = out.replace(token, value)
    return out


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


def _all_sections(brief: ProductBrief) -> set[str]:
    out: set[str] = set()
    for p in brief.pages:
        for s in p.sections:
            if isinstance(s, str):
                out.add(s)
    return out


def _hex_to_hsl(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return "0 0% 50%"
    try:
        r = int(h[0:2], 16) / 255
        g = int(h[2:4], 16) / 255
        b = int(h[4:6], 16) / 255
    except ValueError:
        return "0 0% 50%"
    mx = max(r, g, b)
    mn = min(r, g, b)
    l = (mx + mn) / 2
    if mx == mn:
        s = 0.0
        hh = 0.0
    else:
        d = mx - mn
        s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
        if mx == r:
            hh = (g - b) / d + (6 if g < b else 0)
        elif mx == g:
            hh = (b - r) / d + 2
        else:
            hh = (r - g) / d + 4
        hh /= 6
    return f"{round(hh * 360)} {round(s * 100)}% {round(l * 100)}%"


def _is_dark_color(hex_color: str) -> bool:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return False
    try:
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
    except ValueError:
        return False
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return luminance < 0.5
