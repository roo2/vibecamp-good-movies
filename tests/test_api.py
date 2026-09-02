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


def test_keep_looking_deals_more_cards_instead_of_the_same_shortlist(isolated_web_database):
    """"Keep looking" was a dead end that hung the screen.

    A full shortlist ended the deck, so a person who closed it and asked for
    another card got the same three films back — and the screen, waiting for a
    card it would never be given, sat on "Finding films for you…" forever.
    Telling the server what you have already seen turns that terminal state into
    a threshold.
    """
    from moral_atlas.web.store import MATCHES_WANTED

    me = client.post("/api/access", json={}).json()
    headers = {"X-Session-Token": me["token"]}
    share_token = client.post("/api/sessions", headers=headers).json()["share_token"]
    client.post(f"/api/sessions/{share_token}/start", headers=headers)

    for _ in range(MATCHES_WANTED):
        card = client.get(f"/api/shortlist/next?share_token={share_token}", headers=headers).json()
        assert card["state"] == "card"
        client.post("/api/shortlist/reactions", headers=headers, json={
            "share_token": share_token, "film_id": card["film"]["id"], "reaction": "yes",
        })

    # Asking with no `since` still ends the deck, which is what fills the screen
    # the first time the shortlist completes.
    closed = client.get(f"/api/shortlist/next?share_token={share_token}", headers=headers).json()
    assert closed["state"] == "shortlist"
    assert len(closed["films"]) == MATCHES_WANTED

    # Having seen those three, the deck carries on rather than repeating itself.
    resumed = client.get(
        f"/api/shortlist/next?share_token={share_token}&since={MATCHES_WANTED}",
        headers=headers).json()
    assert resumed["state"] == "card", "keep looking must deal a card, not the shortlist again"
    assert resumed["film"]["id"] not in {film["id"] for film in closed["films"]}

    # And a fourth agreement is what ends it the second time.
    client.post("/api/shortlist/reactions", headers=headers, json={
        "share_token": share_token, "film_id": resumed["film"]["id"], "reaction": "yes",
    })
    grown = client.get(
        f"/api/shortlist/next?share_token={share_token}&since={MATCHES_WANTED}",
        headers=headers).json()
    assert grown["state"] == "shortlist"
    assert len(grown["films"]) == MATCHES_WANTED + 1


def test_the_deck_leans_recent_without_erasing_old_films(isolated_web_database):
    """Old films are pushed down, not made impossible.

    Two people said the films felt old and that they had not seen enough of the
    old ones to judge them — which makes an old card a wasted question rather
    than a matter of taste. So this builds a corpus split evenly between old and
    modern, deals many decks, and checks the lean is real without being a bar:
    an old film someone HAS seen is one of the more informative answers there is.
    """
    from moral_atlas.web.film_service import build_session_deck, DIRECT_CARDS, _recency

    assert _recency({"year": 1960}) == 0.0
    assert _recency({"year": 2019}) == 1.0
    assert 0 < _recency({"year": 2000}) < 1, "the ramp between is a ramp, not a cliff"

    # Half before 1990, half after 2005, and three times the size of a deck so
    # the draw is a choice rather than everything there is.
    for index in range(30):
        for era, year in (("old", 1955 + index), ("new", 2006 + index % 15)):
            isolated_web_database.upsert_film({
                "film_id": f"{era}-{index}", "title": f"{era.title()} {index}", "year": year,
                "artwork_url": f"https://example.test/{era}-{index}.jpg",
            })

    drawn = [isolated_web_database.get_film(film_id)["year"]
             for _ in range(40) for film_id in build_session_deck()["direct"]]
    assert len(drawn) == 40 * DIRECT_CARDS
    modern = sum(1 for year in drawn if year >= 2000) / len(drawn)
    assert modern > 0.8, f"only {modern:.0%} of dealt cards were from 2000 on"
    assert any(year < 1990 for year in drawn), "an old film should still turn up sometimes"


def test_a_factors_name_and_its_propositions_come_from_the_same_reading(isolated_web_database):
    """Names live in the database; the groups under them are recomputed on demand.

    If those two disagree about how to read the responses — one keeping silence
    as a value, the other excluding it — every axis gets its name from one
    clustering and its evidence from another. That looks exactly like a
    mislabelled axis, and nothing raises. So the reading is recorded with the
    rows, and whoever recomputes has to ask.
    """
    from moral_atlas.analysis import factor_names

    assert factor_names.estimator_for("nobody", "subs", "nothing") == "dense", (
        "an unnamed scorer must default to the reading the product has always used")

    with isolated_web_database.connect() as con:
        con.execute(
            "INSERT INTO latent_factors (scorer, variant, bank_version, factor_id, name, "
            "estimator) VALUES ('m', 'subs', 'b', 0, 'an axis', 'strict')")
    assert factor_names.estimator_for("m", "subs", "b") == "strict"

    with isolated_web_database.connect() as con:
        con.execute("UPDATE latent_factors SET estimator=NULL WHERE scorer='m'")
    assert factor_names.estimator_for("m", "subs", "b") == "dense", (
        "rows written before the column existed were all produced densely")


def _reading(db, bank, scorer="deepseek"):
    """One verdict and one named factor, the minimum for a listed reading."""
    with db.connect() as con:
        con.execute(
            "INSERT INTO model_verdicts (scorer, model, film_id, item_id, bank_version, "
            "variant, value) VALUES (?,?,?,?,?,?,?)",
            [scorer, "m", "film-0", "I001", bank, "subs", 1])
        con.execute(
            "INSERT INTO latent_factors (scorer, variant, bank_version, factor_id, name, "
            "n_items, eigenvalue, margin) VALUES (?,?,?,?,?,?,?,?)",
            [scorer, "subs", bank, 0, "An axis", 5, 2.0, 0.5])


def test_a_pooled_bank_names_both_authors_rather_than_itself(isolated_web_database):
    """The picker reads "who wrote the questions -> who answered them", and the
    writer is taken from the bank name. That holds only while a bank has one
    author: a bank pooling two models' propositions would answer "pooled",
    which names the bank instead of the authors."""
    from moral_atlas.web.routes import factors

    db = isolated_web_database
    _reading(db, "pooled-subs")
    _reading(db, "dolphin-subs")

    wrote = {m["bank_version"]: m["wrote"] for m in factors.list_models()["models"]}
    assert wrote["pooled-subs"] == "dolphin + deepseek"
    # A single-author bank must keep reporting its own author, or the mapping
    # has been applied too widely.
    assert wrote["dolphin-subs"] == "dolphin"


def test_taste_dimensions_are_empty_rather_than_broken_before_derivation(isolated_web_database):
    """The atlas hides the section when nothing has been derived. A database
    built before these tables existed must still serve the page."""
    from moral_atlas.web.routes import factors

    body = factors.get_taste_dimensions()
    assert body == {"dimensions": [], "films": [], "findings": {}}


def test_a_taste_dimension_carries_the_evidence_that_named_it(isolated_web_database):
    """Three of the real dimensions have no name, because 1,128 tags could not
    characterise them. `status` and `evidence` travel with every row so the page
    can tell "we know what this is" from "this is real and we do not"."""
    from moral_atlas.web.routes import factors

    db = isolated_web_database
    with db.connect() as con:
        con.execute(
            "INSERT INTO taste_dimensions (dim_id, pole_high, pole_low, variance, "
            "replication, evidence, tags_high, tags_low, status) "
            "VALUES (1,'Enjoyable trash','Acclaimed craft',0.234,1.0,0.73,"
            "'[\"predictable\"]','[\"masterpiece\"]','named')")
        con.execute(
            "INSERT INTO taste_dimensions (dim_id, variance, replication, evidence, status) "
            "VALUES (14,0.026,0.93,0.21,'unnamed')")
        con.execute("INSERT INTO film_taste VALUES ('film-0', 1, 55.67)")

    body = factors.get_taste_dimensions()
    named, unnamed = body["dimensions"][0], body["dimensions"][1]
    assert named["pole_high"] == "Enjoyable trash"
    assert named["tags_high"] == ["predictable"], "tag evidence should arrive parsed"
    assert unnamed["pole_high"] is None and unnamed["status"] == "unnamed"
    # Ordered by how much variation each accounts for, largest first.
    assert named["variance"] > unnamed["variance"]
    assert body["films"][0]["position"] == {"1": 55.67}


def test_the_atlas_opens_on_the_reading_the_product_uses(isolated_web_database):
    """It used to open on whichever reading had the most verdicts — a fact about
    how much scoring has been done, not about which answer is in use — so the
    atlas and the recommender disagreed by default."""
    from moral_atlas.config import settings
    from moral_atlas.web.routes import factors

    db = isolated_web_database
    s = settings()
    _reading(db, "some-other-bank", scorer=s.product_scorer)
    _reading(db, s.factor_bank, scorer=s.product_scorer)

    flagged = [m for m in factors.list_models()["models"] if m["product"]]
    assert [m["bank_version"] for m in flagged] == [s.factor_bank]


def test_a_position_carries_its_taste_free_value_beside_the_raw_one(isolated_web_database):
    """Both travel together. The adjusted number is what the atlas plots, and
    the raw one has to stay beside it or the page cannot show what adjusting
    did — which is most of the argument for adjusting."""
    from moral_atlas.analysis import factor_detail

    db = isolated_web_database
    with db.connect() as con:
        con.execute(
            "INSERT INTO film_moral_adjusted (scorer, variant, bank_version, film_id, "
            "dim_id, score, taste_explained) VALUES ('m','subs','b','film-0',0,0.472,0.194)")

    adjusted, explained = factor_detail._taste_adjusted("m", "b", "subs")
    assert adjusted[("film-0", 0)] == 0.472
    assert explained[0] == 0.194


def test_a_reading_with_no_taste_coverage_still_serves(isolated_web_database):
    """Only some readings have films in the taste corpus. The rest must fall
    back to their raw positions rather than losing their distributions."""
    from moral_atlas.analysis import factor_detail

    assert factor_detail._taste_adjusted("nobody", "nothing", "subs") == ({}, {})


def test_quoted_figures_come_from_the_database_with_their_provenance(isolated_web_database):
    """These were string literals in the components. A number that changed could
    go on being asserted by the page with nothing to show it had."""
    from moral_atlas.web.routes import factors

    db = isolated_web_database
    with db.connect() as con:
        con.execute(
            "INSERT INTO findings (key, value, display, note, source, measured_at) "
            "VALUES ('ml_raters', 162265, '162,265', 'outside raters', 'MovieLens', '2026-09-01')")

    found = factors.get_taste_dimensions()["findings"]["ml_raters"]
    assert found["display"] == "162,265"
    # Provenance travels with the number, or it cannot be checked.
    assert found["source"] and found["measured_at"]


def test_a_film_in_the_app_is_shown_on_the_product_axes_only(monkeypatch):
    """The atlas route this delegates to returns every named axis, because
    auditing the corpus is what that page is for. A person meeting a film in the
    app is not auditing anything, so it is cut to the axes the product reads."""
    from moral_atlas.analysis import user_scores
    from moral_atlas.web.routes import factors

    full = {"factors": [{"factor_id": i, "name": f"axis {i}"} for i in range(5)],
            "film_id": "f", "title": "A film"}
    monkeypatch.setattr(factors, "film_on_factors", lambda *a, **k: full)
    monkeypatch.setattr(user_scores, "factor_axes",
                        lambda *a, **k: [{"dim_id": 0}, {"dim_id": 1}])

    payload = factors.product_film_axes("f")
    assert [f["factor_id"] for f in payload["factors"]] == [0, 1]
    # Everything else about the film survives the cut.
    assert payload["title"] == "A film"


def test_a_film_is_shown_on_the_same_axes_as_the_compass(monkeypatch):
    """The film reading must not disagree with the compass about the axes.

    This route used to take the first PRODUCT_AXES of a payload ordered by
    MARGIN, while the compass asked `factor_axes`, which additionally puts axes
    that can place a person ahead of ones that cannot. The moment that gate
    arrived the two disagreed: the compass moved to "Authority vs Autonomy"
    while every film reading and the scatter plot went on showing "Intrinsic vs
    Utilitarian" — an axis that places nobody above noise. Nothing failed, and
    the two screens simply contradicted each other about what the axes are.
    """
    from moral_atlas.analysis import user_scores
    from moral_atlas.web.routes import factors

    # Margin order puts 1 second; the gate demotes it below 2.
    full = {"factors": [{"factor_id": i, "name": f"axis {i}"} for i in range(4)],
            "film_id": "f", "title": "A film"}
    monkeypatch.setattr(factors, "film_on_factors", lambda *a, **k: full)
    monkeypatch.setattr(user_scores, "factor_axes",
                        lambda *a, **k: [{"dim_id": 0}, {"dim_id": 2}])

    shown = [f["factor_id"] for f in factors.product_film_axes("f")["factors"]]
    assert shown == [0, 2], "the film must follow the compass, not raw margin"


def test_a_film_reading_survives_axes_missing_from_its_payload(monkeypatch):
    """A film engaging none of an axis's propositions has no entry for it.

    Selecting by dim_id must skip such an axis rather than raise, or one film
    with thin coverage takes down the route for every reader.
    """
    from moral_atlas.analysis import user_scores
    from moral_atlas.web.routes import factors

    full = {"factors": [{"factor_id": 0, "name": "axis 0"}], "film_id": "f",
            "title": "A film"}
    monkeypatch.setattr(factors, "film_on_factors", lambda *a, **k: full)
    monkeypatch.setattr(user_scores, "factor_axes",
                        lambda *a, **k: [{"dim_id": 0}, {"dim_id": 2}])

    assert [f["factor_id"] for f in
            factors.product_film_axes("f")["factors"]] == [0]


def test_a_stale_adjusted_null_test_is_withheld_rather_than_drawn(isolated_web_database):
    """Two hundred permutations over a residualised matrix is too slow for a
    page load, so the answer is stored — and anything stored can go stale. A
    chart drawn from a row whose corpus has moved asserts a result nothing
    produced any more, with nothing on screen to say so. It is withheld until
    `atlas taste-null` runs again."""
    from moral_atlas.analysis import taste_null

    db = isolated_web_database
    current = taste_null.fingerprint("m", "subs", "b")
    row = ["m", "subs", "b", 543, "[13.1]", "[4.4]", "[16.0]", "[4.4]"]
    with db.connect() as con:
        con.execute(
            "INSERT INTO null_test_adjusted (scorer, variant, bank_version, films, "
            "eigenvalues, thresholds, control_eigen, control_thresh, source_fingerprint) "
            "VALUES (?,?,?,?,?,?,?,?,?)", [*row, current])

    assert taste_null.load("m", "subs", "b")["films"] == 543

    with db.connect() as con:
        con.execute("UPDATE null_test_adjusted SET source_fingerprint='moved'")
    assert taste_null.load("m", "subs", "b") is None, "a stale row must not be served"


def test_the_fingerprint_moves_when_the_taste_placements_do(isolated_web_database):
    """Residuals are computed from the taste placements, so a changed placement
    means a different test — and the stored answer has to know that."""
    from moral_atlas.analysis import taste_null

    db = isolated_web_database
    before = taste_null.fingerprint("m", "subs", "b")
    with db.connect() as con:
        con.execute("INSERT INTO film_taste VALUES ('film-0', 1, 0.5)")
    assert taste_null.fingerprint("m", "subs", "b") != before
