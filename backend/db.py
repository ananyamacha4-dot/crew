"""SQLite persistence for the AI builder.

Schema:
  projects(id, name, entry, created_at, updated_at)
  files(project_id, path, content, updated_at)   -- PK: (project_id, path)
  messages(id, project_id, role, content, agent, created_at)

One DB file at backend/storage/builder.db. Stdlib only — no ORM.
"""

from __future__ import annotations

import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

DB_PATH = Path(__file__).parent / "storage" / "builder.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    entry       TEXT NOT NULL DEFAULT 'index.html',
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
    project_id  TEXT NOT NULL,
    path        TEXT NOT NULL,
    content     TEXT NOT NULL,
    updated_at  REAL NOT NULL,
    PRIMARY KEY (project_id, path),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT NOT NULL,
    role        TEXT NOT NULL,           -- 'user' | 'assistant' | 'system'
    content     TEXT NOT NULL,
    agent       TEXT,                    -- 'Planner' | 'Coder' | ...
    created_at  REAL NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_files_project   ON files(project_id);
CREATE INDEX IF NOT EXISTS idx_messages_project ON messages(project_id, id);
"""


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


# --- projects ----------------------------------------------------------

def create_project(name: str, entry: str = "index.html") -> str:
    pid = uuid.uuid4().hex[:12]
    now = time.time()
    with connect() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, entry, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (pid, name, entry, now, now),
        )
    return pid


def get_project(project_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, name, entry, created_at, updated_at FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    return dict(row) if row else None


def list_projects() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, name, entry, created_at, updated_at FROM projects ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def touch_project(project_id: str, entry: str | None = None) -> None:
    with connect() as conn:
        if entry is not None:
            conn.execute(
                "UPDATE projects SET updated_at = ?, entry = ? WHERE id = ?",
                (time.time(), entry, project_id),
            )
        else:
            conn.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (time.time(), project_id),
            )


def rename_project(project_id: str, name: str) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE projects SET name = ?, updated_at = ? WHERE id = ?",
            (name, time.time(), project_id),
        )
        return cur.rowcount > 0


def delete_project(project_id: str) -> bool:
    """Cascades to files + messages via FK ON DELETE CASCADE."""
    with connect() as conn:
        cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        return cur.rowcount > 0


# --- files -------------------------------------------------------------

def list_files(project_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT path, content FROM files WHERE project_id = ? ORDER BY path",
            (project_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_file(project_id: str, path: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT path, content FROM files WHERE project_id = ? AND path = ?",
            (project_id, path),
        ).fetchone()
    return dict(row) if row else None


def save_file(project_id: str, path: str, content: str) -> None:
    now = time.time()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO files (project_id, path, content, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(project_id, path) DO UPDATE SET
                content = excluded.content,
                updated_at = excluded.updated_at
            """,
            (project_id, path, content, now),
        )
        conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))


def save_files(project_id: str, files: Iterable[dict]) -> int:
    """Bulk upsert. Each item must have 'path' and 'content'."""
    now = time.time()
    rows = [(project_id, f["path"], f["content"], now) for f in files]
    if not rows:
        return 0
    with connect() as conn:
        conn.executemany(
            """
            INSERT INTO files (project_id, path, content, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(project_id, path) DO UPDATE SET
                content = excluded.content,
                updated_at = excluded.updated_at
            """,
            rows,
        )
        conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
    return len(rows)


def delete_file(project_id: str, path: str) -> None:
    with connect() as conn:
        conn.execute(
            "DELETE FROM files WHERE project_id = ? AND path = ?",
            (project_id, path),
        )


# --- messages ----------------------------------------------------------

def add_message(project_id: str, role: str, content: str, agent: str | None = None) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO messages (project_id, role, content, agent, created_at) VALUES (?, ?, ?, ?, ?)",
            (project_id, role, content, agent, time.time()),
        )
        return cur.lastrowid or 0


def list_messages(project_id: str, limit: int = 50) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, role, content, agent, created_at FROM messages "
            "WHERE project_id = ? ORDER BY id ASC LIMIT ?",
            (project_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]
