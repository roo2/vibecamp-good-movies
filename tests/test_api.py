from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from moral_atlas.web.app import app
from moral_atlas.web.film_service import DIRECT_CARDS, MIN_CARDS


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
            "artwork_url": f"https://example.test/posters/film-{index}.jpg",
        })
    return db


def test_health_is_reachable_under_the_api_prefix():
    """/api/* is the only prefix CloudFront routes here, so /health alone is
    answered by the bucket in the published environment and proves nothing."""
    body = client.get("/api/health")
    assert body.status_code == 200
    assert body.json()["status"] == "ok"
    assert body.json()["version"] == app.version


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
    assert len(films.json()["films"]) == DIRECT_CARDS
    assert all(film["artwork_url"] for film in films.json()["films"])
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


def test_session_direct_deck_uses_only_films_with_artwork(isolated_web_database):
    from moral_atlas.web.film_service import build_session_deck

    films = isolated_web_database.list_films()
    eligible = films[:DIRECT_CARDS]
    with isolated_web_database.connect() as con:
        con.execute("UPDATE films SET artwork_url=NULL")
        for film in eligible:
            con.execute(
                "UPDATE films SET artwork_url=? WHERE film_id=?",
                [f"https://example.test/posters/{film['film_id']}.jpg", film["film_id"]],
            )

    deck = build_session_deck()
    assert len(deck["direct"]) == DIRECT_CARDS
    assert set(deck["direct"]) == {film["film_id"] for film in eligible}


def test_session_deck_needs_enough_eligible_films(isolated_web_database):
    """A short deck is fine; a deck too short to read anybody is not."""
    from moral_atlas.web.film_service import build_session_deck

    films = isolated_web_database.list_films()
    with isolated_web_database.connect() as con:
        con.execute("UPDATE films SET artwork_url=NULL")
        for film in films[:MIN_CARDS - 1]:
            con.execute("UPDATE films SET artwork_url=? WHERE film_id=?",
                        ["https://example.test/p.jpg", film["film_id"]])

    assert build_session_deck() == {"direct": [], "pairs": []}


def test_session_members_receive_the_same_named_film_deck(isolated_web_database):
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
    assert len(host_films) == DIRECT_CARDS
    assert all(film["title"] and film["artwork_url"] for film in host_films)

    deck = group_session_deck(share_token, host["user"]["id"])
    assert deck is not None
    assert len(set(deck["direct"])) == DIRECT_CARDS
    # The blind story pairs were removed from the product: every question now
    # names its film and shows its poster. The key survives so that decks written
    # before the change still read.
    assert deck["pairs"] == []


def test_group_session_tracks_members_and_unlocks_when_everyone_completes(isolated_web_database):
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
            # No pair answers exist any more; finishing the film reactions is
            # what submits, and the submission is what marks a member ready.
            "answers": {}, "session_share_token": share_token,
        })
        assert response.status_code == 201

    assert client.post(f"/api/sessions/{share_token}/wait", headers=host_headers).status_code == 200
    session_status = client.get(f"/api/sessions/{share_token}", headers=host_headers).json()
    assert [member["user"]["name"] for member in session_status["members"]] == ["Ada", "Sam"]
    assert all(member["completed_at"] for member in session_status["members"])

    current = client.get(f"/api/test/results/current?share_token={share_token}", headers=guest_headers)
    assert current.status_code == 200
    assert client.post(f"/api/sessions/{share_token}/unready", headers=guest_headers).status_code == 200
    reopened_status = client.get(f"/api/sessions/{share_token}", headers=host_headers).json()
    assert reopened_status["members"][1]["completed_at"] is None
    assert client.post(f"/api/sessions/{share_token}/continue", headers=host_headers).status_code == 403

    # Submitting again for the same session updates the row rather than adding
    # one, which is what the count below is checking.
    revised = client.post("/api/test/results", headers=guest_headers, json={
        "answers": {}, "session_share_token": share_token,
    })
    assert revised.status_code == 201
    with isolated_web_database.connect(read_only=True) as con:
        assert con.execute(
            "SELECT count(*) FROM test_results WHERE user_id=? AND session_share_token=?",
            [guest["user"]["id"], share_token],
        ).fetchone()[0] == 1

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


def test_shortlist_no_hides_a_film_and_three_shared_yeses_make_a_shortlist():
    """A no removes a film for everyone; three mutual yeses end the swiping.

    The product used to stop at the first film both people wanted, which decided
    the evening for a couple who were enjoying deciding it. Agreement now
    accumulates, and the swiping ends with a shortlist to choose between.
    """
    from moral_atlas.web.store import MATCHES_WANTED

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

    # One person's no takes the film off both decks.
    guest_next = client.get(f"/api/shortlist/next?share_token={share_token}", headers=guest_headers).json()
    assert guest_next["state"] == "card"
    assert guest_next["film"]["id"] != rejected_id
    host_next = client.get(f"/api/shortlist/next?share_token={share_token}", headers=host_headers).json()
    assert host_next["film"]["id"] == guest_next["film"]["id"]

    agreed = []
    while len(agreed) < MATCHES_WANTED:
        card = client.get(f"/api/shortlist/next?share_token={share_token}", headers=host_headers).json()
        assert card["state"] == "card", "the deck ran out before the shortlist filled"
        film_id = card["film"]["id"]
        host_vote = client.post("/api/shortlist/reactions", headers=host_headers, json={
            "share_token": share_token, "film_id": film_id, "reaction": "yes",
        }).json()
        # One person wanting it is never enough, however many they have wanted.
        assert host_vote["state"] == "continue"
        guest_vote = client.post("/api/shortlist/reactions", headers=guest_headers, json={
            "share_token": share_token, "film_id": film_id, "reaction": "yes",
        }).json()
        agreed.append(film_id)
        expected = "shortlist" if len(agreed) == MATCHES_WANTED else "continue"
        assert guest_vote["state"] == expected, (
            f"{len(agreed)} mutual yes(es) should read as {expected}")
        if expected == "continue":
            assert guest_vote["matches"] == len(agreed)

    assert [film["id"] for film in guest_vote["films"]] == agreed
    assert all("artwork_url" in film for film in guest_vote["films"])

    # Both of them see the same shortlist, and asking for another card returns it
    # rather than handing out a film nobody needs to judge.
    for headers in (host_headers, guest_headers):
        assert client.get(f"/api/shortlist/selection?share_token={share_token}",
                          headers=headers).json() == guest_vote
        assert client.get(f"/api/shortlist/next?share_token={share_token}",
                          headers=headers).json()["state"] == "shortlist"


def test_a_removed_yes_takes_a_film_back_off_the_shortlist(isolated_web_database):
    """The shortlist is derived from the votes, so it cannot disagree with them."""
    from moral_atlas.web.store import _agreed_films

    host = client.post("/api/access", json={"name": "Ada"}).json()
    guest = client.post("/api/access", json={"name": "Sam"}).json()
    host_headers = {"X-Session-Token": host["token"]}
    share_token = client.post("/api/sessions", headers=host_headers).json()["share_token"]
    client.post(f"/api/sessions/{share_token}/join", headers={"X-Session-Token": guest["token"]})

    card = client.get(f"/api/shortlist/next?share_token={share_token}", headers=host_headers).json()
    film_id = card["film"]["id"]
    for token in (host["token"], guest["token"]):
        client.post("/api/shortlist/reactions", headers={"X-Session-Token": token}, json={
            "share_token": share_token, "film_id": film_id, "reaction": "yes",
        })

    with isolated_web_database.connect() as con:
        session_id = con.execute("SELECT session_id FROM group_sessions WHERE share_token=?",
                                 [share_token]).fetchone()["session_id"]
        assert _agreed_films(con, session_id) == [film_id]
        con.execute("DELETE FROM shortlist_reactions WHERE session_id=? AND user_id=?",
                    [session_id, guest["user"]["id"]])
        assert _agreed_films(con, session_id) == []


def test_someone_can_take_it_alone_and_without_giving_a_name(isolated_web_database):
    """The solo path: no name, no invitation, no waiting for anybody.

    A room of one is the same machinery with one fewer person in it — the read is
    what the instrument does before it compares anyone — so this checks the two
    places a group of one could have gone wrong: access without a name, and a
    shortlist that requires unanimity among a single person.
    """
    from moral_atlas.web.store import MATCHES_WANTED

    access = client.post("/api/access", json={})
    assert access.status_code == 201, "a name must not be required to start"
    me = access.json()
    assert me["user"]["name"] == ""
    headers = {"X-Session-Token": me["token"]}

    share_token = client.post("/api/sessions", headers=headers).json()["share_token"]
    assert client.post(f"/api/sessions/{share_token}/start", headers=headers).status_code == 200

    films = client.get(f"/api/onboarding/films?share_token={share_token}",
                       headers=headers).json()["films"]
    for index, film in enumerate(films):
        client.post("/api/onboarding/ratings", headers=headers, json={
            "film_id": film["id"], "reaction": "loved_it" if index % 2 else "not_for_me",
            "session_share_token": share_token,
        })
    assert client.post("/api/test/results", headers=headers, json={
        "answers": {}, "session_share_token": share_token,
    }).status_code == 201

    status = client.get(f"/api/sessions/{share_token}", headers=headers).json()
    assert len(status["members"]) == 1, "nobody to wait for, so the app skips the wait"

    # Nobody else to agree with, so one yes is unanimous.
    agreed = []
    while len(agreed) < MATCHES_WANTED:
        card = client.get(f"/api/shortlist/next?share_token={share_token}", headers=headers).json()
        assert card["state"] == "card"
        result = client.post("/api/shortlist/reactions", headers=headers, json={
            "share_token": share_token, "film_id": card["film"]["id"], "reaction": "yes",
        }).json()
        agreed.append(card["film"]["id"])
        assert result["state"] == ("shortlist" if len(agreed) == MATCHES_WANTED else "continue")

    assert [film["id"] for film in result["films"]] == agreed

    # And the compass has nobody to compare them against, which is not an error.
    companions = client.get(f"/api/profile/moral/session/{share_token}", headers=headers)
    assert companions.status_code == 200
    assert companions.json()["companions"] == []
