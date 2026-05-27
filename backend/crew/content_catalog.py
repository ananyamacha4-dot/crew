"""Menu / product / inventory auto-generation.

When the matched template is a coffee shop, restaurant, e-commerce, etc.,
the generated pages need believable data — not Lorem Ipsum, not three
identical placeholder cards. This module owns a set of curated "data packs"
referenced by `awesome-designs/registry.json` under each template's
`data_packs` field.

Each pack is a list of plain dicts. The engineer or scaffold layer can
serialize them straight to a JSON file under `src/data/` so the running
app reads from real-feeling JSON rather than from inline arrays.

The catalog is intentionally small and hand-written — quality over quantity.
For very long inventories (e-commerce of 200 SKUs etc.) the AI content
writer can extend a pack via `generate_inventory()`.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# Curated packs
# ---------------------------------------------------------------------------

COFFEE_MENU: list[dict[str, Any]] = [
    {"name": "Espresso",           "price": "$3.50", "category": "Coffee",        "description": "Single shot of our house roast — bright, full-bodied."},
    {"name": "Americano",          "price": "$4.00", "category": "Coffee",        "description": "Espresso lengthened with hot water."},
    {"name": "Cappuccino",         "price": "$4.75", "category": "Coffee",        "description": "Equal parts espresso, steamed milk, and microfoam."},
    {"name": "Flat White",         "price": "$4.75", "category": "Coffee",        "description": "Double ristretto with silky steamed milk."},
    {"name": "Caramel Latte",      "price": "$5.50", "category": "Coffee",        "description": "Espresso, house caramel, steamed milk."},
    {"name": "Vanilla Latte",      "price": "$5.50", "category": "Coffee",        "description": "Madagascar vanilla, espresso, steamed milk."},
    {"name": "Mocha",              "price": "$5.75", "category": "Coffee",        "description": "Dark chocolate, espresso, steamed milk."},
    {"name": "Cold Brew",          "price": "$5.00", "category": "Cold",          "description": "Steeped 18 hours — smooth, low acidity, served over ice."},
    {"name": "Iced Latte",         "price": "$5.25", "category": "Cold",          "description": "Espresso poured over milk and ice."},
    {"name": "Nitro Cold Brew",    "price": "$5.75", "category": "Cold",          "description": "Cold brew on tap with a cascading nitrogen pour."},
    {"name": "Matcha Latte",       "price": "$5.50", "category": "Tea",           "description": "Ceremonial-grade matcha whisked with steamed milk."},
    {"name": "Chai Latte",         "price": "$5.25", "category": "Tea",           "description": "Spiced black tea concentrate, steamed milk."},
    {"name": "Earl Grey",          "price": "$4.00", "category": "Tea",           "description": "Loose-leaf bergamot-scented black tea."},
    {"name": "Almond Croissant",   "price": "$4.50", "category": "Pastries",      "description": "Toasted almonds, frangipane, powdered sugar."},
    {"name": "Pain au Chocolat",   "price": "$4.25", "category": "Pastries",      "description": "Buttery laminated dough wrapped around dark chocolate."},
    {"name": "Cinnamon Roll",      "price": "$4.50", "category": "Pastries",      "description": "Soft brioche, cinnamon sugar, cream-cheese glaze."},
    {"name": "Avocado Toast",      "price": "$9.00", "category": "Food",          "description": "Sourdough, smashed avocado, chili oil, lemon."},
    {"name": "Smoked Salmon Bagel","price": "$11.00","category": "Food",          "description": "Everything bagel, cream cheese, capers, red onion, dill."},
]


RESTAURANT_MENU: list[dict[str, Any]] = [
    {"name": "Burrata & Heirloom Tomatoes", "price": "$16", "category": "Starters", "description": "Aged balsamic, garden basil, sea salt."},
    {"name": "Tuna Tartare",                "price": "$19", "category": "Starters", "description": "Sushi-grade tuna, avocado, yuzu, taro chip."},
    {"name": "Wild Mushroom Soup",          "price": "$14", "category": "Starters", "description": "Cream of porcini, truffle oil, chive."},
    {"name": "Wagyu Ribeye",                "price": "$58", "category": "Mains",    "description": "12oz dry-aged ribeye, bone marrow butter, frites."},
    {"name": "Pan-Roasted Sea Bass",        "price": "$36", "category": "Mains",    "description": "Saffron broth, fennel, charred lemon."},
    {"name": "Truffle Risotto",             "price": "$28", "category": "Mains",    "description": "Carnaroli rice, shaved black truffle, aged parmesan."},
    {"name": "Half Chicken",                "price": "$26", "category": "Mains",    "description": "Brick-pressed, lemon-thyme jus, market vegetables."},
    {"name": "Tiramisu",                    "price": "$12", "category": "Desserts", "description": "Espresso-soaked savoiardi, mascarpone, cocoa dust."},
    {"name": "Crème Brûlée",                "price": "$11", "category": "Desserts", "description": "Madagascar vanilla custard, brûléed sugar crust."},
    {"name": "Chocolate Lava Cake",         "price": "$13", "category": "Desserts", "description": "Warm flourless cake, vanilla bean ice cream."},
]


BAKERY_MENU: list[dict[str, Any]] = [
    {"name": "Sourdough Loaf",     "price": "$8",  "category": "Bread",    "description": "Naturally leavened, 36-hour cold ferment."},
    {"name": "Country Boule",      "price": "$9",  "category": "Bread",    "description": "Whole wheat blend, crackling crust, open crumb."},
    {"name": "Baguette",           "price": "$5",  "category": "Bread",    "description": "Classic French, baked twice daily."},
    {"name": "Butter Croissant",   "price": "$4.50","category":"Pastries", "description": "81% European butter, 81 layers."},
    {"name": "Almond Croissant",   "price": "$5.25","category":"Pastries", "description": "Filled with frangipane, topped with toasted almonds."},
    {"name": "Kouign-Amann",       "price": "$5.50","category":"Pastries", "description": "Caramelized Breton pastry, salted butter, sugar."},
    {"name": "Chocolate Babka",    "price": "$14", "category": "Pastries", "description": "Brioche braided with dark chocolate, lightly sweet."},
    {"name": "Lemon Tart",         "price": "$7",  "category": "Tarts",    "description": "Meyer lemon curd, torched meringue, sablée crust."},
    {"name": "Fruit Galette",      "price": "$7",  "category": "Tarts",    "description": "Seasonal stone fruit, free-form rustic shell."},
    {"name": "Layer Cake (slice)", "price": "$9",  "category": "Cakes",    "description": "Brown butter cake, vanilla bean buttercream."},
]


FASHION_PRODUCTS: list[dict[str, Any]] = [
    {"name": "Oversized Wool Coat",      "price": "$285", "category": "Outerwear", "sizes": ["XS","S","M","L","XL"]},
    {"name": "Cropped Bomber",           "price": "$165", "category": "Outerwear", "sizes": ["S","M","L","XL"]},
    {"name": "Silk Slip Dress",          "price": "$145", "category": "Dresses",   "sizes": ["XS","S","M","L"]},
    {"name": "Linen Wide-Leg Trouser",   "price": "$98",  "category": "Bottoms",   "sizes": ["24","26","28","30","32"]},
    {"name": "Cashmere Crewneck",        "price": "$175", "category": "Knits",     "sizes": ["XS","S","M","L","XL"]},
    {"name": "Logo Sweatshirt",          "price": "$78",  "category": "Knits",     "sizes": ["S","M","L","XL"]},
    {"name": "Leather Crossbody",        "price": "$220", "category": "Accessories","sizes": ["One Size"]},
    {"name": "Wool Beanie",              "price": "$32",  "category": "Accessories","sizes": ["One Size"]},
    {"name": "Knit Polo",                "price": "$95",  "category": "Tops",      "sizes": ["S","M","L","XL"]},
    {"name": "Pleated Midi Skirt",       "price": "$120", "category": "Bottoms",   "sizes": ["XS","S","M","L"]},
]


ECOMMERCE_PRODUCTS: list[dict[str, Any]] = [
    {"name": "Minimalist Ceramic Mug",      "price": "$24", "category": "Home"},
    {"name": "Walnut Cutting Board",         "price": "$48", "category": "Home"},
    {"name": "Linen Throw Blanket",          "price": "$78", "category": "Home"},
    {"name": "Stoneware Dinner Set",         "price": "$165","category": "Home"},
    {"name": "Brass Desk Lamp",              "price": "$140","category": "Office"},
    {"name": "Leather Notebook",             "price": "$36", "category": "Office"},
    {"name": "Wool Felt Mouse Pad",          "price": "$28", "category": "Office"},
    {"name": "Cotton Tote Bag",              "price": "$22", "category": "Bags"},
    {"name": "Canvas Backpack",              "price": "$95", "category": "Bags"},
    {"name": "Stainless Water Bottle",       "price": "$32", "category": "Outdoor"},
]


PROPERTY_LISTINGS: list[dict[str, Any]] = [
    {"title": "Modern 3BR Townhouse",    "price": "$895,000", "beds": 3, "baths": 2.5, "sqft": 1850, "location": "Capitol Hill, Seattle"},
    {"title": "Lakefront 4BR Estate",    "price": "$1,985,000","beds": 4, "baths": 3,   "sqft": 3200, "location": "Lake Union, Seattle"},
    {"title": "Loft-Style 1BR Condo",    "price": "$525,000", "beds": 1, "baths": 1,   "sqft": 920,  "location": "Belltown, Seattle"},
    {"title": "Craftsman Bungalow",      "price": "$725,000", "beds": 3, "baths": 2,   "sqft": 1650, "location": "Ballard, Seattle"},
    {"title": "Penthouse with City View", "price": "$2,400,000","beds": 3, "baths": 3.5, "sqft": 2750, "location": "Downtown, Seattle"},
]


TRAVEL_DESTINATIONS: list[dict[str, Any]] = [
    {"name": "Kyoto, Japan",          "tagline": "Temples, gardens, quiet streets",   "from_price": "$1,890"},
    {"name": "Lisbon, Portugal",      "tagline": "Tiled facades, miradouros, fado",   "from_price": "$1,240"},
    {"name": "Reykjavík, Iceland",    "tagline": "Northern lights, glaciers, hot springs","from_price": "$1,650"},
    {"name": "Marrakech, Morocco",    "tagline": "Souks, riads, the Atlas at sunset", "from_price": "$1,180"},
    {"name": "Queenstown, NZ",        "tagline": "Alps, fjords, adventure",           "from_price": "$2,140"},
    {"name": "Mexico City, Mexico",   "tagline": "Frida, mole, neighborhood culture", "from_price": "$980"},
]


DASHBOARD_METRICS: list[dict[str, Any]] = [
    {"label": "MRR",            "value": "$148.2K",   "delta": "+12.4%", "trend": "up"},
    {"label": "Active Users",   "value": "24,815",    "delta": "+3.1%",  "trend": "up"},
    {"label": "Conversion",     "value": "4.7%",      "delta": "-0.2%",  "trend": "down"},
    {"label": "Avg. Session",   "value": "5m 12s",    "delta": "+8s",    "trend": "up"},
]


EXPENSE_CATEGORIES: list[dict[str, Any]] = [
    {"category": "Groceries",       "icon": "ShoppingCart", "budget": 600},
    {"category": "Dining",          "icon": "Coffee",       "budget": 250},
    {"category": "Transport",       "icon": "Car",          "budget": 200},
    {"category": "Subscriptions",   "icon": "Repeat",       "budget": 95},
    {"category": "Utilities",       "icon": "Zap",          "budget": 180},
    {"category": "Entertainment",   "icon": "Music",        "budget": 120},
]


MUSIC_TRACKS: list[dict[str, Any]] = [
    {"title": "Midnight Drive",     "artist": "Nova Bloom",   "album": "Neon Skylines",  "duration": "3:42"},
    {"title": "Glass Sky",          "artist": "Hana Moriya",  "album": "Glass Sky",      "duration": "4:11"},
    {"title": "Slow Tide",          "artist": "Atlas & Eden", "album": "Anchor",         "duration": "3:55"},
    {"title": "Paper Cranes",       "artist": "Yuki Park",    "album": "Folded Light",   "duration": "3:18"},
    {"title": "Late Bloomer",       "artist": "Cassia June",  "album": "After Hours",    "duration": "4:02"},
    {"title": "Quiet Engines",      "artist": "Halo District","album": "Static Garden",  "duration": "3:34"},
]


COURSES: list[dict[str, Any]] = [
    {"title": "Intro to Web Design",          "instructor": "Marisol Tan", "duration": "8h",  "level": "Beginner"},
    {"title": "React from Scratch",           "instructor": "Devin Park",  "duration": "14h", "level": "Beginner"},
    {"title": "Type Systems with TypeScript", "instructor": "Anika Rao",   "duration": "11h", "level": "Intermediate"},
    {"title": "Designing for Accessibility",  "instructor": "Imani Cole",  "duration": "6h",  "level": "Intermediate"},
    {"title": "Systems Design Deep-Dive",     "instructor": "Yusuf Demir", "duration": "18h", "level": "Advanced"},
]


# ---------------------------------------------------------------------------
# Niche-specific menus (additive — do not replace RESTAURANT_MENU)
# ---------------------------------------------------------------------------

CHINESE_RESTAURANT_MENU: list[dict[str, Any]] = [
    {"name": "Steamed Pork Dumplings (Xiao Long Bao)", "price": "$13", "category": "Dim Sum",        "description": "Soup-filled dumplings, ginger-vinegar dipping sauce.",          "image_subject": "xiao long bao steamer top down"},
    {"name": "Shrimp Har Gow",                          "price": "$12", "category": "Dim Sum",        "description": "Crystal-skinned dumplings with whole shrimp.",                  "image_subject": "har gow translucent dumpling bamboo steamer"},
    {"name": "Pan-Fried Pork Buns (Sheng Jian Bao)",    "price": "$11", "category": "Dim Sum",        "description": "Crisp-bottomed buns, sesame, scallion, juicy pork.",            "image_subject": "sheng jian bao pan fried buns"},
    {"name": "Kung Pao Chicken",                        "price": "$22", "category": "Sichuan Mains", "description": "Wok-tossed chicken, peanuts, dried chilies, Sichuan pepper.",   "image_subject": "kung pao chicken sichuan wok"},
    {"name": "Mapo Tofu",                               "price": "$19", "category": "Sichuan Mains", "description": "Silken tofu, fermented bean, ground pork, numbing chili oil.",  "image_subject": "mapo tofu sichuan red chili"},
    {"name": "Dry-Fried Green Beans",                   "price": "$17", "category": "Sichuan Mains", "description": "Blistered long beans with minced pork and preserved mustard.",  "image_subject": "dry fried green beans sichuan"},
    {"name": "Peking Duck (Half)",                      "price": "$48", "category": "House Specials","description": "Lacquered duck, thin pancakes, scallion, hoisin.",              "image_subject": "peking duck carved restaurant"},
    {"name": "Salt & Pepper Squid",                     "price": "$21", "category": "House Specials","description": "Crisp-fried squid, garlic, white pepper, jalapeño.",            "image_subject": "salt pepper squid crispy"},
    {"name": "Whole Steamed Sea Bass",                  "price": "$42", "category": "House Specials","description": "Ginger, scallion, hot soy, sizzling oil at the table.",        "image_subject": "whole steamed sea bass ginger scallion"},
    {"name": "Hand-Pulled Beef Noodles",                "price": "$18", "category": "Noodles & Rice","description": "Lanzhou-style broth, daikon, cilantro, chili oil.",             "image_subject": "hand pulled beef noodles bowl steam"},
    {"name": "Dan Dan Noodles",                         "price": "$16", "category": "Noodles & Rice","description": "Chili oil, preserved vegetable, peanuts, ground pork.",         "image_subject": "dan dan noodles chili oil"},
    {"name": "Yangzhou Fried Rice",                     "price": "$15", "category": "Noodles & Rice","description": "Shrimp, char siu, egg, scallion, jasmine rice.",                "image_subject": "yangzhou fried rice plate"},
    {"name": "Mongolian Hot Pot (per person)",          "price": "$36", "category": "Hot Pot",       "description": "Choose mild or spicy broth; sliced lamb, tofu, leafy greens.",   "image_subject": "hot pot bubbling spicy lamb"},
    {"name": "Mango Pudding",                           "price": "$9",  "category": "Desserts",      "description": "Coconut cream, fresh Alphonso mango, sago pearls.",             "image_subject": "mango pudding coconut cream"},
    {"name": "Sesame Balls (Jian Dui)",                 "price": "$8",  "category": "Desserts",      "description": "Golden glutinous rice spheres with sweet lotus paste.",         "image_subject": "sesame balls jian dui dessert"},
    {"name": "Jasmine Tea (Pot)",                       "price": "$6",  "category": "Tea & Drinks",  "description": "Whole-leaf jasmine pearls steeped tableside.",                  "image_subject": "jasmine tea porcelain pot pour"},
    {"name": "Oolong Tea (Pot)",                        "price": "$7",  "category": "Tea & Drinks",  "description": "Roasted Wuyi oolong, layered and complex.",                     "image_subject": "oolong tea porcelain cup"},
]


SAAS_FEATURES: list[dict[str, Any]] = [
    {"title": "Realtime collaboration",   "description": "Multi-cursor editing, presence, and live comments — no refresh needed.", "icon": "Users",       "image_subject": "abstract realtime collaboration multi cursor"},
    {"title": "End-to-end encryption",    "description": "Customer-managed keys, encrypted at rest and in transit.",                "icon": "ShieldCheck", "image_subject": "abstract data encryption shield"},
    {"title": "API-first",                "description": "Every dashboard action has an idempotent REST + GraphQL counterpart.",    "icon": "Code",        "image_subject": "code editor api request response"},
    {"title": "Audit log",                "description": "Immutable trail of every change, exportable to your SIEM.",               "icon": "Activity",    "image_subject": "audit log timeline minimal dashboard"},
    {"title": "SSO / SAML",               "description": "Okta, Google Workspace, Microsoft Entra, and any SAML 2.0 IdP.",          "icon": "Lock",        "image_subject": "single sign on flow diagram"},
    {"title": "Granular permissions",     "description": "Role-based access down to the row level — no shared admin accounts.",     "icon": "Settings",    "image_subject": "permission matrix grid dashboard"},
    {"title": "Custom workflows",         "description": "Drag-build automations that fire on events and call your APIs.",          "icon": "Zap",         "image_subject": "workflow automation node graph"},
    {"title": "Self-hosted option",       "description": "Run the same binary on your VPC. No code changes required.",              "icon": "Cloud",       "image_subject": "private cloud server rack abstract"},
]


SAAS_PLANS: list[dict[str, Any]] = [
    {
        "name": "Hobby", "price": "$0", "period": "/mo",
        "description": "For exploring on your own.",
        "features": ["Up to 3 projects", "Community support", "Basic integrations", "1 GB storage"],
        "cta_label": "Start free", "highlighted": False,
    },
    {
        "name": "Team", "price": "$24", "period": "/mo per seat",
        "description": "For small teams shipping together.",
        "features": ["Unlimited projects", "Realtime collaboration", "SSO with Google", "100 GB storage", "Email support"],
        "cta_label": "Start trial", "highlighted": True,
    },
    {
        "name": "Enterprise", "price": "Custom", "period": "",
        "description": "For organizations with compliance needs.",
        "features": ["SAML / SCIM", "Audit log + SIEM export", "Custom data residency", "Dedicated support engineer", "99.99% SLA"],
        "cta_label": "Contact sales", "highlighted": False,
    },
]


SAAS_CHANGELOG: list[dict[str, Any]] = [
    {"date": "2025-02-11", "title": "Realtime presence v2",            "body": "Cursor presence now bursts to 500 concurrent collaborators on a single document."},
    {"date": "2025-01-28", "title": "Workflow templates",              "body": "Twelve starter automations covering onboarding, ETL, and alerting flows."},
    {"date": "2025-01-14", "title": "SAML auto-provisioning",          "body": "SCIM 2.0 user/group sync for Okta and Microsoft Entra."},
    {"date": "2024-12-19", "title": "Granular row-level permissions",  "body": "Permissions can now be scoped per record, not just per project."},
    {"date": "2024-12-03", "title": "API rate-limit dashboard",        "body": "See per-token and per-endpoint quotas in real time."},
    {"date": "2024-11-19", "title": "Self-hosted GA",                  "body": "The single-binary self-hosted distribution is now generally available."},
]


PORTFOLIO_PROJECTS: list[dict[str, Any]] = [
    {"title": "Acre — banking app",          "role": "Lead Product Designer",         "year": "2024", "tags": ["mobile", "fintech", "design system"],     "summary": "Reframed onboarding for a regulated neobank; 38% lift in first-week activation.", "image_subject": "modern banking app screen minimal"},
    {"title": "Folio — publisher CMS",       "role": "UX + frontend",                  "year": "2024", "tags": ["web", "cms", "editorial"],                "summary": "Built a block-based editor and live preview for a magazine network.",              "image_subject": "cms admin dashboard editorial"},
    {"title": "Slate — typography tool",     "role": "Solo developer",                 "year": "2023", "tags": ["tools", "typography", "browser"],         "summary": "A browser tool for sketching display type with variable axes.",                   "image_subject": "typography variable font tool screen"},
    {"title": "Atlas — travel planner",      "role": "Product + visual design",        "year": "2023", "tags": ["mobile", "travel", "maps"],                "summary": "Day-by-day itineraries powered by a route engine and offline maps.",              "image_subject": "travel app itinerary map screen"},
    {"title": "Studio site rebuild",         "role": "Brand + web",                    "year": "2022", "tags": ["brand", "web", "motion"],                  "summary": "Editorial redesign with a custom serif system and case-study templates.",         "image_subject": "design studio website minimal editorial"},
    {"title": "Aurora — climate dashboard",  "role": "Design partner",                 "year": "2022", "tags": ["data viz", "climate", "dashboard"],        "summary": "Visualizing community-level emissions reductions for a policy team.",             "image_subject": "climate data visualization dashboard"},
]


PORTFOLIO_JOURNAL: list[dict[str, Any]] = [
    {"date": "2025-02-02", "title": "On honest design briefs",     "summary": "Why we now write the brief together with the client.", "minutes": 5},
    {"date": "2025-01-12", "title": "Variable type without tears", "summary": "A small set of habits that keep variable-font work calm.", "minutes": 8},
    {"date": "2024-12-20", "title": "Year in review, quietly",    "summary": "A short list of what worked and what to leave behind.",  "minutes": 4},
    {"date": "2024-11-08", "title": "On saying 'maybe later'",     "summary": "A defense of holding scope back until the work is older.", "minutes": 3},
]


PORTFOLIO_SKILLS: list[dict[str, Any]] = [
    {"label": "Product design",      "level": "lead"},
    {"label": "Brand systems",       "level": "lead"},
    {"label": "Design tokens",       "level": "lead"},
    {"label": "React + TypeScript",  "level": "shipping"},
    {"label": "Framer Motion",       "level": "shipping"},
    {"label": "Tailwind CSS",        "level": "shipping"},
    {"label": "Variable typography", "level": "shipping"},
    {"label": "Motion direction",    "level": "exploring"},
]


HEALTHCARE_SERVICES: list[dict[str, Any]] = [
    {"title": "Primary care",        "description": "Annual physicals, preventive screenings, and acute visits with a clinician who knows your history.", "icon": "Heart",       "image_subject": "doctor consultation patient bright clinic"},
    {"title": "Pediatrics",          "description": "Well-child visits, vaccinations, and gentle care for children from birth through adolescence.",      "icon": "User",        "image_subject": "pediatrician with child examination room friendly"},
    {"title": "Women's health",      "description": "OB-GYN visits, prenatal care, and routine screenings in a calm, modern space.",                     "icon": "Sparkles",    "image_subject": "modern womens health clinic interior bright"},
    {"title": "Mental health",       "description": "Therapy and medication management with licensed clinicians, in-person or via telehealth.",          "icon": "Brain",       "image_subject": "therapy session calm room natural light"},
    {"title": "Dental",              "description": "Cleanings, restorative work, and cosmetic dentistry with same-day appointments available.",        "icon": "Smile",       "image_subject": "modern dental clinic chair bright"},
    {"title": "Physical therapy",    "description": "Recovery and performance plans built by movement specialists.",                                     "icon": "Activity",    "image_subject": "physical therapy session bright gym natural light"},
    {"title": "Lab & imaging",       "description": "On-site phlebotomy, ultrasound, and x-ray with same-day results for most panels.",                  "icon": "ShieldCheck", "image_subject": "modern medical lab clean bright"},
    {"title": "Telehealth",          "description": "Same-day video visits with a clinician for non-urgent concerns, prescriptions included.",          "icon": "Video",       "image_subject": "doctor video call laptop modern home office"},
]


HEALTHCARE_DOCTORS: list[dict[str, Any]] = [
    {"name": "Dr. Amelia Park, MD",     "role": "Family Medicine",    "credentials": "MD, Board Certified", "bio": "Twelve years in primary care; emphasis on shared decision-making and clear plans.", "image_subject": "smiling female doctor white coat portrait neutral background"},
    {"name": "Dr. Marcus Chen, DDS",    "role": "Dentistry",          "credentials": "DDS, AGD Fellow",     "bio": "Restorative and cosmetic dentistry with a calm, no-rush approach.",                "image_subject": "smiling male dentist portrait modern clinic"},
    {"name": "Dr. Priya Rao, PsyD",     "role": "Behavioral Health",  "credentials": "PsyD, Licensed",      "bio": "Therapy for anxiety, mood, and life transitions — in-person and telehealth.",        "image_subject": "smiling female therapist portrait warm background"},
    {"name": "Dr. Jordan Hayes, DPT",   "role": "Physical Therapy",   "credentials": "DPT, OCS",            "bio": "Sports recovery, post-op rehab, and movement coaching.",                              "image_subject": "smiling male physical therapist portrait bright gym"},
    {"name": "Dr. Naomi Olsen, MD",     "role": "Pediatrics",         "credentials": "MD, FAAP",            "bio": "Newborn to teen care with a focus on family education.",                               "image_subject": "smiling female pediatrician portrait friendly"},
    {"name": "Dr. Samuel Ortiz, DO",    "role": "Internal Medicine",  "credentials": "DO, Board Certified", "bio": "Chronic disease management and preventive medicine.",                                  "image_subject": "smiling male doctor portrait office neutral background"},
]


HEALTHCARE_TESTIMONIALS: list[dict[str, Any]] = [
    {"quote": "First clinic where I didn't feel rushed. Dr. Park actually answered every question I had.", "author": "Maya P.",    "role": "Patient since 2022"},
    {"quote": "My kids actually look forward to their visits now. The pediatric team is wonderful.",        "author": "Daniel & Sara N.", "role": "Parents"},
    {"quote": "The telehealth option saved me a four-hour round trip during a tough recovery.",            "author": "Aaron T.",    "role": "Patient since 2024"},
]


JAPANESE_RESTAURANT_MENU: list[dict[str, Any]] = [
    {"name": "Chef's Sashimi (12 pcs)",     "price": "$38", "category": "Sashimi & Sushi", "description": "Daily selection of three fish, freshly sliced.",                 "image_subject": "sashimi platter chef selection"},
    {"name": "Omakase Nigiri (8 pcs)",      "price": "$54", "category": "Sashimi & Sushi", "description": "Eight pieces of chef-selected nigiri over warm rice.",           "image_subject": "omakase nigiri counter"},
    {"name": "Spicy Tuna Roll",             "price": "$16", "category": "Sashimi & Sushi", "description": "Tuna, scallion, chili mayo, cucumber.",                          "image_subject": "spicy tuna roll plated"},
    {"name": "Tonkotsu Ramen",              "price": "$19", "category": "Ramen",           "description": "Pork bone broth, chashu, ajitama, scallion, kikurage.",          "image_subject": "tonkotsu ramen bowl steam dark wood"},
    {"name": "Miso Ramen",                  "price": "$18", "category": "Ramen",           "description": "Red miso, ground pork, corn, scallion, butter.",                 "image_subject": "miso ramen butter corn"},
    {"name": "Shoyu Ramen",                 "price": "$17", "category": "Ramen",           "description": "Light chicken-shoyu broth, menma, nori, soft egg.",              "image_subject": "shoyu ramen clear broth"},
    {"name": "Vegetable Tempura",           "price": "$15", "category": "Izakaya",         "description": "Seasonal vegetables, light tempura batter, tentsuyu.",           "image_subject": "vegetable tempura plate"},
    {"name": "Chicken Karaage",             "price": "$13", "category": "Izakaya",         "description": "Marinated fried chicken thigh, lemon, kewpie.",                  "image_subject": "chicken karaage japanese"},
    {"name": "Grilled Yakitori (3 skewers)","price": "$14", "category": "Izakaya",         "description": "Thigh + scallion, breast + shiso, tsukune meatball.",            "image_subject": "yakitori skewers charcoal grill"},
    {"name": "Unagi Donburi",               "price": "$26", "category": "Donburi",         "description": "Grilled freshwater eel, tare glaze, warm rice.",                 "image_subject": "unagi donburi bowl"},
    {"name": "Mochi Ice Cream (3 pcs)",     "price": "$9",  "category": "Desserts",        "description": "Matcha, black sesame, yuzu.",                                    "image_subject": "mochi ice cream trio"},
    {"name": "Matcha Tea (Whisked)",        "price": "$7",  "category": "Tea & Sake",      "description": "Ceremonial grade matcha, traditional preparation.",              "image_subject": "matcha whisked chawan"},
]


# ---------------------------------------------------------------------------
# Pack registry (extended)
# ---------------------------------------------------------------------------

_PACKS: dict[str, list[dict[str, Any]]] = {
    "coffee_menu":              COFFEE_MENU,
    "restaurant_menu":          RESTAURANT_MENU,
    "bakery_menu":              BAKERY_MENU,
    "fashion_products":         FASHION_PRODUCTS,
    "ecommerce_products":       ECOMMERCE_PRODUCTS,
    "property_listings":        PROPERTY_LISTINGS,
    "travel_destinations":      TRAVEL_DESTINATIONS,
    "dashboard_metrics":        DASHBOARD_METRICS,
    "expense_categories":       EXPENSE_CATEGORIES,
    "music_tracks":             MUSIC_TRACKS,
    "courses":                  COURSES,
    "chinese_restaurant_menu":  CHINESE_RESTAURANT_MENU,
    "japanese_restaurant_menu": JAPANESE_RESTAURANT_MENU,
    # Open Lovable reference packs (additive — used by the new archetype scaffolders)
    "saas_features":            SAAS_FEATURES,
    "saas_plans":               SAAS_PLANS,
    "saas_changelog":           SAAS_CHANGELOG,
    "portfolio_projects":       PORTFOLIO_PROJECTS,
    "portfolio_journal":        PORTFOLIO_JOURNAL,
    "portfolio_skills":         PORTFOLIO_SKILLS,
    "healthcare_services":      HEALTHCARE_SERVICES,
    "healthcare_doctors":       HEALTHCARE_DOCTORS,
    "healthcare_testimonials":  HEALTHCARE_TESTIMONIALS,
}


# ---------------------------------------------------------------------------
# Niche -> pack resolver (used by template intelligence engine)
# ---------------------------------------------------------------------------

# (category, sub_niche) -> pack name. sub_niche None means "default for this category".
_NICHE_TO_PACK: dict[tuple[str, str | None], str] = {
    ("restaurant", "chinese"):    "chinese_restaurant_menu",
    ("restaurant", "japanese"):   "japanese_restaurant_menu",
    ("restaurant", "italian"):    "restaurant_menu",
    ("restaurant", "french"):     "restaurant_menu",
    ("restaurant", "mexican"):    "restaurant_menu",
    ("restaurant", "indian"):     "restaurant_menu",
    ("restaurant", "thai"):       "restaurant_menu",
    ("restaurant", "steakhouse"): "restaurant_menu",
    ("restaurant", "cafe"):       "coffee_menu",
    ("restaurant", "bakery"):     "bakery_menu",
    ("restaurant", None):         "restaurant_menu",
    ("ecommerce",  "fashion"):    "fashion_products",
    ("ecommerce",  "electronics"):"ecommerce_products",
    ("ecommerce",  "furniture"):  "ecommerce_products",
    ("ecommerce",  None):         "ecommerce_products",
    # Open Lovable archetypes — point to the primary data pack each scaffolder reads.
    ("saas",       None):              "saas_features",
    ("saas",       "b2b-saas"):        "saas_features",
    ("saas",       "ai-saas"):         "saas_features",
    ("saas",       "developer-tool"):  "saas_features",
    ("portfolio",  None):                  "portfolio_projects",
    ("portfolio",  "designer-portfolio"):  "portfolio_projects",
    ("portfolio",  "dev-portfolio"):       "portfolio_projects",
    ("portfolio",  "photographer-portfolio"): "portfolio_projects",
    ("healthcare", None):       "healthcare_services",
    ("healthcare", "clinic"):   "healthcare_services",
    ("healthcare", "hospital"): "healthcare_services",
    ("healthcare", "dental"):   "healthcare_services",
    ("healthcare", "wellness"): "healthcare_services",
}


def pack_for_niche(category: str, sub_niche: str | None) -> list[dict[str, Any]] | None:
    """Return the curated content pack for a (category, sub_niche) pair.

    Falls back to the category default when the sub_niche has no specific
    pack. Returns None if the category itself is not recognized — the caller
    should treat that as "no niche data, generate from scratch".
    """
    key = (category, sub_niche)
    pack_name = _NICHE_TO_PACK.get(key)
    if pack_name is None and sub_niche is not None:
        pack_name = _NICHE_TO_PACK.get((category, None))
    if pack_name is None:
        return None
    pack = _PACKS.get(pack_name)
    if pack is None:
        return None
    return [dict(item) for item in pack]


def pack_name_for_niche(category: str, sub_niche: str | None) -> str | None:
    """Return the resolved pack NAME (not data) for a niche, useful for trail logs."""
    key = (category, sub_niche)
    pack_name = _NICHE_TO_PACK.get(key)
    if pack_name is None and sub_niche is not None:
        pack_name = _NICHE_TO_PACK.get((category, None))
    return pack_name


def pack_names() -> list[str]:
    return sorted(_PACKS.keys())


def get_pack(name: str) -> list[dict[str, Any]]:
    """Return a copy of the named pack, or [] if unknown."""
    raw = _PACKS.get(name) or []
    return [dict(item) for item in raw]


def get_packs(names: Iterable[str]) -> dict[str, list[dict[str, Any]]]:
    return {n: get_pack(n) for n in names if n in _PACKS}


def serialize_pack(name: str, *, indent: int = 2) -> str:
    return json.dumps(get_pack(name), indent=indent, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Inventory generator — synthetic items for long-tail inventories
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InventoryRule:
    """Recipe for synthesizing a long inventory from a small base pack."""
    base_pack: str
    variants_per_item: int = 1
    price_jitter: tuple[int, int] = (-2, 5)


def generate_inventory(rule: InventoryRule, *, seed: int | None = None) -> list[dict[str, Any]]:
    """Expand a base pack into a larger inventory with stable, seeded variation.

    Useful when a template wants 60 products on a category page but the
    curated pack only has 10. We never invent fields — we just clone with
    small numeric jitter on `price`, and a numeric suffix on `name`.
    """
    rng = random.Random(seed)
    base = get_pack(rule.base_pack)
    if not base:
        return []
    out: list[dict[str, Any]] = []
    for item in base:
        out.append(dict(item))
        for variant_idx in range(1, max(0, rule.variants_per_item) + 1):
            new = dict(item)
            new["name"] = f"{item.get('name', 'Item')} · v{variant_idx + 1}"
            if "price" in new and isinstance(new["price"], str) and new["price"].startswith("$"):
                try:
                    base_val = float(new["price"][1:].replace(",", ""))
                    delta = rng.uniform(*rule.price_jitter)
                    bumped = max(1.0, round(base_val + delta, 2))
                    new["price"] = f"${bumped:g}"
                except ValueError:
                    pass
            out.append(new)
    return out
