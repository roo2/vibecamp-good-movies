"""Tests for the dyno serving the interface and the API from one process.

The failure this guards against is specific and quiet: a catch-all that hands
index.html to everything turns a mistyped API path into a 200 with a web page in
it. The front end then reads `<!doctype html>` as JSON and reports something
unrelated, three layers away from the actual mistake.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from moral_atlas.web import frontend


@pytest.fixture
def built(tmp_path: Path) -> Path:
    """A dist directory shaped like one Vite writes."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)")
    (tmp_path / "index.html").write_text("<!doctype html><title>App</title>")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    return tmp_path


@pytest.fixture
def client(built: Path) -> TestClient:
    app = FastAPI()

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    assert frontend.mount(app, built)
    return TestClient(app)


def test_the_interface_is_served_at_the_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "<title>App</title>" in r.text


def test_a_route_inside_the_interface_gets_the_interface(client):
    """`/stance` is a screen, not an endpoint — the browser asks the server for
    it on a reload and must get the app back, not a 404."""
    r = client.get("/stance")
    assert r.status_code == 200
    assert "<title>App</title>" in r.text


def test_the_api_still_answers(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_an_unknown_api_path_is_a_404_not_a_web_page(client):
    """The whole reason the catch-all checks prefixes."""
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
    assert "doctype" not in r.text.lower()


def test_real_files_are_served_as_themselves(client):
    r = client.get("/favicon.svg")
    assert r.status_code == 200
    assert r.text == "<svg/>"


def test_hashed_assets_are_cached_and_the_index_is_not(client):
    """index.html names the current asset hashes. A cached one points a
    returning browser at files that no longer exist, which is a white screen."""
    assert "immutable" in client.get("/assets/index-abc123.js").headers["cache-control"]
    assert client.get("/").headers["cache-control"] == "no-store"


def test_a_missing_build_explains_itself_rather_than_crashing(tmp_path):
    """A dyno that dies on boot over a front-end build takes the API with it."""
    app = FastAPI()

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    assert not frontend.mount(app, tmp_path / "nothing-here")
    client = TestClient(app)
    assert client.get("/").status_code == 503
    assert client.get("/api/health").status_code == 200


def test_the_pipeline_page_keeps_its_own_address():
    """`/internal` is where it lives whether or not the interface is served, so
    a runbook can name one URL and be right on both."""
    from moral_atlas.web.app import app

    r = TestClient(app).get("/internal")
    assert r.status_code == 200
    assert "atlas" in r.text.lower()


def test_an_expensive_document_is_built_once_under_concurrency():
    """Two cold requests must not each run the same permutation test.

    On one dyno CPU that is not twice the work, it is worse than twice: the two
    builds interleave and each makes the other slower, to produce the identical
    document.
    """
    import threading

    from moral_atlas import db
    from moral_atlas.web import documents

    db.init_db()
    documents.forget("thing")
    builds = []

    def slow_build():
        builds.append(1)
        threading.Event().wait(0.2)
        return {"built": True}

    threads = [threading.Thread(target=documents.get, args=("thing", "k1", slow_build))
               for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(builds) == 1, f"built {len(builds)} times, wanted once"


def test_a_document_survives_the_process_that_built_it():
    """A restart must not mean building it again.

    Held only in memory these were rebuilt on every boot, and the machine they
    run on takes forty seconds over the atlas and twelve over a model's factors
    — so the first person through the door each morning paid for both, while
    they competed for the one CPU. The store outlives the process.
    """
    from moral_atlas import db
    from moral_atlas.web import documents

    db.init_db()
    documents.forget("thing")
    builds = []

    def build():
        builds.append(1)
        return {"films": ["a"]}

    first = documents.get("thing", "k1", build)
    documents.forget("thing")               # what a restart looks like from here
    second = documents.get("thing", "k1", build)

    assert first == second
    assert len(builds) == 1, "the second process should have read it, not made it"


def test_a_document_built_against_an_older_corpus_is_not_served():
    """The stored copy is keyed on what it was derived from, so a sweep drops it."""
    from moral_atlas import db
    from moral_atlas.web import documents

    db.init_db()
    documents.forget("thing")

    assert documents.get("thing", "films=1", lambda: {"films": 1}) == {"films": 1}
    documents.forget("thing")
    assert documents.get("thing", "films=2", lambda: {"films": 2}) == {"films": 2}

    with db.connect(read_only=True) as con:
        kept = con.execute("SELECT COUNT(*) AS n FROM documents WHERE name='thing'"
                           ).fetchone()["n"]
    assert kept == 1, "and the superseded one is dropped rather than piling up"


def test_documents_are_kept_apart_by_name():
    """The atlas and each model's factors share the table and must not share a row."""
    from moral_atlas import db
    from moral_atlas.web import documents

    db.init_db()
    documents.forget("one")
    documents.forget("two")

    documents.get("one", "k", lambda: {"which": "one"})
    documents.get("two", "k", lambda: {"which": "two"})
    documents.forget("one")

    assert documents.get("one", "k", lambda: {"which": "rebuilt"}) == {"which": "one"}
