"""Domain operations shared by the API: units, progress, primers, ingest, recall."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import timedelta

from . import llm, sources
from .db import clock, new_id, parse_ts, row, rows
from .state import get_thread, touch

REL_TYPES = ("REQUIRES", "EXTENDS", "ANALOGOUS_TO", "CONTRASTS_WITH")
LENSES = ("core", "pattern", "steps")


# --------------------------------------------------------------------- units

def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or new_id()[:8]


def read_seconds(markdown: str) -> int:
    return max(10, round(len(markdown.split()) / 150 * 60))  # technical prose reads slowly


def unique_slug(conn: sqlite3.Connection, base: str) -> str:
    slug, n = base, 2
    while conn.execute("SELECT 1 FROM knowledge_units WHERE slug = ?", (slug,)).fetchone():
        slug, n = f"{base}-{n}", n + 1
    return slug


def create_unit(conn: sqlite3.Connection, title: str, domain: str, slug: str | None = None) -> dict:
    uid, now = new_id(), clock.iso()
    conn.execute(
        "INSERT INTO knowledge_units (id, title, slug, domain, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (uid, title.strip(), unique_slug(conn, slug or slugify(title)), domain.strip() or "Unsorted", now, now),
    )
    return get_unit_row(conn, uid)


def get_unit_row(conn: sqlite3.Connection, unit_id: str) -> dict | None:
    return row(conn.execute("SELECT * FROM knowledge_units WHERE id = ? OR slug = ?", (unit_id, unit_id)))


def set_layer(
    conn: sqlite3.Connection,
    unit_id: str,
    depth: int,
    content: str,
    lens: str = "core",
    origin: str = "curated",
    model: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO unit_depth_layers (id, unit_id, depth_level, lens, content_markdown,"
        " read_time_seconds, origin, model, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(unit_id, depth_level, lens) DO UPDATE SET"
        " content_markdown = excluded.content_markdown, read_time_seconds = excluded.read_time_seconds,"
        " origin = excluded.origin, model = excluded.model, created_at = excluded.created_at",
        (new_id(), unit_id, depth, lens, content.strip(), read_seconds(content), origin, model, clock.iso()),
    )
    conn.execute("UPDATE knowledge_units SET updated_at = ? WHERE id = ?", (clock.iso(), unit_id))


def add_source(
    conn: sqlite3.Connection, unit_id: str, kind: str, title: str, url: str | None, excerpt: str | None = None
) -> None:
    conn.execute(
        "INSERT INTO unit_sources (id, unit_id, kind, url, title, excerpt, retrieved_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (new_id(), unit_id, kind, url, title, excerpt, clock.iso()),
    )


def add_relation(
    conn: sqlite3.Connection,
    source_id: str,
    target_id: str,
    rel_type: str,
    description: str | None = None,
    origin: str = "curated",
) -> bool:
    if rel_type not in REL_TYPES or source_id == target_id:
        return False
    cur = conn.execute(
        "INSERT OR IGNORE INTO concept_relationships (id, source_unit_id, target_unit_id,"
        " relationship_type, description, origin) VALUES (?, ?, ?, ?, ?, ?)",
        (new_id(), source_id, target_id, rel_type, description, origin),
    )
    return cur.rowcount > 0


def set_probe(conn: sqlite3.Connection, unit_id: str, prompt: str, answer: str, origin: str = "curated") -> None:
    conn.execute(
        "INSERT INTO recall_probes (id, unit_id, prompt, reference_answer, origin) VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(unit_id) DO UPDATE SET prompt = excluded.prompt,"
        " reference_answer = excluded.reference_answer, origin = excluded.origin",
        (new_id(), unit_id, prompt.strip(), answer.strip(), origin),
    )


def neighbors(conn: sqlite3.Connection, unit_id: str, rel_type: str | None = None) -> dict:
    """Relations grouped for the panel. Inverse edges are folded in so the
    panel reads naturally from either end: if B REQUIRES A then, seen from A,
    B is downstream (it builds on A)."""
    out = {"prerequisites": [], "downstream": [], "analogous": [], "contrasts": []}
    q = (
        "SELECT r.*, s.title AS source_title, s.domain AS source_domain,"
        " t.title AS target_title, t.domain AS target_domain"
        " FROM concept_relationships r"
        " JOIN knowledge_units s ON s.id = r.source_unit_id"
        " JOIN knowledge_units t ON t.id = r.target_unit_id"
        " WHERE r.source_unit_id = ? OR r.target_unit_id = ?"
    )
    for r in rows(conn.execute(q, (unit_id, unit_id))):
        if rel_type and r["relationship_type"] != rel_type:
            continue
        outgoing = r["source_unit_id"] == unit_id
        other = (
            {"id": r["target_unit_id"], "title": r["target_title"], "domain": r["target_domain"]}
            if outgoing
            else {"id": r["source_unit_id"], "title": r["source_title"], "domain": r["source_domain"]}
        )
        other.update(description=r["description"], relationship_type=r["relationship_type"], origin=r["origin"])
        t = r["relationship_type"]
        if t == "ANALOGOUS_TO":
            out["analogous"].append(other)
        elif t == "CONTRASTS_WITH":
            out["contrasts"].append(other)
        else:
            # "S REQUIRES T" and "S EXTENDS T" both put T underneath S.
            out["prerequisites" if outgoing else "downstream"].append(other)
    return out


def get_unit(conn: sqlite3.Connection, unit_id: str) -> dict | None:
    unit = get_unit_row(conn, unit_id)
    if not unit:
        return None
    uid = unit["id"]
    layers = rows(
        conn.execute(
            "SELECT depth_level, lens, content_markdown, read_time_seconds, origin, model, created_at"
            " FROM unit_depth_layers WHERE unit_id = ? ORDER BY depth_level, lens",
            (uid,),
        )
    )
    unit["layers"] = layers
    unit["sources"] = rows(
        conn.execute(
            "SELECT kind, url, title, retrieved_at FROM unit_sources WHERE unit_id = ? ORDER BY retrieved_at",
            (uid,),
        )
    )
    unit["relations"] = neighbors(conn, uid)
    unit["probe"] = row(
        conn.execute("SELECT id, prompt, reference_answer, origin FROM recall_probes WHERE unit_id = ?", (uid,))
    )
    return unit


def list_units(conn: sqlite3.Connection, q: str | None = None) -> list[dict]:
    sql = (
        "SELECT u.id, u.title, u.slug, u.domain, u.updated_at,"
        " (SELECT content_markdown FROM unit_depth_layers l WHERE l.unit_id = u.id AND depth_level = 0"
        "  AND lens = 'core') AS hook,"
        " (SELECT COUNT(*) FROM unit_depth_layers l WHERE l.unit_id = u.id) AS layer_count"
        " FROM knowledge_units u"
    )
    args: tuple = ()
    if q:
        sql += " WHERE u.title LIKE ? OR u.domain LIKE ?"
        args = (f"%{q}%", f"%{q}%")
    sql += " ORDER BY u.domain, u.title"
    return rows(conn.execute(sql, args))


# ------------------------------------------------------------------ progress

def record_progress(
    conn: sqlite3.Connection,
    thread_id: str,
    unit_id: str,
    depth: int | None = None,
    status: str | None = None,
    note: str | None = None,
    lens: str | None = None,
) -> dict:
    now = clock.iso()
    existing = row(
        conn.execute("SELECT * FROM thread_progress WHERE thread_id = ? AND unit_id = ?", (thread_id, unit_id))
    )
    if existing is None:
        conn.execute(
            "INSERT INTO thread_progress (id, thread_id, unit_id, max_depth_reached, user_status,"
            " user_notes, completed_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                new_id(), thread_id, unit_id, depth or 0, status or "VIEWED", note,
                now if status == "CONSOLIDATED" else None, now, now,
            ),
        )
    else:
        conn.execute(
            "UPDATE thread_progress SET max_depth_reached = MAX(max_depth_reached, ?),"
            " user_status = COALESCE(?, user_status), user_notes = COALESCE(?, user_notes),"
            " completed_at = CASE WHEN ? = 'CONSOLIDATED' THEN ? ELSE completed_at END,"
            " updated_at = ? WHERE id = ?",
            (depth or 0, status, note, status, now, now, existing["id"]),
        )
    sets, args = ["current_unit_id = ?"], [unit_id]
    if depth is not None:
        sets.append("current_depth = ?")
        args.append(depth)
    if lens in LENSES:
        sets.append("current_lens = ?")
        args.append(lens)
    conn.execute(f"UPDATE threads SET {', '.join(sets)} WHERE id = ?", (*args, thread_id))
    touch(conn, thread_id)
    return row(conn.execute("SELECT * FROM thread_progress WHERE thread_id = ? AND unit_id = ?", (thread_id, unit_id)))


def add_pin(conn: sqlite3.Connection, thread_id: str, text: str, unit_id: str | None) -> dict:
    pid = new_id()
    conn.execute(
        "INSERT INTO pins (id, thread_id, unit_id, text, created_at) VALUES (?, ?, ?, ?, ?)",
        (pid, thread_id, unit_id, text.strip(), clock.iso()),
    )
    if unit_id:
        # Mirror into the spec's user_notes so the latest thought sits with the unit.
        record_progress(conn, thread_id, unit_id, note=text.strip())
    touch(conn, thread_id)
    return row(conn.execute("SELECT * FROM pins WHERE id = ?", (pid,)))


def thread_detail(conn: sqlite3.Connection, thread_id: str) -> dict | None:
    t = get_thread(conn, thread_id)
    if not t:
        return None
    t["progress"] = rows(
        conn.execute(
            "SELECT p.*, u.title AS unit_title FROM thread_progress p JOIN knowledge_units u ON u.id = p.unit_id"
            " WHERE p.thread_id = ? ORDER BY p.created_at",
            (thread_id,),
        )
    )
    t["pins"] = rows(
        conn.execute(
            "SELECT p.*, u.title AS unit_title FROM pins p LEFT JOIN knowledge_units u ON u.id = p.unit_id"
            " WHERE p.thread_id = ? ORDER BY p.created_at DESC",
            (thread_id,),
        )
    )
    t["parent"] = row(
        conn.execute("SELECT id, title, status FROM threads WHERE id = ?", (t["parent_thread_id"],))
    ) if t["parent_thread_id"] else None
    t["children"] = rows(
        conn.execute(
            "SELECT id, title, status, branch_trigger_concept FROM threads WHERE parent_thread_id = ?"
            " ORDER BY created_at",
            (thread_id,),
        )
    )
    t["current_unit_title"] = (
        conn.execute("SELECT title FROM knowledge_units WHERE id = ?", (t["current_unit_id"],)).fetchone() or [None]
    )[0]
    return t


# ------------------------------------------------------------------- primers

def progress_hash(conn: sqlite3.Connection, thread_id: str) -> str:
    t = get_thread(conn, thread_id)
    prog = conn.execute(
        "SELECT unit_id, max_depth_reached, user_status, COALESCE(user_notes,'') FROM thread_progress"
        " WHERE thread_id = ? ORDER BY unit_id",
        (thread_id,),
    ).fetchall()
    pins = conn.execute("SELECT id FROM pins WHERE thread_id = ? ORDER BY id", (thread_id,)).fetchall()
    blob = json.dumps(
        [t["current_unit_id"], t["title"], [tuple(p) for p in prog], [p[0] for p in pins]], sort_keys=True
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _hook(conn: sqlite3.Connection, unit_id: str) -> str:
    r = conn.execute(
        "SELECT content_markdown FROM unit_depth_layers WHERE unit_id = ? AND depth_level = 0"
        " ORDER BY lens = 'core' DESC LIMIT 1",
        (unit_id,),
    ).fetchone()
    return r[0] if r else ""


def _first_sentence(text: str, limit: int = 160) -> str:
    text = " ".join(text.split())
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    s = m.group(1) if m else text
    return s if len(s) <= limit else s[: limit - 1] + "…"


def recommended_unit(conn: sqlite3.Connection, thread_id: str) -> str | None:
    """Chosen deterministically, never by the LLM (which could invent ids)."""
    stuck = conn.execute(
        "SELECT unit_id FROM thread_progress WHERE thread_id = ? AND user_status = 'STUCK'"
        " ORDER BY updated_at DESC LIMIT 1",
        (thread_id,),
    ).fetchone()
    if stuck:
        return stuck[0]
    t = get_thread(conn, thread_id)
    if t["current_unit_id"]:
        return t["current_unit_id"]
    last = conn.execute(
        "SELECT unit_id FROM thread_progress WHERE thread_id = ? ORDER BY updated_at DESC LIMIT 1", (thread_id,)
    ).fetchone()
    return last[0] if last else None


def fallback_primer(conn: sqlite3.Connection, thread_id: str) -> dict:
    t = thread_detail(conn, thread_id)
    anchor = t["title"]
    if t["parent"] and t["branch_trigger_concept"]:
        anchor = f"{t['title']} — branched from “{t['parent']['title']}”: {t['branch_trigger_concept']}"
    elif t["branch_trigger_concept"]:
        anchor = f"{t['title']} — {t['branch_trigger_concept']}"
    consolidated = [
        f"{p['unit_title']}: {_first_sentence(_hook(conn, p['unit_id']))}"
        for p in t["progress"]
        if p["user_status"] == "CONSOLIDATED"
    ][-3:]
    if not consolidated:
        consolidated = [f"Explored: {p['unit_title']} (to L{p['max_depth_reached']})" for p in t["progress"]][-3:]
    if t["pins"]:
        open_q = t["pins"][0]["text"]
    else:
        stuck = [p for p in t["progress"] if p["user_status"] == "STUCK"]
        if stuck:
            open_q = f"You marked “{stuck[-1]['unit_title']}” as stuck."
        elif t["current_unit_title"]:
            open_q = f"You were last at “{t['current_unit_title']}”, level L{t['current_depth']}."
        else:
            open_q = "No open question was recorded. Start from the seed concept."
    return {"anchor_summary": anchor, "consolidated_points": consolidated, "open_question": open_q}


def llm_primer(conn: sqlite3.Connection, thread_id: str) -> dict:
    t = thread_detail(conn, thread_id)
    units = "\n".join(
        f"- {p['unit_title']} [{p['user_status']}, L{p['max_depth_reached']}]: {_first_sentence(_hook(conn, p['unit_id']), 240)}"
        for p in t["progress"]
    ) or "(none recorded)"
    pins = "\n".join(f"- {p['text']}" for p in reversed(t["pins"][:8])) or "(none)"
    parent = "none"
    if t["parent"]:
        parent = f"{t['parent']['title']} — reason: {t['branch_trigger_concept'] or 'not given'}"
    data = llm.complete_json(
        llm.PRIMER_SYSTEM,
        llm.PRIMER_USER.format(thread_title=t["title"], parent_context=parent, units_explored=units, pins=pins),
        max_tokens=800,
    )
    points = [str(p) for p in (data.get("consolidated_points") or [])][:3]
    return {
        "anchor_summary": str(data["anchor_summary"]).strip(),
        "consolidated_points": points,
        "open_question": str(data["open_question"]).strip(),
    }


def get_primer(conn: sqlite3.Connection, thread_id: str, force: bool = False) -> dict:
    """Return the cached primer if progress has not changed, else build one."""
    h = progress_hash(conn, thread_id)
    if not force:
        cached = row(
            conn.execute(
                "SELECT * FROM resumption_primers WHERE thread_id = ? AND progress_hash = ?"
                " ORDER BY generated_at DESC LIMIT 1",
                (thread_id, h),
            )
        )
        if cached:
            return _primer_out(conn, cached)
    origin = "synthesised"
    try:
        payload = llm_primer(conn, thread_id)
    except Exception:  # noqa: BLE001 - any provider/parse failure falls back
        payload, origin = fallback_primer(conn, thread_id), "fallback"
    pid = new_id()
    conn.execute(
        "INSERT INTO resumption_primers (id, thread_id, anchor_summary, consolidated_points, open_question,"
        " recommended_unit_id, progress_hash, origin, generated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            pid, thread_id, payload["anchor_summary"], json.dumps(payload["consolidated_points"]),
            payload["open_question"], recommended_unit(conn, thread_id), h, origin, clock.iso(),
        ),
    )
    return _primer_out(conn, row(conn.execute("SELECT * FROM resumption_primers WHERE id = ?", (pid,))))


def _primer_out(conn: sqlite3.Connection, p: dict) -> dict:
    p = dict(p)
    p["consolidated_points"] = json.loads(p["consolidated_points"])
    p["recommended_unit_title"] = None
    if p["recommended_unit_id"]:
        r = conn.execute("SELECT title FROM knowledge_units WHERE id = ?", (p["recommended_unit_id"],)).fetchone()
        p["recommended_unit_title"] = r[0] if r else None
    return p


# ---------------------------------------------------------------- expansion

def expansion_prompts(conn: sqlite3.Connection, unit_id: str, level: int, lens: str) -> tuple[str, str]:
    unit = get_unit(conn, unit_id)
    system = llm.EXPANSION_SYSTEM.format(level=llm.LEVEL_SPECS[level], lens=llm.LENS_SPECS[lens])
    have = "\n\n".join(
        f"[L{l['depth_level']} {l['lens']}]\n{l['content_markdown']}"
        for l in unit["layers"]
        if l["depth_level"] < 2 or l["lens"] == "core"
    )[:6000]
    src_rows = rows(
        conn.execute("SELECT title, url, excerpt FROM unit_sources WHERE unit_id = ?", (unit["id"],))
    )
    src = "\n\n".join(
        f"SOURCE: {s['title']} {s['url'] or ''}\n{(s['excerpt'] or '')[:5000]}" for s in src_rows
    ) or "(no stored source text; rely on standard textbook knowledge and say where uncertain)"
    rel = unit["relations"]
    related = ", ".join(x["title"] for k in rel for x in rel[k]) or "none"
    user = (
        f"Concept: {unit['title']} (domain: {unit['domain']})\n"
        f"Related concepts in the learner's graph: {related}\n\n"
        f"Existing material for this concept:\n{have or '(none yet)'}\n\n"
        f"Source material:\n{src}\n\n"
        f"Write the L{level} [{lens}] layer now. Output only the layer content."
    )
    return system, user


# ------------------------------------------------------------------- ingest

def ingest(conn: sqlite3.Connection, kind: str, ref: str, domain: str = "", title: str | None = None) -> dict:
    doc = sources.fetch(kind, ref, title)
    existing = list_units(conn)
    listing = "\n".join(f"{u['id']} | {u['title']} | {u['domain']}" for u in existing[:200]) or "(none)"
    model_used = None
    try:
        data = llm.complete_json(
            llm.INGEST_SYSTEM,
            llm.INGEST_USER.format(
                kind=doc.kind, source_title=doc.title, source_url=doc.url or "", source_text=doc.text,
                domain_hint=domain, existing=listing,
            ),
            max_tokens=2000,
        )
        model_used = llm.settings.default_model
        unit_title = (data.get("title") or doc.title).strip()
        unit_domain = (domain or data.get("domain") or "Unsorted").strip()
    except Exception:  # noqa: BLE001
        data = None
        unit_title, unit_domain = (title or doc.title), (domain or "Unsorted")

    unit = create_unit(conn, unit_title, unit_domain)
    add_source(conn, unit["id"], doc.kind, doc.title, doc.url, doc.text)
    valid_ids = {u["id"] for u in existing}
    if data:
        set_layer(conn, unit["id"], 0, data.get("l0", ""), origin="synthesised", model=model_used)
        if data.get("l1"):
            set_layer(conn, unit["id"], 1, data["l1"], origin="synthesised", model=model_used)
        probe = data.get("probe") or {}
        if probe.get("prompt") and probe.get("answer"):
            set_probe(conn, unit["id"], probe["prompt"], probe["answer"], origin="synthesised")
        for r in data.get("relations") or []:
            if r.get("target_id") in valid_ids:
                add_relation(
                    conn, unit["id"], r["target_id"], str(r.get("type", "")).upper(),
                    r.get("description"), origin="synthesised",
                )
    else:
        set_layer(conn, unit["id"], 0, sources.first_paragraph(doc.text), origin="extracted")
    return get_unit(conn, unit["id"])


def generate_probe(conn: sqlite3.Connection, unit_id: str) -> dict:
    unit = get_unit(conn, unit_id)
    material = "\n\n".join(l["content_markdown"] for l in unit["layers"] if l["depth_level"] <= 1)[:5000]
    data = llm.complete_json(llm.PROBE_SYSTEM, f"Concept: {unit['title']}\n\nMaterial:\n{material}", max_tokens=600)
    set_probe(conn, unit["id"], data["prompt"], data["answer"], origin="synthesised")
    return get_unit(conn, unit["id"])["probe"]


# -------------------------------------------------------------------- recall

INTERVALS = {"again": 1.0, "shaky": 3.0}


def record_attempt(
    conn: sqlite3.Connection, probe_id: str, rating: str, response: str | None, thread_id: str | None
) -> dict:
    prev = row(
        conn.execute(
            "SELECT interval_days FROM recall_attempts WHERE probe_id = ? ORDER BY created_at DESC LIMIT 1",
            (probe_id,),
        )
    )
    if rating == "solid":
        interval = max(7.0, (prev["interval_days"] if prev else 3.0) * 2.5)
    else:
        interval = INTERVALS[rating]
    due = clock.now() + timedelta(days=interval)
    aid = new_id()
    conn.execute(
        "INSERT INTO recall_attempts (id, probe_id, thread_id, response, rating, interval_days, next_due_at,"
        " created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (aid, probe_id, thread_id, response, rating, interval, due.isoformat(timespec="seconds"), clock.iso()),
    )
    if thread_id:
        touch(conn, thread_id)
    return row(conn.execute("SELECT * FROM recall_attempts WHERE id = ?", (aid,)))


def recall_queue(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    """Probes worth resurfacing: units you have engaged with whose last
    attempt is due, or that you consolidated but never tested. No overdue
    counts, no penalties: just what is ready."""
    q = (
        "SELECT p.id AS probe_id, p.prompt, p.reference_answer, p.origin, u.id AS unit_id, u.title, u.domain,"
        " (SELECT next_due_at FROM recall_attempts a WHERE a.probe_id = p.id ORDER BY created_at DESC LIMIT 1)"
        "   AS next_due_at"
        " FROM recall_probes p JOIN knowledge_units u ON u.id = p.unit_id"
        " WHERE EXISTS (SELECT 1 FROM thread_progress tp WHERE tp.unit_id = u.id"
        "   AND (tp.user_status = 'CONSOLIDATED' OR tp.max_depth_reached >= 1))"
    )
    now = clock.now()
    ready = [
        r for r in rows(conn.execute(q))
        if r["next_due_at"] is None or parse_ts(r["next_due_at"]) <= now
    ]
    ready.sort(key=lambda r: r["next_due_at"] or "")
    return ready[:limit]
