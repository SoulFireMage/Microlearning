import json

import pytest

from app import llm
from app.config import settings


def test_think_filter_across_chunk_boundaries():
    f = llm.ThinkFilter()
    chunks = ["Hel", "lo <thi", "nk>secret reasoning</th", "ink> world", " <think>more</think>!"]
    out = "".join(f.feed(c) for c in chunks) + f.flush()
    assert out == "Hello  world !"


def test_extract_json_handles_fences_and_think():
    text = '<think>hmm {"no": 1}</think>Sure:\n```json\n{"a": [1, 2]}\n```'
    assert llm.extract_json(text) == {"a": [1, 2]}


@pytest.fixture()
def llm_on(client, monkeypatch):
    monkeypatch.setattr(settings, "hf_token", "test-token")
    return client


def test_expand_streams_and_saves(llm_on, monkeypatch):
    client = llm_on
    captured = {}

    def fake_stream(system, user, max_tokens=4000):
        captured["system"], captured["user"] = system, user
        yield "## Pattern\n"
        yield "Softmax is Boltzmann."

    monkeypatch.setattr(llm, "stream", fake_stream)
    unit = client.get("/api/units/softmax").json()
    r = client.post(f"/api/units/{unit['id']}/expand", json={"level": 2, "lens": "pattern"})
    assert r.status_code == 200
    assert r.text == "## Pattern\nSoftmax is Boltzmann."
    assert "PATTERN lens" in captured["system"] and "do not invent citations" in captured["system"]
    assert "Bridle" in captured["user"]  # sources passed for grounding
    layer = [l for l in client.get(f"/api/units/{unit['id']}").json()["layers"]
             if l["depth_level"] == 2 and l["lens"] == "pattern"][0]
    assert layer["origin"] == "synthesised" and layer["model"] == settings.default_model


def test_ingest_with_llm_validates_relation_ids(llm_on, monkeypatch):
    client = llm_on
    sm = client.get("/api/units/softmax").json()

    def fake_json(system, user, max_tokens=1500):
        assert "SOURCE TEXT" in user and sm["id"] in user
        return {
            "title": "Log-sum-exp",
            "domain": "ML Mathematics",
            "l0": "A smooth max.",
            "l1": "Convex; gradient is softmax.",
            "probe": {"prompt": "Why is LSE a smooth max?", "answer": "max <= LSE <= max + log n"},
            "relations": [
                {"target_id": sm["id"], "type": "extends", "description": "gradient of LSE is softmax"},
                {"target_id": "made-up-id", "type": "REQUIRES", "description": "hallucinated"},
            ],
        }

    monkeypatch.setattr(llm, "complete_json", fake_json)
    r = client.post("/api/ingest", json={"kind": "text", "ref": "Log-sum-exp\nLSE(x) = log sum exp x_i is a smooth approximation to the maximum."})
    assert r.status_code == 201
    u = r.json()
    assert u["title"] == "Log-sum-exp"
    assert {l["origin"] for l in u["layers"]} == {"synthesised"}
    assert u["probe"]["origin"] == "synthesised"
    prereqs = u["relations"]["prerequisites"]
    assert [p["id"] for p in prereqs] == [sm["id"]]  # hallucinated id dropped


def test_primer_uses_llm_but_recommends_deterministically(llm_on, monkeypatch):
    client = llm_on
    monkeypatch.setattr(llm, "complete_json", lambda *a, **k: {
        "anchor_summary": "Why logits become probabilities.",
        "consolidated_points": ["a", "b", "c", "d"],
        "open_question": "PSD Jacobian?",
        "suggested_next_unit_id": "something-invented",
    })
    unit = client.get("/api/units/softmax").json()
    t = client.post("/api/threads", json={"title": "x", "seed_unit_id": unit["id"]}).json()
    p = client.get(f"/api/threads/{t['id']}/primer").json()
    assert p["origin"] == "synthesised"
    assert len(p["consolidated_points"]) == 3
    assert p["recommended_unit_id"] == unit["id"]


def test_primer_falls_back_when_llm_raises(llm_on, monkeypatch):
    client = llm_on
    def boom(*a, **k):
        raise TimeoutError("provider cold")
    monkeypatch.setattr(llm, "complete_json", boom)
    unit = client.get("/api/units/softmax").json()
    t = client.post("/api/threads", json={"title": "x", "seed_unit_id": unit["id"]}).json()
    assert client.get(f"/api/threads/{t['id']}/primer").json()["origin"] == "fallback"


def test_backend_selection(monkeypatch):
    monkeypatch.setattr(settings, "hf_token", "hf")
    monkeypatch.setattr(settings, "openrouter_api_key", None)
    monkeypatch.setattr(settings, "llm_backend_pref", "auto")
    assert settings.llm_backend == "hf" and settings.model == settings.default_model
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-or")
    assert settings.llm_backend == "openrouter" and settings.model == settings.openrouter_model
    monkeypatch.setattr(settings, "llm_backend_pref", "hf")
    assert settings.llm_backend == "hf"
    monkeypatch.setattr(settings, "hf_token", None)
    assert settings.llm_backend is None and not settings.llm_enabled
