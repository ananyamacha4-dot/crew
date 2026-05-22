"""FastAPI app for the AI builder.

Frontend only ever calls POST /generate. The other routes exist so the UI
can read back project state (file tree, individual file contents, chat
history) without re-running the crew.

Routes:
  GET  /                              health
  POST /generate                      run the agent crew (one call)
  GET  /projects                      list all projects
  GET  /projects/{id}                 project metadata + file list
  GET  /projects/{id}/files/{path}    one file's contents
  GET  /projects/{id}/messages        chat history
  POST /projects/{id}/save            user edited a file in the browser
"""

from __future__ import annotations

import os
import traceback

from dotenv import load_dotenv

load_dotenv(override=True)  # must happen before crewai imports read env

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import db
from crew import generate as crew_generate
from crew.schemas import (
    GeneratedFile,
    GenerateRequest,
    GenerateResponse,
    SaveFileRequest,
)

app = FastAPI(title="AI Builder")


def _allowed_origins() -> list[str]:
    configured = os.getenv("ALLOWED_ORIGINS") or os.getenv("ALLOWED_ORIGIN")
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]


# Frontend dev server (Next.js)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


def _has_any_llm_key() -> bool:
    return bool(
        os.getenv("GROQ_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )


@app.get("/")
def health() -> dict:
    return {
        "status": "ok",
        "worker_model": os.getenv("WORKER_MODEL", "groq/llama-3.3-70b-versatile"),
        "engineer_model": os.getenv("ENGINEER_MODEL") or os.getenv("WORKER_MODEL"),
        "critic_model": os.getenv("CRITIC_MODEL") or os.getenv("WORKER_MODEL"),
        "max_critic_iters": int(os.getenv("MAX_CRITIC_ITERS", "1")),
        "providers": {
            "groq": bool(os.getenv("GROQ_API_KEY")),
            "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
            "openai": bool(os.getenv("OPENAI_API_KEY")),
        },
    }


@app.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest) -> GenerateResponse:
    if not _has_any_llm_key():
        raise HTTPException(
            500,
            "No LLM provider key configured. Set one of GROQ_API_KEY, "
            "ANTHROPIC_API_KEY, OPENAI_API_KEY in backend/.env",
        )
    try:
        return crew_generate(req.prompt, project_id=req.project_id)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Crew failed: {e}") from e


@app.get("/projects")
def list_projects() -> list[dict]:
    return db.list_projects()


@app.get("/projects/{project_id}")
def get_project(project_id: str) -> dict:
    proj = db.get_project(project_id)
    if not proj:
        raise HTTPException(404, f"Project {project_id} not found")
    proj["files"] = db.list_files(project_id)
    return proj


@app.get("/projects/{project_id}/files/{path:path}")
def get_project_file(project_id: str, path: str) -> dict:
    if not db.get_project(project_id):
        raise HTTPException(404, f"Project {project_id} not found")
    f = db.get_file(project_id, path)
    if not f:
        raise HTTPException(404, f"File {path} not in project {project_id}")
    return f


@app.get("/projects/{project_id}/messages")
def get_messages(project_id: str) -> list[dict]:
    if not db.get_project(project_id):
        raise HTTPException(404, f"Project {project_id} not found")
    return db.list_messages(project_id)


@app.post("/projects/{project_id}/save")
def save_file(project_id: str, req: SaveFileRequest) -> GeneratedFile:
    if not db.get_project(project_id):
        raise HTTPException(404, f"Project {project_id} not found")
    db.save_file(project_id, req.path, req.content)
    return GeneratedFile(path=req.path, content=req.content)
