"""The landing page has one hard requirement: it always renders.

It is the first thing anyone opens, including on a fresh clone with no database
and on a half-finished pipeline run, so every test here is really the same test
asked in a different state of the store.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from moral_atlas.api import app
from moral_atlas.web.routes import landing


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_root_serves_html_with_both_doors(client, monkeypatch):
    monkeypatch.setattr(landing, "_snapshot", lambda: {
        "films": 40, "evidence": 133, "skeletons": 284, "propositions": 696,
        "bank_items": 694, "scores": 3000,
        "dimensions": [("Payback or Mercy", 79), ("Telling or Sparing", 35)],
        "variants": [("spine", 40), ("subs", 38)], "ready": True,
    })
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    body = r.text
    assert "localhost:5173" in body          # the frontend door
    assert "localhost:8001" in body          # the data door
    assert "Payback or Mercy" in body
    assert "696" in body                     # counts are formatted with separators


def test_root_renders_on_an_empty_store(client, monkeypatch):
    """A fresh clone hits `/` before `atlas ingest` has ever run."""
    monkeypatch.setattr(landing, "_snapshot", lambda: {
        "films": 0, "evidence": 0, "skeletons": 0, "propositions": 0,
        "bank_items": 0, "scores": 0, "dimensions": [], "variants": [],
        "ready": False,
    })
    r = client.get("/")
    assert r.status_code == 200
    assert "atlas dimensions" in r.text      # tells you what to run next
    assert "Nothing scored yet" in r.text


def test_snapshot_survives_a_missing_database(monkeypatch, tmp_path):
    """No database at all must read as zeroes, not as a 500."""
    from moral_atlas import config

    config.settings.cache_clear()
    monkeypatch.setenv("HOME", str(tmp_path))
    real = config.Settings()
    object.__setattr__(real, "db_path", tmp_path / "nope.sqlite")
    monkeypatch.setattr(landing, "settings", lambda: real)
    snap = landing._snapshot()
    assert snap["films"] == 0 and snap["dimensions"] == [] and not snap["ready"]


def test_bars_scale_to_the_widest_axis():
    html = landing._bars([("A", 100), ("B", 50)])
    assert "--w:100.0%" in html and "--w:50.0%" in html


def test_bars_and_coverage_explain_themselves_when_empty():
    assert "atlas dimensions" in landing._bars([])
    assert "Nothing scored" in landing._coverage([], 40)


def test_coverage_is_a_share_of_the_corpus():
    html = landing._coverage([("subs", 20)], 40)
    assert "--w:50.0%" in html and "20/40" in html


def test_urls_are_escaped_into_the_page(client, monkeypatch):
    """The URLs come from the environment, so they are attacker-adjacent input."""
    from moral_atlas import config

    config.settings.cache_clear()
    monkeypatch.setenv("ATLAS_FRONTEND_URL", 'http://x/"><script>alert(1)</script>')
    try:
        r = client.get("/")
        assert r.status_code == 200
        assert "<script>alert(1)</script>" not in r.text
    finally:
        config.settings.cache_clear()
