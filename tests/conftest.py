import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import settings


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "test.db")
    monkeypatch.setattr(settings, "hf_token", None)  # LLM off: exercise fallbacks
    monkeypatch.setattr(settings, "openrouter_api_key", None)
    monkeypatch.setattr(settings, "app_password", None)
    db.clock.offset_seconds = 0
    from app.main import app

    with TestClient(app) as c:
        yield c
    db.clock.offset_seconds = 0


def advance_days(days: float) -> None:
    db.clock.offset_seconds += days * 86400
