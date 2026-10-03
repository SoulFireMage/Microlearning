"""Thread lifecycle state machine.

States: NEW, ACTIVE, PAUSED, DORMANT, RESOLVED.

Additions beyond the original spec, each closing a gap in it:
  * RESUME    PAUSED -> ACTIVE   Returning to a parent after a short branch
                                  should not need a primer; the spec only
                                  allowed PAUSED -> ACTIVE via a primer.
  * PAUSE     ACTIVE -> PAUSED   Manual pause (the briefing mentions it; the
                                  matrix omitted it).
  * AUTO_PAUSE ACTIVE -> PAUSED  Enforces the 1-2 concurrent ACTIVE limit.
  * REOPEN    RESOLVED -> PAUSED A resolved curiosity can come back.
  * BRANCH from NEW/PAUSED too:  you can pivot before reading a word.

Dormancy is computed lazily (on read) rather than by a background job,
because a Space sleeps when idle and a cron would not run anyway.
"""
from __future__ import annotations

import sqlite3
from datetime import timedelta

from .config import settings
from .db import clock, new_id, parse_ts, row, rows

NEW, ACTIVE, PAUSED, DORMANT, RESOLVED = "NEW", "ACTIVE", "PAUSED", "DORMANT", "RESOLVED"
STATES = (NEW, ACTIVE, PAUSED, DORMANT, RESOLVED)

TRANSITIONS: dict[tuple[str, str], str] = {
    (NEW, "START_SESSION"): ACTIVE,
    (NEW, "BRANCH_LATERAL"): PAUSED,
    (ACTIVE, "BRANCH_LATERAL"): PAUSED,
    (PAUSED, "BRANCH_LATERAL"): PAUSED,
    (ACTIVE, "PAUSE"): PAUSED,
    (ACTIVE, "AUTO_PAUSE"): PAUSED,
    (ACTIVE, "IDLE_TIMEOUT"): DORMANT,
    (PAUSED, "IDLE_TIMEOUT"): DORMANT,
    (DORMANT, "RESUME_CLICKED"): PAUSED,
    (PAUSED, "PRIMER_ACKNOWLEDGED"): ACTIVE,
    (PAUSED, "RESUME"): ACTIVE,
    (ACTIVE, "MARK_RESOLVED"): RESOLVED,
    (PAUSED, "MARK_RESOLVED"): RESOLVED,
    (DORMANT, "MARK_RESOLVED"): RESOLVED,
    (NEW, "MARK_RESOLVED"): RESOLVED,
    (RESOLVED, "REOPEN"): PAUSED,
}


class TransitionError(ValueError):
    pass


def next_state(current: str, event: str) -> str:
    try:
        return TRANSITIONS[(current, event)]
    except KeyError:
        raise TransitionError(f"Event {event} is not valid from state {current}") from None


def get_thread(conn: sqlite3.Connection, thread_id: str) -> dict | None:
    return row(conn.execute("SELECT * FROM threads WHERE id = ?", (thread_id,)))


def touch(conn: sqlite3.Connection, thread_id: str) -> None:
    conn.execute(
        "UPDATE threads SET last_accessed_at = ? WHERE id = ?", (clock.iso(), thread_id)
    )


def fire(conn: sqlite3.Connection, thread_id: str, event: str) -> dict:
    """Apply an event to a thread, log it, and run its side effects."""
    thread = get_thread(conn, thread_id)
    if thread is None:
        raise KeyError(thread_id)
    target = next_state(thread["status"], event)
    now = clock.iso()
    updates = {"status": target}
    if event == "IDLE_TIMEOUT":
        updates["primer_pending"] = 1
    elif event == "PRIMER_ACKNOWLEDGED":
        updates["primer_pending"] = 0
    if event != "IDLE_TIMEOUT":
        # Going dormant is not an access; everything else the user did is.
        updates["last_accessed_at"] = now
    sets = ", ".join(f"{k} = ?" for k in updates)
    # Compare-and-swap on status: concurrent requests (e.g. two dormancy
    # sweeps) must not both apply the same transition.
    cur = conn.execute(
        f"UPDATE threads SET {sets} WHERE id = ? AND status = ?",
        (*updates.values(), thread_id, thread["status"]),
    )
    if cur.rowcount == 0:
        raise TransitionError(f"Thread {thread_id} changed state concurrently")
    conn.execute(
        "INSERT INTO thread_events (id, thread_id, event, from_status, to_status, at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (new_id(), thread_id, event, thread["status"], target, now),
    )
    if target == ACTIVE:
        enforce_active_limit(conn, keep=thread_id)
    return get_thread(conn, thread_id)


def enforce_active_limit(conn: sqlite3.Connection, keep: str) -> None:
    active = rows(
        conn.execute(
            "SELECT id FROM threads WHERE status = 'ACTIVE' AND id != ?"
            " ORDER BY last_accessed_at DESC",
            (keep,),
        )
    )
    allowed_others = max(settings.max_active - 1, 0)
    for t in active[allowed_others:]:
        fire(conn, t["id"], "AUTO_PAUSE")


def sweep_dormancy(conn: sqlite3.Connection) -> int:
    """Move threads idle past the dormancy window to DORMANT. Returns count."""
    cutoff = clock.now() - timedelta(days=settings.dormancy_days)
    candidates = rows(
        conn.execute(
            # A thread already awaiting primer acknowledgement is parked;
            # timing it out again would double-count it in the metric.
            "SELECT id, last_accessed_at FROM threads"
            " WHERE status IN ('ACTIVE','PAUSED') AND primer_pending = 0"
        )
    )
    moved = 0
    for t in candidates:
        if parse_ts(t["last_accessed_at"]) < cutoff:
            try:
                fire(conn, t["id"], "IDLE_TIMEOUT")
                moved += 1
            except TransitionError:
                pass  # another request got there first

    return moved


def create_thread(
    conn: sqlite3.Connection,
    title: str,
    seed_unit_id: str | None,
    parent_thread_id: str | None = None,
    reason: str | None = None,
) -> dict:
    tid = new_id()
    now = clock.iso()
    conn.execute(
        "INSERT INTO threads (id, title, status, parent_thread_id, branch_trigger_concept,"
        " current_unit_id, last_accessed_at, created_at) VALUES (?, ?, 'NEW', ?, ?, ?, ?, ?)",
        (tid, title, parent_thread_id, reason, seed_unit_id, now, now),
    )
    conn.execute(
        "INSERT INTO thread_events (id, thread_id, event, from_status, to_status, at)"
        " VALUES (?, ?, 'CREATED', NULL, 'NEW', ?)",
        (new_id(), tid, now),
    )
    return get_thread(conn, tid)


def open_thread(conn: sqlite3.Connection, thread_id: str) -> tuple[dict, bool]:
    """The user clicked a thread. Returns (thread, needs_primer).

    A dormant thread (or one whose primer was never acknowledged) is never
    dropped straight into content: it goes to PAUSED and asks for a primer.
    """
    thread = get_thread(conn, thread_id)
    if thread is None:
        raise KeyError(thread_id)
    status = thread["status"]
    if status == DORMANT:
        return fire(conn, thread_id, "RESUME_CLICKED"), True
    if status == PAUSED and thread["primer_pending"]:
        return thread, True
    if status == NEW:
        return fire(conn, thread_id, "START_SESSION"), False
    if status == PAUSED:
        return fire(conn, thread_id, "RESUME"), False
    if status == ACTIVE:
        touch(conn, thread_id)
        return get_thread(conn, thread_id), False
    return thread, False  # RESOLVED: read-only view


def resumption_metrics(conn: sqlite3.Connection) -> dict:
    counted = conn.execute(
        "SELECT COUNT(*) FROM thread_events WHERE event = 'IDLE_TIMEOUT'"
    ).fetchone()[0]
    reactivated = conn.execute(
        "SELECT COUNT(*) FROM thread_events WHERE event = 'PRIMER_ACKNOWLEDGED'"
    ).fetchone()[0]
    # Time parked: from going dormant to being picked back up.
    parked_days: list[float] = []
    for tid in rows(conn.execute("SELECT DISTINCT thread_id FROM thread_events")):
        events = rows(
            conn.execute(
                "SELECT event, at FROM thread_events WHERE thread_id = ? ORDER BY at",
                (tid["thread_id"],),
            )
        )
        went_dormant = None
        for e in events:
            if e["event"] == "IDLE_TIMEOUT":
                went_dormant = parse_ts(e["at"])
            elif e["event"] == "PRIMER_ACKNOWLEDGED" and went_dormant is not None:
                parked_days.append((parse_ts(e["at"]) - went_dormant).total_seconds() / 86400)
                went_dormant = None
    parked_days.sort()
    median = None
    if parked_days:
        mid = len(parked_days) // 2
        median = (
            parked_days[mid]
            if len(parked_days) % 2
            else (parked_days[mid - 1] + parked_days[mid]) / 2
        )
    return {
        "dormant_counted": counted,
        "dormant_reactivated": reactivated,
        "resumption_score": (reactivated / counted) if counted else None,
        "median_days_parked_before_return": median,
    }
