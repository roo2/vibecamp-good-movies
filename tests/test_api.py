from fastapi.testclient import TestClient

from moral_atlas.web.app import app


client = TestClient(app)


def test_name_only_access_and_result_capture():
    access = client.post("/api/access", json={"name": "Ada"})
    assert access.status_code == 201
    payload = access.json()
    assert payload["user"]["name"] == "Ada"

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
