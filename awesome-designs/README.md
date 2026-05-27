# awesome-designs

Premium starter-template registry for the AI Builder. Each entry below is a
high-level **template manifest** the matcher uses to seed a generation. The
generator combines the manifest with the user's prompt to produce a multi-page
React + Vite + Tailwind project.

This folder is **purely additive**. Nothing in the existing pipeline reads from
it unless the new `backend/crew/templates/` module is wired in by the manager.

## Structure

```
awesome-designs/
├── README.md                         # this file
├── registry.json                     # all 30 template manifests
├── coffee-shop/template.json         # example per-category manifest
├── restaurant/template.json
├── dashboard-analytics/template.json
└── ...
```

A manifest has the shape:

```json
{
  "key": "coffee-shop",
  "label": "Coffee Shop",
  "category": "hospitality",
  "kind": "website",
  "match_keywords": ["coffee", "cafe", "espresso", "barista"],
  "pages": [
    { "name": "Home",    "route": "/",         "sections": ["hero", "menu-preview", "story", "locations"] },
    { "name": "Menu",    "route": "/menu",     "sections": ["menu-grid", "drink-builder"] },
    { "name": "Shop",    "route": "/shop",     "sections": ["product-grid", "cart-drawer"] }
  ],
  "navigation": [
    { "label": "Menu", "route": "/menu" },
    { "label": "Shop", "route": "/shop" }
  ],
  "design": {
    "palette_hint": "warm-cream",
    "mood": ["warm", "artisanal", "cozy"],
    "fonts": { "display": "Fraunces", "body": "Inter" }
  },
  "image_subjects": ["latte art", "espresso machine", "coffee beans", "cafe interior"],
  "data_packs": ["coffee_menu", "store_locations"]
}
```

## Categories

| # | Key | Kind |
|---|---|---|
| 1 | coffee-shop | website |
| 2 | restaurant | website |
| 3 | fashion-store | website |
| 4 | bakery | website |
| 5 | ai-saas | landing |
| 6 | startup-landing | landing |
| 7 | music-streaming | app |
| 8 | chat-application | app |
| 9 | dashboard-analytics | app |
| 10 | kanban-board | app |
| 11 | expense-tracker | app |
| 12 | portfolio | website |
| 13 | agency | website |
| 14 | real-estate | website |
| 15 | photography | website |
| 16 | fitness | website |
| 17 | travel-booking | website |
| 18 | hotel | website |
| 19 | ecommerce | website |
| 20 | furniture-store | website |
| 21 | car-showcase | website |
| 22 | education-platform | website |
| 23 | movie-streaming | app |
| 24 | food-delivery | app |
| 25 | crypto-dashboard | app |
| 26 | banking-app | app |
| 27 | medical-clinic | website |
| 28 | gaming-platform | website |
| 29 | news-magazine | website |
| 30 | social-media | app |
