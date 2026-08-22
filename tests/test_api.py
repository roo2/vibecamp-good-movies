from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from moral_atlas.web.app import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_web_database(monkeypatch, tmp_path):
    """Web persistence tests never write into the developer's atlas database."""
    from moral_atlas import db
    from moral_atlas.config import settings

    test_settings = replace(
        settings(), data_dir=tmp_path, cache_dir=tmp_path / "cache",
        db_path=tmp_path / "web.sqlite",
    )
    monkeypatch.setattr(db, "settings", lambda: test_settings)
    db.init_db()
    return db


def test_name_only_access_and_result_capture(isolated_web_database):
    access = client.post("/api/access", json={"name": "Ada"})
    assert access.status_code == 201
    payload = access.json()
    assert payload["user"]["name"] == "Ada"

    current_user = client.get("/api/access/me", headers={"X-Session-Token": payload["token"]})
    assert current_user.status_code == 200
    assert current_user.json() == payload["user"]

    result = client.post(
        "/api/test/results",
        headers={"X-Session-Token": payload["token"]},
        json={"answers": {"responsibility": "a", "loyalty": "neither"}},
    )
    assert result.status_code == 201
    assert result.json()["answered_count"] == 2

    saved = client.get("/api/test/results", headers={"X-Session-Token": payload["token"]})
    assert saved.status_code == 200
    assert len(saved.json()) == 1

    with isolated_web_database.connect(read_only=True) as con:
        user = con.execute("SELECT user_id, name FROM users").fetchone()
        assert dict(user) == {"user_id": payload["user"]["id"], "name": "Ada"}
        assert con.execute("SELECT count(*) FROM test_results").fetchone()[0] == 1


def test_results_require_a_session():
    response = client.post("/api/test/results", json={"answers": {}})
    assert response.status_code == 401


def test_movie_reaction_is_captured_for_the_active_user(monkeypatch):
    from moral_atlas.web.routes import onboarding

    monkeypatch.setattr(onboarding, "random_onboarding_films", lambda limit=10: [{
        "id": "the-lion-king-1994", "title": "The Lion King", "year": 1994,
        "genre": "Animation", "runtime_min": 88,
    }])
    monkeypatch.setattr(onboarding, "film_exists", lambda film_id: film_id == "the-lion-king-1994")
    access = client.post("/api/access", json={"name": "Ada"}).json()
    films = client.get("/api/onboarding/films")
    assert films.status_code == 200
    assert films.json()["films"][0]["id"] == "the-lion-king-1994"

    rating = client.post(
        "/api/onboarding/ratings",
        headers={"X-Session-Token": access["token"]},
        json={"film_id": "the-lion-king-1994", "reaction": "loved_it"},
    )
    assert rating.status_code == 201
    assert rating.json()["reaction"] == "loved_it"

    saved = client.get("/api/onboarding/ratings", headers={"X-Session-Token": access["token"]})
    assert saved.status_code == 200
    assert saved.json()[0]["film_id"] == "the-lion-king-1994"
