# Open Lovable Reference Layer

Curated reference manifests inspired by patterns observed in
[firecrawl/open-lovable](https://github.com/firecrawl/open-lovable) — an
open-source AI app builder.

## What this folder is

Open Lovable itself is a self-contained app builder (Next.js 15 + Vercel AI
SDK + Firecrawl + Vercel Sandbox). We do **not** clone its code. Instead, we
extract the *shapes* that good multi-page React apps tend to take in
Open Lovable–style outputs, and express those shapes as `template.json`
manifests in our existing `TemplateManifest` schema.

Each subfolder here is a multi-page archetype:

| Folder | Archetype | Pages |
|---|---|---|
| `saas-marketing/` | B2B SaaS landing | /, /features, /pricing, /docs, /changelog |
| `portfolio-personal/` | Designer / dev portfolio | /, /work, /about, /journal, /contact |
| `ecommerce-boutique/` | Small-batch ecommerce | /, /shop, /product, /cart, /lookbook, /about |

The existing `backend/crew/templates/registry.py:_load_overrides()` walks
this tree recursively and auto-registers each manifest — no loader changes
needed.

## How this differs from `restaurant/`

The `restaurant/` reference set focuses on **hospitality verticals** with a
shared shape (Home / Menu / About / Gallery / Contact / Reservations). The
Open Lovable set focuses on **product / showcase / commerce** shapes that
don't fit the restaurant mold.

Both layers share the same scaffold infrastructure (HashRouter, shared Nav /
Footer / Layout components, Pollinations imagery, design-mode CSS variables).
The only thing per-archetype is the page emitters (in
`backend/crew/scaffold_multi.py`).

## `patterns.json`

A sibling document — **not** a TemplateManifest — that captures non-template
metadata: component vocabulary, motion conventions, layout principles,
responsive breakpoints, and per-archetype default layouts. Loaded by
`backend/crew/reference_patterns.py` and consumed by the scaffolders as
inspiration context.

## Adding a new archetype

1. Create a subfolder under `awesome-designs/open-lovable/<archetype>/`.
2. Add a `template.json` following the existing schema. Pick a unique `key`,
   a `category` that matches your niche classifier mapping, and a list of
   `pages` with routes.
3. (If the category is new) add a page emitter dispatch case to
   `backend/crew/scaffold_multi.py:scaffold_for_plan`.
4. Add the category to `MULTI_PAGE_CATEGORIES` in
   `backend/crew/manager.py` once the emitter is verified end-to-end.

## Constraint

We deliberately use a **minimal component stack** (react,
react-router-dom, lucide-react, sonner, clsx, tailwind-merge) so generated
output renders cleanly in Sandpack. Richer Open Lovable stack pieces
(Radix, framer-motion, react-hook-form, zod, jotai) are documented as
*aspirational* in `patterns.json` but not imported.
