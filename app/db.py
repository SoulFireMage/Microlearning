"""SQLite storage: connection handling and schema.

Plain sqlite3 rather than an ORM: the schema is small, the queries are
explicit, and there is one fewer dependency to keep working on a Space.
"""
from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_units (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    domain TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- One row per (unit, depth, lens). lens: 'core' | 'pattern' | 'steps'.
-- origin records provenance: 'curated' (hand-written), 'extracted'
-- (verbatim from a source), 'synthesised' (LLM output, verify before trusting).
CREATE TABLE IF NOT EXISTS unit_depth_layers (
    id TEXT PRIMARY KEY,
    unit_id TEXT NOT NULL REFERENCES knowledge_units(id) ON DELETE CASCADE,
    depth_level INTEGER NOT NULL CHECK (depth_level IN (0, 1, 2)),
    lens TEXT NOT NULL DEFAULT 'core',
    content_markdown TEXT NOT NULL,
    read_time_seconds INTEGER NOT NULL,
    origin TEXT NOT NULL DEFAULT 'curated',
    model TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (unit_id, depth_level, lens)
);

CREATE TABLE IF NOT EXISTS unit_sources (
    id TEXT PRIMARY KEY,
    unit_id TEXT NOT NULL REFERENCES knowledge_units(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,            -- 'wikipedia' | 'arxiv' | 'url' | 'text' | 'reference'
    url TEXT,
    title TEXT NOT NULL,
    excerpt TEXT,                  -- source text kept for grounding synthesis
    retrieved_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('NEW','ACTIVE','PAUSED','DORMANT','RESOLVED')),
    parent_thread_id TEXT REFERENCES threads(id) ON DELETE SET NULL,
    branch_trigger_concept TEXT,
    current_unit_id TEXT REFERENCES knowledge_units(id) ON DELETE SET NULL,
    current_depth INTEGER NOT NULL DEFAULT 0,
    current_lens TEXT NOT NULL DEFAULT 'core',
    primer_pending INTEGER NOT NULL DEFAULT 0,
    last_accessed_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS thread_progress (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    unit_id TEXT NOT NULL REFERENCES knowledge_units(id) ON DELETE CASCADE,
    max_depth_reached INTEGER NOT NULL DEFAULT 0,
    user_status TEXT NOT NULL DEFAULT 'VIEWED' CHECK (user_status IN ('VIEWED','CONSOLIDATED','STUCK')),
    user_notes TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (thread_id, unit_id)
);

-- Drop-pins: an append-only log of open loops. The spec kept a single
-- user_notes field, which loses history on every overwrite; primers need
-- the trail, not just the last word.
CREATE TABLE IF NOT EXISTS pins (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    unit_id TEXT REFERENCES knowledge_units(id) ON DELETE SET NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Every state transition, for metrics and history.
CREATE TABLE IF NOT EXISTS thread_events (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    event TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS resumption_primers (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    anchor_summary TEXT NOT NULL,
    consolidated_points TEXT NOT NULL,   -- JSON array
    open_question TEXT NOT NULL,
    recommended_unit_id TEXT REFERENCES knowledge_units(id) ON DELETE SET NULL,
    progress_hash TEXT NOT NULL,
    origin TEXT NOT NULL,                -- 'synthesised' | 'fallback'
    generated_at TEXT NOT NULL,
    dismissed_at TEXT
);

CREATE TABLE IF NOT EXISTS concept_relationships (
    id TEXT PRIMARY KEY,
    source_unit_id TEXT NOT NULL REFERENCES knowledge_units(id) ON DELETE CASCADE,
    target_unit_id TEXT NOT NULL REFERENCES knowledge_units(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL CHECK (relationship_type IN ('REQUIRES','EXTENDS','ANALOGOUS_TO','CONTRASTS_WITH')),
    description TEXT,
    origin TEXT NOT NULL DEFAULT 'curated',
    UNIQUE (source_unit_id, target_unit_id, relationship_type)
);

-- Active retrieval. The briefing names the illusion of competence as the
-- core failure of summary apps, so each unit carries a recall probe.
CREATE TABLE IF NOT EXISTS recall_probes (
    id TEXT PRIMARY KEY,
    unit_id TEXT NOT NULL UNIQUE REFERENCES knowledge_units(id) ON DELETE CASCADE,
    prompt TEXT NOT NULL,
    reference_answer TEXT NOT NULL,
    origin TEXT NOT NULL DEFAULT 'curated'
);

CREATE TABLE IF NOT EXISTS recall_attempts (
    id TEXT PRIMARY KEY,
    probe_id TEXT NOT NULL REFERENCES recall_probes(id) ON DELETE CASCADE,
    thread_id TEXT REFERENCES threads(id) ON DELETE SET NULL,
    response TEXT,
    rating TEXT NOT NULL CHECK (rating IN ('again','shaky','solid')),
    interval_days REAL NOT NULL,
    next_due_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_layers_unit ON unit_depth_layers(unit_id);
CREATE INDEX IF NOT EXISTS ix_progress_thread ON thread_progress(thread_id);
CREATE INDEX IF NOT EXISTS ix_pins_thread ON pins(thread_id, created_at);
CREATE INDEX IF NOT EXISTS ix_events_thread ON thread_events(thread_id, at);
CREATE INDEX IF NOT EXISTS ix_rel_source ON concept_relationships(source_unit_id);
CREATE INDEX IF NOT EXISTS ix_rel_target ON concept_relationships(target_unit_id);
CREATE INDEX IF NOT EXISTS ix_attempts_probe ON recall_attempts(probe_id, created_at);
"""


def new_id() -> str:
    return uuid.uuid4().hex


class Clock:
    """Indirection over 'now' so tests can move time forward."""

    def __init__(self) -> None:
        self.offset_seconds = 0.0

    def now(self) -> datetime:
        from datetime import timedelta

        return datetime.now(timezone.utc) + timedelta(seconds=self.offset_seconds)

    def iso(self) -> str:
        return self.now().isoformat(timespec="seconds")


clock = Clock()


def parse_ts(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


def init_db(path: Path | None = None) -> str:
    """Create the schema; returns the journal mode actually in effect."""
    conn = connect(path)
    try:
        wanted = settings.journal_mode
        try:
            mode = conn.execute(f"PRAGMA journal_mode = {wanted}").fetchone()[0]
        except sqlite3.DatabaseError:
            mode = conn.execute("PRAGMA journal_mode = DELETE").fetchone()[0]
        conn.executescript(SCHEMA)
        conn.commit()
        return str(mode).upper()
    finally:
        conn.close()


@contextmanager
def session() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_conn() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: one connection per request, committed on success."""
    with session() as conn:
        yield conn


def rows(cur: sqlite3.Cursor) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def row(cur: sqlite3.Cursor) -> dict | None:
    r = cur.fetchone()
    return dict(r) if r else None
