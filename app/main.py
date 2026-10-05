"""FastAPI application: REST API + static single-page UI."""
from __future__ import annotations

import hashlib
import logging
import hmac
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import llm, seed, services as S, sources, state
from .config import settings
from .db import get_conn, init_db, rows, session

log = logging.getLogger("uvicorn.error")
STATIC = Path(__file__).resolve().parent.parent / "static"

RUNTIME = {"journal_mode": None}

# scope="function": commit BEFORE the response is sent. With the default
# ("request") the commit runs after sending, so a client's immediate
# follow-up request could read stale state.
DB = Depends(get_conn, scope="function")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    RUNTIME["journal_mode"] = init_db()
    if not str(settings.db_path).startswith("/data"):
        log.warning("Database at %s is NOT on persistent storage (/data). "
                    "On a Space, attach a Storage Bucket at /data or data is lost on restart.", settings.db_path)
    if settings.seed_on_start:
        with session() as conn:
            seed.seed(conn)
    yield


app = FastAPI(title="Thread-Resilient Learning Engine", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


# ---------------------------------------------------------------------- auth

COOKIE = "tr_session"


def _token() -> str:
    key = (settings.app_secret + (settings.app_password or "")).encode()
    return hmac.new(key, b"thread-resilient", hashlib.sha256).hexdigest()


@app.middleware("http")
async def _auth(request: Request, call_next):
    if settings.app_password:
        path = request.url.path
        open_paths = path in ("/login", "/healthz") or path.startswith("/static/")
        if not open_paths and not hmac.compare_digest(request.cookies.get(COOKIE, ""), _token()):
            if path.startswith("/api/"):
                return JSONResponse({"detail": "Not authenticated"}, status_code=401)
            return RedirectResponse("/login")
    return await call_next(request)


LOGIN_PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sign in</title><link rel="stylesheet" href="/static/style.css"></head>
<body class="login"><form method="post" action="/login" class="login-card">
<div class="brand">threads<span>/</span></div>
<input type="password" name="password" placeholder="Password" autofocus>
<button type="submit">Enter</button>{error}</form></body></html>"""


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return LOGIN_PAGE.format(error="")


@app.post("/login")
async def login(request: Request):
    form = await request.body()
    from urllib.parse import parse_qs

    pw = parse_qs(form.decode()).get("password", [""])[0]
    if settings.app_password and hmac.compare_digest(pw, settings.app_password):
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie(COOKIE, _token(), httponly=True, samesite="none", max_age=60 * 60 * 24 * 90, secure=True)
        # SameSite=None: the Space page embeds the app in a cross-site iframe.
        return resp
    return HTMLResponse(LOGIN_PAGE.format(error='<p class="err">Wrong password.</p>'), status_code=401)


# ----------------------------------------------------------------- schemas

class ThreadIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    seed_unit_id: str | None = None
    concept: str | None = None  # free-text concept: creates a stub unit


class BranchIn(BaseModel):
    unit_id: str | None = None
    concept: str | None = None
    reason: str | None = None
    title: str | None = None
    relationship_type: Literal["REQUIRES", "EXTENDS", "ANALOGOUS_TO", "CONTRASTS_WITH"] | None = None


class ProgressIn(BaseModel):
    unit_id: str
    depth: int | None = Field(default=None, ge=0, le=2)
    lens: Literal["core", "pattern", "steps"] | None = None
    status: Literal["VIEWED", "CONSOLIDATED", "STUCK"] | None = None
    note: str | None = None


class PinIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    unit_id: str | None = None


class ExpandIn(BaseModel):
    level: int = Field(ge=0, le=2)
    lens: Literal["core", "pattern", "steps"] = "core"


class UnitIn(BaseModel):
    title: str = Field(min_length=1)
    domain: str = "Unsorted"
    l0: str | None = None
    l1: str | None = None
    l2: str | None = None


class LayerIn(BaseModel):
    level: int = Field(ge=0, le=2)
    lens: Literal["core", "pattern", "steps"] = "core"
    content: str = Field(min_length=1)


class IngestIn(BaseModel):
    kind: Literal["wikipedia", "arxiv", "url", "text"]
    ref: str = Field(min_length=1)
    domain: str = ""
    title: str | None = None
    thread_id: str | None = None


class RelationIn(BaseModel):
    target_unit_id: str
    relationship_type: Literal["REQUIRES", "EXTENDS", "ANALOGOUS_TO", "CONTRASTS_WITH"]
    description: str | None = None


class AttemptIn(BaseModel):
    rating: Literal["again", "shaky", "solid"]
    response: str | None = None
    thread_id: str | None = None


# ------------------------------------------------------------------ helpers

def _thread_or_404(conn: sqlite3.Connection, thread_id: str) -> dict:
    t = state.get_thread(conn, thread_id)
    if not t:
        raise HTTPException(404, "Thread not found")
    return t


def _unit_or_404(conn: sqlite3.Connection, unit_id: str) -> dict:
    u = S.get_unit_row(conn, unit_id)
    if not u:
        raise HTTPException(404, "Unit not found")
    return u


def _fire(conn: sqlite3.Connection, thread_id: str, event: str) -> dict:
    try:
        state.fire(conn, thread_id, event)
    except state.TransitionError as e:
        raise HTTPException(409, str(e)) from e
    return S.thread_detail(conn, thread_id)


def _resolve_unit(conn: sqlite3.Connection, unit_id: str | None, concept: str | None, domain: str = "Unsorted") -> str | None:
    if unit_id:
        return _unit_or_404(conn, unit_id)["id"]
    if concept and concept.strip():
        existing = conn.execute(
            "SELECT id FROM knowledge_units WHERE lower(title) = lower(?)", (concept.strip(),)
        ).fetchone()
        if existing:
            return existing[0]
        return S.create_unit(conn, concept.strip(), domain)["id"]
    return None


# ------------------------------------------------------------------ meta

@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/meta")
def meta():
    return {
        "llm_enabled": settings.llm_enabled,
        "model": settings.model,
        "llm_backend": settings.llm_backend,
        "db_path": str(settings.db_path),
        "journal_mode": RUNTIME["journal_mode"],
        "persistent": str(settings.db_path).startswith("/data"),
        "dormancy_days": settings.dormancy_days,
        "max_active": settings.max_active,
    }


@app.get("/api/metrics")
def metrics(conn: sqlite3.Connection = DB):
    state.sweep_dormancy(conn)
    m = state.resumption_metrics(conn)
    m["units"] = conn.execute("SELECT COUNT(*) FROM knowledge_units").fetchone()[0]
    m["recall_ready"] = len(S.recall_queue(conn, limit=500))
    return m


# ---------------------------------------------------------------- threads

@app.get("/api/threads")
def list_threads(status: str | None = None, conn: sqlite3.Connection = DB):
    state.sweep_dormancy(conn)
    sql = (
        "SELECT t.*, u.title AS current_unit_title,"
        " (SELECT COUNT(*) FROM thread_progress p WHERE p.thread_id = t.id) AS unit_count,"
        " (SELECT text FROM pins WHERE pins.thread_id = t.id ORDER BY created_at DESC LIMIT 1) AS last_pin,"
        " pt.title AS parent_title"
        " FROM threads t LEFT JOIN knowledge_units u ON u.id = t.current_unit_id"
        " LEFT JOIN threads pt ON pt.id = t.parent_thread_id"
    )
    args: list = []
    if status:
        wanted = [s.strip().upper() for s in status.split(",") if s.strip()]
        sql += f" WHERE t.status IN ({','.join('?' * len(wanted))})"
        args = wanted
    sql += " ORDER BY t.last_accessed_at DESC"
    return rows(conn.execute(sql, args))


@app.post("/api/threads", status_code=201)
def create_thread(body: ThreadIn, conn: sqlite3.Connection = DB):
    unit_id = _resolve_unit(conn, body.seed_unit_id, body.concept)
    t = state.create_thread(conn, body.title.strip(), unit_id)
    return S.thread_detail(conn, t["id"])


@app.get("/api/threads/{thread_id}")
def get_thread(thread_id: str, conn: sqlite3.Connection = DB):
    _thread_or_404(conn, thread_id)
    return S.thread_detail(conn, thread_id)


@app.post("/api/threads/{thread_id}/open")
def open_thread(thread_id: str, conn: sqlite3.Connection = DB):
    """The single entry point for 'user clicked a thread'. Dormant threads
    return needs_primer=true and must go through the primer first."""
    _thread_or_404(conn, thread_id)
    state.sweep_dormancy(conn)
    _, needs_primer = state.open_thread(conn, thread_id)
    out = {"thread": S.thread_detail(conn, thread_id), "needs_primer": needs_primer}
    if needs_primer:
        out["primer"] = S.get_primer(conn, thread_id)
    return out


@app.get("/api/threads/{thread_id}/primer")
def primer(thread_id: str, refresh: bool = False, conn: sqlite3.Connection = DB):
    _thread_or_404(conn, thread_id)
    return S.get_primer(conn, thread_id, force=refresh)


@app.post("/api/threads/{thread_id}/resume")
def resume(thread_id: str, conn: sqlite3.Connection = DB):
    """Acknowledge the primer and step back in at the recommended unit."""
    t = _thread_or_404(conn, thread_id)
    if t["status"] == state.DORMANT:
        state.fire(conn, thread_id, "RESUME_CLICKED")
    t = state.get_thread(conn, thread_id)
    event = "PRIMER_ACKNOWLEDGED" if t["primer_pending"] else "RESUME"
    detail = _fire(conn, thread_id, event)
    p = conn.execute(
        "SELECT id, recommended_unit_id FROM resumption_primers WHERE thread_id = ? AND dismissed_at IS NULL"
        " ORDER BY generated_at DESC LIMIT 1",
        (thread_id,),
    ).fetchone()
    if p:
        conn.execute("UPDATE resumption_primers SET dismissed_at = ? WHERE id = ?", (state.clock.iso(), p[0]))
        if p[1]:
            conn.execute("UPDATE threads SET current_unit_id = ? WHERE id = ?", (p[1], thread_id))
            detail = S.thread_detail(conn, thread_id)
    return detail


@app.post("/api/threads/{thread_id}/pause")
def pause(thread_id: str, conn: sqlite3.Connection = DB):
    _thread_or_404(conn, thread_id)
    return _fire(conn, thread_id, "PAUSE")


@app.post("/api/threads/{thread_id}/resolve")
def resolve(thread_id: str, conn: sqlite3.Connection = DB):
    _thread_or_404(conn, thread_id)
    return _fire(conn, thread_id, "MARK_RESOLVED")


@app.post("/api/threads/{thread_id}/reopen")
def reopen(thread_id: str, conn: sqlite3.Connection = DB):
    _thread_or_404(conn, thread_id)
    return _fire(conn, thread_id, "REOPEN")


@app.post("/api/threads/{thread_id}/branch", status_code=201)
def branch(thread_id: str, body: BranchIn, conn: sqlite3.Connection = DB):
    parent = _thread_or_404(conn, thread_id)
    if parent["status"] not in (state.NEW, state.ACTIVE, state.PAUSED):
        raise HTTPException(409, f"Cannot branch from a {parent['status']} thread")
    target = _resolve_unit(conn, body.unit_id, body.concept)
    if not target:
        raise HTTPException(422, "Give unit_id or concept to branch to")
    if body.relationship_type and parent["current_unit_id"]:
        # Record the associative link that caused the pivot.
        # Phrased "current unit <TYPE> new concept", e.g. Attention REQUIRES Softmax.
        S.add_relation(conn, parent["current_unit_id"], target, body.relationship_type, body.reason, origin="user")
    title = (body.title or "").strip() or S.get_unit_row(conn, target)["title"]
    state.fire(conn, thread_id, "BRANCH_LATERAL")
    child = state.create_thread(conn, title, target, parent_thread_id=thread_id, reason=body.reason)
    state.fire(conn, child["id"], "START_SESSION")
    return S.thread_detail(conn, child["id"])


@app.post("/api/threads/{thread_id}/progress")
def progress(thread_id: str, body: ProgressIn, conn: sqlite3.Connection = DB):
    _thread_or_404(conn, thread_id)
    unit = _unit_or_404(conn, body.unit_id)
    return S.record_progress(conn, thread_id, unit["id"], body.depth, body.status, body.note, body.lens)


@app.post("/api/threads/{thread_id}/pins", status_code=201)
def pin(thread_id: str, body: PinIn, conn: sqlite3.Connection = DB):
    _thread_or_404(conn, thread_id)
    unit_id = _unit_or_404(conn, body.unit_id)["id"] if body.unit_id else None
    return S.add_pin(conn, thread_id, body.text, unit_id)


@app.get("/api/threads/{thread_id}/events")
def thread_events(thread_id: str, conn: sqlite3.Connection = DB):
    _thread_or_404(conn, thread_id)
    return rows(conn.execute("SELECT * FROM thread_events WHERE thread_id = ? ORDER BY at", (thread_id,)))


# ------------------------------------------------------------------ units

@app.get("/api/units")
def list_units(q: str | None = None, conn: sqlite3.Connection = DB):
    return S.list_units(conn, q)


@app.post("/api/units", status_code=201)
def create_unit(body: UnitIn, conn: sqlite3.Connection = DB):
    u = S.create_unit(conn, body.title, body.domain)
    for level, text in ((0, body.l0), (1, body.l1), (2, body.l2)):
        if text and text.strip():
            S.set_layer(conn, u["id"], level, text, origin="curated")
    return S.get_unit(conn, u["id"])


@app.get("/api/units/{unit_id}")
def get_unit(unit_id: str, conn: sqlite3.Connection = DB):
    u = S.get_unit(conn, unit_id)
    if not u:
        raise HTTPException(404, "Unit not found")
    return u


@app.put("/api/units/{unit_id}/layers")
def put_layer(unit_id: str, body: LayerIn, conn: sqlite3.Connection = DB):
    """Hand-edit a layer (e.g. correct a synthesised one). Marks it curated."""
    u = _unit_or_404(conn, unit_id)
    S.set_layer(conn, u["id"], body.level, body.content, lens=body.lens, origin="curated")
    return S.get_unit(conn, u["id"])


@app.post("/api/units/{unit_id}/relations", status_code=201)
def add_relation(unit_id: str, body: RelationIn, conn: sqlite3.Connection = DB):
    u = _unit_or_404(conn, unit_id)
    t = _unit_or_404(conn, body.target_unit_id)
    S.add_relation(conn, u["id"], t["id"], body.relationship_type, body.description, origin="user")
    return S.neighbors(conn, u["id"])


@app.post("/api/units/{unit_id}/expand")
def expand(unit_id: str, body: ExpandIn, conn: sqlite3.Connection = DB):
    """Stream a missing layer as plain text; saved when the stream completes."""
    u = _unit_or_404(conn, unit_id)
    if not settings.llm_enabled:
        raise HTTPException(503, "LLM disabled: set HF_TOKEN or OPENROUTER_API_KEY.")
    system, user = S.expansion_prompts(conn, u["id"], body.level, body.lens)

    def gen():
        parts: list[str] = []
        try:
            for piece in llm.stream(system, user, max_tokens=5000 if body.level == 2 else 1500):
                parts.append(piece)
                yield piece
        except Exception as e:  # noqa: BLE001
            yield f"\n\n> Generation failed: {type(e).__name__}: {e}"
            return
        text = "".join(parts).strip()
        if text:
            with session() as c:
                S.set_layer(c, u["id"], body.level, text, lens=body.lens, origin="synthesised",
                            model=settings.model)

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8",
                             headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


@app.post("/api/units/{unit_id}/probe")
def make_probe(unit_id: str, conn: sqlite3.Connection = DB):
    u = _unit_or_404(conn, unit_id)
    try:
        return S.generate_probe(conn, u["id"])
    except llm.LLMUnavailable as e:
        raise HTTPException(503, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Probe generation failed: {e}") from e


@app.get("/api/graph/neighbors/{unit_id}")
def graph_neighbors(unit_id: str, type: str | None = Query(default=None), conn: sqlite3.Connection = DB):
    u = _unit_or_404(conn, unit_id)
    return S.neighbors(conn, u["id"], type.upper() if type else None)


@app.get("/api/graph")
def graph(conn: sqlite3.Connection = DB):
    return {
        "nodes": rows(conn.execute("SELECT id, title, domain FROM knowledge_units")),
        "edges": rows(conn.execute(
            "SELECT source_unit_id AS source, target_unit_id AS target, relationship_type AS type, description"
            " FROM concept_relationships")),
    }


# ----------------------------------------------------------------- ingest

@app.post("/api/ingest", status_code=201)
def ingest(body: IngestIn, conn: sqlite3.Connection = DB):
    try:
        unit = S.ingest(conn, body.kind, body.ref, body.domain, body.title)
    except sources.SourceError as e:
        raise HTTPException(422, str(e)) from e
    if body.thread_id and state.get_thread(conn, body.thread_id):
        S.record_progress(conn, body.thread_id, unit["id"], depth=0)
    return unit


# ----------------------------------------------------------------- recall

@app.get("/api/recall/queue")
def recall_queue(conn: sqlite3.Connection = DB):
    return S.recall_queue(conn)


@app.post("/api/recall/{probe_id}/attempt", status_code=201)
def recall_attempt(probe_id: str, body: AttemptIn, conn: sqlite3.Connection = DB):
    if not conn.execute("SELECT 1 FROM recall_probes WHERE id = ?", (probe_id,)).fetchone():
        raise HTTPException(404, "Probe not found")
    return S.record_attempt(conn, probe_id, body.rating, body.response, body.thread_id)


# ----------------------------------------------------------------- export

EXPORT_TABLES = (
    "knowledge_units", "unit_depth_layers", "unit_sources", "concept_relationships", "recall_probes",
    "threads", "thread_progress", "pins", "thread_events", "resumption_primers", "recall_attempts",
)


@app.get("/api/export")
def export(conn: sqlite3.Connection = DB):
    data = {t: rows(conn.execute(f"SELECT * FROM {t}")) for t in EXPORT_TABLES}
    return JSONResponse(data, headers={"Content-Disposition": 'attachment; filename="threads-export.json"'})


# ------------------------------------------------------------------- SPA

@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")
