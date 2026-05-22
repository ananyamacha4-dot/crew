# Architecture & Flow

Project: **Multi-Role Agent Chat** — one chat box. User types a prompt. A manager LLM picks the right specialist role(s). The right answer comes back.

---

## High-level diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                          BROWSER (Next.js)                           │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  Chat UI  (app/page.tsx)                                       │  │
│  │   - message list                                               │  │
│  │   - input box                                                  │  │
│  │   - "thinking..." indicator                                    │  │
│  └────────────────────┬───────────────────────────────────────────┘  │
└───────────────────────┼──────────────────────────────────────────────┘
                        │  POST /chat  { prompt, history }
                        ▼
┌──────────────────────────────────────────────────────────────────────┐
│                       BACKEND (FastAPI)                              │
│                                                                      │
│   app/main.py                                                        │
│      └── POST /chat ──┐                                              │
│                       │                                              │
│                       ▼                                              │
│              crew/manager.py                                         │
│              build_crew() → Crew(process=hierarchical)               │
│                       │                                              │
│                       ▼                                              │
│           ┌──────────────────────────────┐                           │
│           │     MANAGER LLM (gpt-4o)     │  ◀── reads role/goal      │
│           │     "Which agent fits this   │      of each specialist   │
│           │      prompt? Delegate."      │      and picks one        │
│           └──────────────┬───────────────┘                           │
│                          │ delegates                                 │
│       ┌──────────┬───────┴────────┬──────────┐                       │
│       ▼          ▼                ▼          ▼                       │
│   Researcher   Coder            Writer       QA                      │
│   (Serper)     (python ideas)   (markdown)   (review)                │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
                        │
                        ▼  { reply, trace[] }
                  back to browser
```

---

## Request flow (step by step)

1. User types **"Research the latest Next.js 15 features and write a 200-word summary"** in the chat.
2. Browser sends `POST /chat` with the prompt.
3. FastAPI builds a `Crew` in `Process.hierarchical` mode.
4. Manager LLM reads:
   - `Researcher.role` = "Researcher" / goal = "find current info via web search"
   - `Coder.role` = "Python Developer"
   - `Writer.role` = "Technical Writer"
   - `QA.role` = "QA Reviewer"
5. Manager decides: *"prompt needs research + writing"* → delegates to Researcher first.
6. Researcher uses the Serper tool, returns notes.
7. Manager passes notes to Writer → Writer produces the 200-word summary.
8. (Optional) QA reviews.
9. Final string flows back through FastAPI → browser → rendered in chat.

**Key idea:** the user never chooses a role. The prompt itself decides who answers, via the manager LLM. That's the "prompt orchestration" the CTO asked for.

---

## Folder layout

```
crew-ai/
├── ARCHITECTURE.md          ← this file
├── CREWAI_GUIDE.md          ← developer guide
├── README.md                ← how to run
├── .gitignore
│
├── backend/                 ← Python / FastAPI / CrewAI
│   ├── .env.example
│   ├── requirements.txt
│   ├── main.py              ← FastAPI app, POST /chat
│   └── crew/
│       ├── __init__.py
│       ├── manager.py       ← builds the Crew
│       └── agents/
│           ├── __init__.py
│           ├── researcher.py
│           ├── coder.py
│           ├── writer.py
│           └── qa.py
│
└── frontend/                ← Next.js (app router, TypeScript)
    ├── package.json
    ├── tsconfig.json
    ├── next.config.mjs
    ├── .env.local.example
    └── app/
        ├── layout.tsx
        ├── page.tsx         ← chat UI
        └── globals.css
```

---

## Component responsibilities

| Component | Responsibility | Stays out of |
|---|---|---|
| `frontend/app/page.tsx` | Chat UI, send message, render history | Knows nothing about CrewAI internals |
| `backend/main.py` | HTTP layer: validate input, call crew, return JSON | Knows nothing about the UI |
| `backend/crew/manager.py` | Assemble agents + task + crew, run `kickoff()` | Knows nothing about HTTP |
| `backend/crew/agents/*.py` | One file per role. Define `role`, `goal`, `backstory`, `tools` | Knows nothing about each other — the manager wires them |

This separation is what makes the architecture **clean and pleasant**:
- Add a new role → one new file in `agents/`, one line in `manager.py`. UI doesn't change.
- Swap models (gpt-4o → claude) → one line in `manager.py`. Agents don't change.
- Redesign chat UI → only `page.tsx` / `globals.css`. Backend doesn't change.

---

## Why hierarchical (not sequential)

The CTO's requirement is *"the prompt selects the role"*. That's `Process.hierarchical`:

| | `Process.sequential` | `Process.hierarchical` |
|---|---|---|
| Who decides order? | Developer hard-codes it | Manager LLM decides at runtime |
| Add a new prompt type | Need new code path | Just add an agent, manager routes |
| Cost | Cheaper (fewer LLM calls) | More expensive (manager + workers) |
| Fit for your task | ✗ | ✓ |

---

## Data contract between frontend and backend

**Request** (`POST /chat`):

```json
{
  "prompt": "string — the user's message",
  "history": [
    {"role": "user",      "content": "previous user message"},
    {"role": "assistant", "content": "previous assistant reply"}
  ]
}
```

**Response**:

```json
{
  "reply": "string — the final answer",
  "agent_used": "Researcher | Coder | Writer | QA | Manager",
  "trace": ["optional debug strings showing routing decisions"]
}
```

This contract is the only thing both sides agree on. Either side can be rewritten independently as long as the contract holds.

---

## What's NOT in v1 (intentionally cut)

- Persistent chat history (in-memory only per request). Add a DB later.
- User accounts / auth.
- Streaming responses (token-by-token). Add via SSE later.
- File uploads.

Keep v1 simple → demo to the CTO → then layer features.
