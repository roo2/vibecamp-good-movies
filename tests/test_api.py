from dataclasses import replace
from datetime import datetime, timedelta, timezone

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
    for index in range(20):
        db.upsert_film({
            "film_id": f"film-{index}", "title": f"Film {index}", "year": 2000 + index,
            "description": f"A spoiler-free story prompt number {index}.",
        })
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


def test_movie_reaction_is_captured_for_the_active_user():
    access = client.post("/api/access", json={"name": "Ada"}).json()
    headers = {"X-Session-Token": access["token"]}
    group_session = client.post("/api/sessions", headers=headers).json()
    share_token = group_session["share_token"]
    films = client.get(f"/api/onboarding/films?share_token={share_token}", headers=headers)
    assert films.status_code == 200
    assert len(films.json()["films"]) == 5
    film_id = films.json()["films"][0]["id"]

    rating = client.post(
        "/api/onboarding/ratings",
        headers=headers,
        json={"film_id": film_id, "reaction": "loved_it", "session_share_token": share_token},
    )
    assert rating.status_code == 201
    assert rating.json()["reaction"] == "loved_it"

    saved = client.get("/api/onboarding/ratings", headers=headers)
    assert saved.status_code == 200
    assert saved.json()[0]["film_id"] == film_id


def test_session_members_receive_the_same_named_and_blind_film_deck(isolated_web_database):
    from moral_atlas.web.store import group_session_deck
    host = client.post("/api/access", json={"name": "Ada"}).json()
    guest = client.post("/api/access", json={"name": "Sam"}).json()
    host_headers = {"X-Session-Token": host["token"]}
    guest_headers = {"X-Session-Token": guest["token"]}
    share_token = client.post("/api/sessions", headers=host_headers).json()["share_token"]
    client.post(f"/api/sessions/{share_token}/join", headers=guest_headers)

    host_films = client.get(f"/api/onboarding/films?share_token={share_token}", headers=host_headers).json()["films"]
    guest_films = client.get(f"/api/onboarding/films?share_token={share_token}", headers=guest_headers).json()["films"]
    assert host_films == guest_films
    assert len(host_films) == 5

    host_pairs = client.get(f"/api/test/questions?share_token={share_token}", headers=host_headers).json()["questions"]
    guest_pairs = client.get(f"/api/test/questions?share_token={share_token}", headers=guest_headers).json()["questions"]
    assert host_pairs == guest_pairs
    assert len(host_pairs) == 5
    assert all(choice["label"] in {"Story A", "Story B"} for pair in host_pairs for choice in pair["choices"])
    deck = group_session_deck(share_token, host["user"]["id"])
    assert deck is not None
    direct_ids = set(deck["direct"])
    blind_ids = {film_id for pair in deck["pairs"] for film_id in pair}
    assert len(direct_ids) == 5
    assert len(blind_ids) == 10
    assert direct_ids.isdisjoint(blind_ids)


def test_group_session_tracks_members_and_unlocks_when_everyone_completes():
    host = client.post("/api/access", json={"name": "Ada"}).json()
    guest = client.post("/api/access", json={"name": "Sam"}).json()
    host_headers = {"X-Session-Token": host["token"]}
    guest_headers = {"X-Session-Token": guest["token"]}

    created = client.post("/api/sessions", headers=host_headers)
    assert created.status_code == 201
    share_token = created.json()["share_token"]
    assert client.post(f"/api/sessions/{share_token}/join", headers=guest_headers).status_code == 200
    assert client.post(f"/api/sessions/{share_token}/start", headers=host_headers).status_code == 200

    for headers in (host_headers, guest_headers):
        response = client.post("/api/test/results", headers=headers, json={
            "answers": {"pair-1": "a"}, "session_share_token": share_token,
        })
        assert response.status_code == 201

    assert client.post(f"/api/sessions/{share_token}/wait", headers=host_headers).status_code == 200
    session_status = client.get(f"/api/sessions/{share_token}", headers=host_headers).json()
    assert [member["user"]["name"] for member in session_status["members"]] == ["Ada", "Sam"]
    assert all(member["completed_at"] for member in session_status["members"])
    continued = client.post(f"/api/sessions/{share_token}/continue", headers=host_headers)
    assert continued.status_code == 200
    assert continued.json()["status"] == "results_started"


def test_host_can_continue_after_waiting_ten_minutes_with_incomplete_members(isolated_web_database):
    host = client.post("/api/access", json={"name": "Ada"}).json()
    guest = client.post("/api/access", json={"name": "Sam"}).json()
    host_headers = {"X-Session-Token": host["token"]}
    group_session = client.post("/api/sessions", headers=host_headers).json()
    share_token = group_session["share_token"]
    client.post(f"/api/sessions/{share_token}/join", headers={"X-Session-Token": guest["token"]})
    client.post(f"/api/sessions/{share_token}/start", headers=host_headers)
    client.post(f"/api/sessions/{share_token}/wait", headers=host_headers)

    assert client.post(f"/api/sessions/{share_token}/continue", headers=host_headers).status_code == 403
    with isolated_web_database.connect() as con:
        con.execute(
            "UPDATE group_sessions SET waiting_started_at=? WHERE share_token=?",
            [(datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat(), share_token],
        )
    continued = client.post(f"/api/sessions/{share_token}/continue", headers=host_headers)
    assert continued.status_code == 200
    assert continued.json()["status"] == "results_started"


def test_shortlist_no_hides_a_film_from_other_members_and_unanimous_yes_selects_it():
    host = client.post("/api/access", json={"name": "Ada"}).json()
    guest = client.post("/api/access", json={"name": "Sam"}).json()
    host_headers = {"X-Session-Token": host["token"]}
    guest_headers = {"X-Session-Token": guest["token"]}
    share_token = client.post("/api/sessions", headers=host_headers).json()["share_token"]
    assert client.post(f"/api/sessions/{share_token}/join", headers=guest_headers).status_code == 200

    first = client.get(f"/api/shortlist/next?share_token={share_token}", headers=host_headers)
    assert first.status_code == 200
    assert "artwork_url" in first.json()["film"]
    rejected_id = first.json()["film"]["id"]
    assert client.post("/api/shortlist/reactions", headers=host_headers, json={
        "share_token": share_token, "film_id": rejected_id, "reaction": "no",
    }).json()["state"] == "continue"

    guest_next = client.get(f"/api/shortlist/next?share_token={share_token}", headers=guest_headers).json()
    assert guest_next["state"] == "card"
    assert guest_next["film"]["id"] != rejected_id
    selected_id = guest_next["film"]["id"]
    host_next = client.get(f"/api/shortlist/next?share_token={share_token}", headers=host_headers).json()
    assert host_next["film"]["id"] == selected_id

    host_vote = client.post("/api/shortlist/reactions", headers=host_headers, json={
        "share_token": share_token, "film_id": selected_id, "reaction": "yes",
    })
    assert host_vote.json()["state"] == "continue"
    guest_vote = client.post("/api/shortlist/reactions", headers=guest_headers, json={
        "share_token": share_token, "film_id": selected_id, "reaction": "yes",
    })
    assert guest_vote.json()["state"] == "selected"
    assert guest_vote.json()["film"]["id"] == selected_id

    persisted_selection = client.get(f"/api/shortlist/selection?share_token={share_token}", headers=host_headers)
    assert persisted_selection.json() == guest_vote.json()
