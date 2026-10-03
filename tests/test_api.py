from tests.conftest import advance_days


def _unit(client, slug):
    return client.get(f"/api/units/{slug}").json()


def _new_thread(client, slug="softmax", title="Why softmax?"):
    unit = _unit(client, slug)
    r = client.post("/api/threads", json={"title": title, "seed_unit_id": unit["id"]})
    assert r.status_code == 201
    return r.json(), unit


def test_seed_loaded(client):
    units = client.get("/api/units").json()
    assert len(units) >= 8
    sm = _unit(client, "softmax")
    lenses = {(l["depth_level"], l["lens"]) for l in sm["layers"]}
    assert {(0, "core"), (1, "core"), (2, "core"), (1, "pattern"), (1, "steps")} <= lenses
    assert sm["probe"]["prompt"]
    rel = sm["relations"]
    assert any(x["title"].startswith("The Boltzmann") for x in rel["analogous"])
    # attention REQUIRES softmax, so from softmax attention is downstream
    assert any("attention" in x["title"].lower() for x in rel["downstream"])


def test_new_thread_opens_active(client):
    t, _ = _new_thread(client)
    assert t["status"] == "NEW"
    r = client.post(f"/api/threads/{t['id']}/open").json()
    assert r["needs_primer"] is False
    assert r["thread"]["status"] == "ACTIVE"


def test_branch_pauses_parent_and_links(client):
    t, unit = _new_thread(client, "scaled-dot-product-attention", "Attention")
    client.post(f"/api/threads/{t['id']}/open")
    sm = _unit(client, "softmax")
    r = client.post(
        f"/api/threads/{t['id']}/branch",
        json={"unit_id": sm["id"], "reason": "Need softmax first", "relationship_type": "REQUIRES"},
    )
    assert r.status_code == 201
    child = r.json()
    assert child["status"] == "ACTIVE"
    assert child["parent"]["id"] == t["id"]
    assert child["branch_trigger_concept"] == "Need softmax first"
    parent = client.get(f"/api/threads/{t['id']}").json()
    assert parent["status"] == "PAUSED"
    # Returning to the parent soon after needs no primer.
    back = client.post(f"/api/threads/{t['id']}/open").json()
    assert back["needs_primer"] is False and back["thread"]["status"] == "ACTIVE"


def test_branch_to_free_concept_creates_stub(client):
    t, _ = _new_thread(client)
    client.post(f"/api/threads/{t['id']}/open")
    child = client.post(f"/api/threads/{t['id']}/branch", json={"concept": "Gumbel-softmax trick"}).json()
    assert child["current_unit_title"] == "Gumbel-softmax trick"


def test_active_limit_enforced(client):
    ids = []
    for slug in ("softmax", "shannon-entropy", "singular-value-decomposition"):
        t, _ = _new_thread(client, slug, slug)
        client.post(f"/api/threads/{t['id']}/open")
        ids.append(t["id"])
        advance_days(0.01)
    active = client.get("/api/threads?status=ACTIVE").json()
    assert len(active) == 2
    assert ids[0] not in {a["id"] for a in active}


def test_dormancy_primer_and_resume_cycle(client):
    t, unit = _new_thread(client)
    tid = t["id"]
    client.post(f"/api/threads/{tid}/open")
    client.post(f"/api/threads/{tid}/progress", json={"unit_id": unit["id"], "depth": 1, "status": "CONSOLIDATED"})
    client.post(f"/api/threads/{tid}/pins", json={"text": "Why is the Jacobian PSD?", "unit_id": unit["id"]})

    advance_days(8)
    listed = {x["id"]: x for x in client.get("/api/threads").json()}
    assert listed[tid]["status"] == "DORMANT"

    opened = client.post(f"/api/threads/{tid}/open").json()
    assert opened["needs_primer"] is True
    p = opened["primer"]
    assert p["origin"] == "fallback"  # no HF token in tests
    assert p["open_question"] == "Why is the Jacobian PSD?"
    assert p["recommended_unit_id"] == unit["id"]
    assert any("Softmax" in s for s in p["consolidated_points"])

    # Cached: same id when nothing changed.
    assert client.get(f"/api/threads/{tid}/primer").json()["id"] == p["id"]

    # Closing the modal without acknowledging must not bypass the primer.
    again = client.post(f"/api/threads/{tid}/open").json()
    assert again["needs_primer"] is True

    resumed = client.post(f"/api/threads/{tid}/resume").json()
    assert resumed["status"] == "ACTIVE"
    m = client.get("/api/metrics").json()
    assert m["dormant_counted"] == 1 and m["dormant_reactivated"] == 1
    assert m["resumption_score"] == 1.0


def test_primer_cache_invalidates_on_progress(client):
    t, unit = _new_thread(client)
    tid = t["id"]
    client.post(f"/api/threads/{tid}/open")
    p1 = client.get(f"/api/threads/{tid}/primer").json()
    client.post(f"/api/threads/{tid}/pins", json={"text": "new loop"})
    p2 = client.get(f"/api/threads/{tid}/primer").json()
    assert p1["id"] != p2["id"] and p2["open_question"] == "new loop"


def test_resolve_and_reopen(client):
    t, _ = _new_thread(client)
    client.post(f"/api/threads/{t['id']}/open")
    assert client.post(f"/api/threads/{t['id']}/resolve").json()["status"] == "RESOLVED"
    assert client.post(f"/api/threads/{t['id']}/branch", json={"concept": "x"}).status_code == 409
    assert client.post(f"/api/threads/{t['id']}/reopen").json()["status"] == "PAUSED"


def test_progress_depth_is_monotonic(client):
    t, unit = _new_thread(client)
    tid = t["id"]
    client.post(f"/api/threads/{tid}/progress", json={"unit_id": unit["id"], "depth": 2})
    r = client.post(f"/api/threads/{tid}/progress", json={"unit_id": unit["id"], "depth": 0}).json()
    assert r["max_depth_reached"] == 2


def test_recall_queue_and_spacing(client):
    t, unit = _new_thread(client)
    tid = t["id"]
    assert client.get("/api/recall/queue").json() == []
    client.post(f"/api/threads/{tid}/progress", json={"unit_id": unit["id"], "depth": 1})
    q = client.get("/api/recall/queue").json()
    assert len(q) == 1
    probe_id = q[0]["probe_id"]
    a = client.post(f"/api/recall/{probe_id}/attempt", json={"rating": "solid"}).json()
    assert a["interval_days"] == 7.5
    assert client.get("/api/recall/queue").json() == []
    advance_days(8)
    assert len(client.get("/api/recall/queue").json()) == 1
    a2 = client.post(f"/api/recall/{probe_id}/attempt", json={"rating": "solid"}).json()
    assert a2["interval_days"] == 7.5 * 2.5


def test_expand_without_token_is_503(client):
    unit = _unit(client, "softmax")
    r = client.post(f"/api/units/{unit['id']}/expand", json={"level": 2, "lens": "pattern"})
    assert r.status_code == 503


def test_ingest_text_fallback(client):
    text = "Jensen's inequality\n\nFor a convex function f and a random variable X, f of the expectation of X is at most the expectation of f of X, with equality for affine f or degenerate X."
    r = client.post("/api/ingest", json={"kind": "text", "ref": text, "domain": "Probability"})
    assert r.status_code == 201
    u = r.json()
    assert u["title"] == "Jensen's inequality"
    assert u["layers"][0]["origin"] == "extracted"


def test_export(client):
    data = client.get("/api/export").json()
    assert "threads" in data and len(data["knowledge_units"]) >= 8


def test_auth_gate(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "app_password", "pw")
    assert client.get("/api/units").status_code == 401
    r = client.post("/login", data={"password": "pw"}, follow_redirects=False)
    assert r.status_code == 303
    client.cookies.set("tr_session", r.cookies.get("tr_session"))
    assert client.get("/api/units").status_code == 200


def test_concurrent_sweeps_do_not_error(client):
    import threading
    t, _ = _new_thread(client)
    client.post(f"/api/threads/{t['id']}/open")
    advance_days(8)
    codes = []
    def hit(path):
        codes.append(client.get(path).status_code)
    ths = [threading.Thread(target=hit, args=(p,)) for p in ["/api/threads", "/api/metrics"] * 4]
    [x.start() for x in ths]; [x.join() for x in ths]
    assert set(codes) == {200}
    assert client.get("/api/metrics").json()["dormant_counted"] == 1


def test_sweep_skips_thread_that_changed_underneath():
    from app.state import TransitionError, fire
    import sqlite3
    from app import db
    conn = sqlite3.connect(":memory:"); conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)
    conn.execute("INSERT INTO threads (id,title,status,last_accessed_at,created_at) VALUES ('t','x','DORMANT','2020-01-01','2020-01-01')")
    import pytest
    with pytest.raises(TransitionError):
        fire(conn, "t", "IDLE_TIMEOUT")
