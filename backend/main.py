from __future__ import annotations

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

import os
import traceback
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# Load environment variables before imports
load_dotenv(override=True)

# Fix LiteLLM unsupported params
import litellm

litellm.drop_params = True
litellm.modify_params = True

_original_completion = litellm.completion


def _patched_completion(*args, **kwargs):
    messages = kwargs.get("messages") or (
        args[1] if len(args) > 1 else []
    )

    if isinstance(messages, list):
        for msg in messages:
            if isinstance(msg, dict):
                msg.pop("cache_breakpoint", None)
                msg.pop("cache_control", None)

    kwargs["messages"] = messages
    return _original_completion(*args, **kwargs)


litellm.completion = _patched_completion

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import db
from crew import generate as crew_generate
from crew.schemas import (
    GeneratedFile,
    GenerateImageRequest,
    GenerateImageResponse,
    GenerateRequest,
    GenerateResponse,
    OptimizePromptRequest,
    OptimizePromptResponse,
    RenameProjectRequest,
    SaveFileRequest,
)
from services.image_cache import cache_dir as _image_cache_dir
from services.image_gen import generate_image_url
from services.theme_engine import detect_theme, optimize_prompt as theme_optimize_prompt

from services.theme_engine import enhance_prompt


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(
    title="AI Builder",
    lifespan=lifespan
)


def _allowed_origins() -> list[str]:
    configured = (
        os.getenv("ALLOWED_ORIGINS")
        or os.getenv("ALLOWED_ORIGIN")
    )

    if configured:
        return [
            origin.strip()
            for origin in configured.split(",")
            if origin.strip()
        ]

    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3002",
    ]


# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve cached Imagen / Gemini generated images. URLs returned by
# services.image_gen.generate_image_url look like
#   http://127.0.0.1:8000/assets/<sha256_prefix>.png
# The directory is created on first call to cache_dir() so this mount is safe
# at import time even on a fresh checkout.
app.mount("/assets", StaticFiles(directory=str(_image_cache_dir())), name="assets")


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
        "worker_model": os.getenv(
            "WORKER_MODEL",
            "groq/llama-3.3-70b-versatile",
        ),
        "providers": {
            "groq": bool(os.getenv("GROQ_API_KEY")),
            "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
            "openai": bool(os.getenv("OPENAI_API_KEY")),
        },
    }


@app.post("/generate-image", response_model=GenerateImageResponse)
def generate_image(req: GenerateImageRequest) -> GenerateImageResponse:
    """Synthesize an image URL from a text prompt via Pollinations.ai.

    No API key required. The URL is hot-loadable in <img src> — the frontend
    renders it directly. Same (prompt, seed) returns the same image, so
    callers can pin a seed for stability.
    """
    try:
        url = generate_image_url(
            req.prompt,
            width=req.width,
            height=req.height,
            seed=req.seed,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return GenerateImageResponse(
        image_url=url,
        prompt=req.prompt,
        width=req.width,
        height=req.height,
        seed=req.seed,
    )


@app.post("/optimize-prompt", response_model=OptimizePromptResponse)
def optimize_prompt(req: OptimizePromptRequest) -> OptimizePromptResponse:
    """Expand a short prompt into a richly specified build prompt.

    Theme is detected from the input (coffee shop, fintech, gaming, ...) and
    used to inject palette + design guidance before the LLM rewrite. If no
    LLM key is configured, a deterministic fallback is returned — the endpoint
    never hard-errors on missing providers.
    """
    try:
        optimized = theme_optimize_prompt(req.prompt)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Optimizer failed: {e}") from e
    return OptimizePromptResponse(
        optimized_prompt=optimized,
        category=detect_theme(req.prompt),
    )


@app.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest) -> GenerateResponse:
    if not _has_any_llm_key():
        raise HTTPException(
            status_code=500,
            detail=(
                "No LLM provider key configured. "
                "Set one of GROQ_API_KEY, "
                "ANTHROPIC_API_KEY, "
                "OPENAI_API_KEY in backend/.env"
            ),
        )

    try:
        enhanced_prompt = enhance_prompt(req.prompt)
        return crew_generate(
            enhanced_prompt,
            project_id=req.project_id,
        )

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Crew failed: {e}",
        ) from e


@app.get("/projects")
def list_projects() -> list[dict]:
    return db.list_projects()


@app.get("/projects/{project_id}")
def get_project(project_id: str) -> dict:
    proj = db.get_project(project_id)

    if not proj:
        raise HTTPException(
            status_code=404,
            detail=f"Project {project_id} not found",
        )

    proj["files"] = db.list_files(project_id)
    return proj


@app.get("/projects/{project_id}/files/{path:path}")
def get_project_file(project_id: str, path: str) -> dict:
    if not db.get_project(project_id):
        raise HTTPException(
            status_code=404,
            detail=f"Project {project_id} not found",
        )

    f = db.get_file(project_id, path)

    if not f:
        raise HTTPException(
            status_code=404,
            detail=f"File {path} not in project {project_id}",
        )

    return f


@app.get("/projects/{project_id}/messages")
def get_messages(project_id: str) -> list[dict]:
    if not db.get_project(project_id):
        raise HTTPException(
            status_code=404,
            detail=f"Project {project_id} not found",
        )

    return db.list_messages(project_id)


def _is_safe_path(path: str) -> bool:
    """Reject paths that attempt directory traversal."""

    normalized = os.path.normpath(path).replace("\\", "/")

    return (
        not normalized.startswith("/")
        and not normalized.startswith("\\")
        and ".." not in normalized.split("/")
    )


@app.post("/projects/{project_id}/save")
def save_file(
    project_id: str,
    req: SaveFileRequest,
) -> GeneratedFile:

    if not db.get_project(project_id):
        raise HTTPException(
            status_code=404,
            detail=f"Project {project_id} not found",
        )

    if not _is_safe_path(req.path):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file path: {req.path}",
        )

    db.save_file(
        project_id,
        req.path,
        req.content,
    )

    return GeneratedFile(
        path=req.path,
        content=req.content,
    )


# ---------------------------------------------------------------------------
# Project + file mutations — round out the CRUD surface
# ---------------------------------------------------------------------------

@app.patch("/projects/{project_id}")
def rename_project(project_id: str, req: RenameProjectRequest) -> dict:
    if not db.get_project(project_id):
        raise HTTPException(404, f"Project {project_id} not found")
    db.rename_project(project_id, req.name)
    return db.get_project(project_id) or {}


@app.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str) -> None:
    if not db.delete_project(project_id):
        raise HTTPException(404, f"Project {project_id} not found")


@app.delete("/projects/{project_id}/files/{path:path}", status_code=204)
def delete_project_file(project_id: str, path: str) -> None:
    if not db.get_project(project_id):
        raise HTTPException(404, f"Project {project_id} not found")
    if not _is_safe_path(path):
        raise HTTPException(400, f"Invalid file path: {path}")
    if not db.get_file(project_id, path):
        raise HTTPException(404, f"File {path} not in project {project_id}")
    db.delete_file(project_id, path)