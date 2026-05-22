# CrewAI AI Builder

A working end-to-end prompt-to-app builder:

- Frontend: Next.js and TypeScript
- Backend: FastAPI and CrewAI
- Agent pipeline: prompt planning, code generation, review, and saved project files

```text
Browser -> Next.js frontend -> FastAPI backend -> CrewAI -> LLM provider
Browser <- Next.js frontend <- FastAPI backend <- generated files
```

## Prerequisites

- Python 3.11+ (`python --version`)
- Node.js 18+ (`node --version`)
- At least one LLM provider key in `backend/.env`: `GROQ_API_KEY`, `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY`

## 1) Backend Setup

Open PowerShell in this folder:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Open `backend\.env` and add your real provider key. Example:

```text
OPENAI_API_KEY=sk-your-real-key-here
WORKER_MODEL=gpt-4o-mini
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3001
```

Start the backend:

```powershell
uvicorn main:app --reload --port 8000
```

You should see `Uvicorn running on http://127.0.0.1:8000`.

Test it in another PowerShell:

```powershell
curl http://localhost:8000/
```

The response should include `status`, `worker_model`, and `providers`.

## 2) Frontend Setup

Open a second PowerShell in this folder:

```powershell
cd frontend
npm install
```

Optional: copy the frontend env example if your backend is not on the default port:

```powershell
copy .env.local.example .env.local
```

Start the frontend:

```powershell
npm run dev
```

Open the URL Next.js prints. It is usually `http://localhost:3000`, but it may use `http://localhost:3001` if port 3000 is already busy.

## How It Works

1. You type a prompt in the browser and press Enter.
2. `frontend/app/lib/api.ts` sends `POST http://localhost:8000/generate` with `{ prompt, project_id }`.
3. `backend/main.py` receives the request and runs the CrewAI generation pipeline.
4. The backend returns generated project files, an agent trail, and a message.
5. The frontend renders the generated artifact and lets you edit saved files.

## File Map

```text
crew-ai/
  README.md
  ARCHITECTURE.md
  CREWAI_GUIDE.md
  backend/
    .env
    .env.example
    requirements.txt
    main.py
    crew/
  frontend/
    .env.local.example
    package.json
    tsconfig.json
    next.config.mjs
    app/
      layout.tsx
      page.tsx
      lib/api.ts
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `Error: Failed to fetch` | Make sure the backend is running on port 8000 and CORS allows the frontend origin. This project allows `localhost:3000` and `localhost:3001` by default. |
| Browser is on `localhost:3001` | That is okay. Next.js uses 3001 when 3000 is busy. Keep `ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3001` in `backend/.env`. |
| Backend health response looks old, for example only `model` and `openai_key` | Stop the old uvicorn/python process on port 8000, then restart from this repo's `backend` folder. |
| No provider key configured | Add `GROQ_API_KEY`, `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY` to `backend/.env`, then restart uvicorn. |
| `ModuleNotFoundError: crewai` | Activate the venv with `.\.venv\Scripts\Activate.ps1`, then run `pip install -r requirements.txt`. |
| Port 8000 is already in use | Stop the stale backend process, or run uvicorn on another port and set `NEXT_PUBLIC_API_BASE_URL` in `frontend/.env.local`. |

