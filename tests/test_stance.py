"""Choosing a moral position, and what it does to the deck.

The position is CHOSEN rather than inferred, and the tests are mostly about the
difference between "no" and "not asked". Somebody who picks none of these has
answered; somebody who has never seen the question has not; and both have no
stance, so `stance_id` alone cannot tell them apart and the product would ask
the first person again forever.

The ranking test is the one that matters: at weight zero the deck must be
byte-identical to the deck without a stance, because the whole control is only
defensible if turning it off returns exactly what was there before.
"""
from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from moral_atlas.api import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_web_database(monkeypatch, tmp_path):
    """Never write into the developer's atlas database."""
    from moral_atlas import db
    from moral_atlas.config import settings

    test_settings = replace(
        settings(), data_dir=tmp_path, cache_dir=tmp_path / "cache",
        db_path=tmp_path / "web.sqlite",
    )
    monkeypatch.setattr(db, "settings", lambda: test_settings)
    db.init_db()
    # A session cannot be created without a deck to hand out, so the corpus has
    # to exist before the first request rather than inside the test.
    for index in range(20):
        db.upsert_film({
            "film_id": f"film-{index}", "title": f"Film {index}", "year": 2000 + index,
            "description": f"A story prompt number {index}.",
            "artwork_url": f"https://example.test/posters/film-{index}.jpg",
        })
    return db


def _user(name: str) -> dict[str, str]:
    access = client.post("/api/access", json={"name": name}).json()
    return {"X-Session-Token": access["token"]}


def test_the_catalogue_offers_three_faces_and_a_way_out(isolated_web_database):
    headers = _user("Ada")
    body = client.get("/api/profile/stance", headers=headers).json()
    # Most-affirming first, so the screen does not open on the bleakest label.
    assert [s["label"] for s in body["stances"]] == ["Traditional", "Progressive", "Cynical"]
    assert all(s["character"] and s["line"] for s in body["stances"])
    # The label is the thing somebody scans; the claim is what stops it being a
    # word they have to interpret. Neither is optional.
    assert all(s["label"] and s["line"] for s in body["stances"])
    # Never asked: no stance, and not yet answered.
    assert body["stance_id"] is None and body["answered"] is False


def test_declining_counts_as_an_answer(isolated_web_database):
    headers = _user("Ada")
    saved = client.put("/api/profile/stance",
                       json={"stance_id": None, "weight": 0.8}, headers=headers)
    assert saved.status_code == 200
    body = client.get("/api/profile/stance", headers=headers).json()
    assert body["stance_id"] is None
    assert body["answered"] is True        # asked and answered, unlike above
    assert body["weight"] == 0.0           # no position means nothing to weight


def test_a_choice_round_trips(isolated_web_database):
    headers = _user("Ada")
    client.put("/api/profile/stance",
               json={"stance_id": "order", "weight": 0.5}, headers=headers)
    body = client.get("/api/profile/stance", headers=headers).json()
    assert (body["stance_id"], body["weight"], body["answered"]) == ("order", 0.5, True)


def test_an_unknown_position_is_refused(isolated_web_database):
    headers = _user("Ada")
    bad = client.put("/api/profile/stance",
                     json={"stance_id": "sigma", "weight": 0.5}, headers=headers)
    assert bad.status_code == 400


@pytest.mark.parametrize("weight", [-0.5, 1.5])
def test_the_weight_stays_inside_its_range(isolated_web_database, weight):
    headers = _user("Ada")
    out = client.put("/api/profile/stance",
                     json={"stance_id": "ruin", "weight": weight}, headers=headers)
    assert out.status_code == 422


def test_turning_the_weight_off_changes_nothing():
    """The one invariant the whole control rests on."""
    from moral_atlas.web.shortlist_service import _blend

    for own in (-0.4, 0.0, 0.137, 2.5):
        assert _blend(own, 0.9, 0.0) == own      # off
        assert _blend(own, None, 0.7) == own     # nothing behind the position
        assert _blend(own, own, 0.7) == pytest.approx(own)   # agreeing changes nothing


def test_the_blend_moves_between_the_two_scores():
    from moral_atlas.web.shortlist_service import _blend

    assert _blend(0.0, 1.0, 0.25) == pytest.approx(0.25)
    assert _blend(0.0, 1.0, 1.0) == pytest.approx(1.0)   # all the way over
    assert _blend(1.0, 0.0, 0.5) == pytest.approx(0.5)


def test_changing_a_position_re_ranks_the_deck_without_losing_votes():
    """Saving must reach the cards, and must not deal a swiped film again.

    A session materialises its deck order once and keeps it, so the choice has
    to drop that order — and dropping it must not resurrect anything already
    judged, because votes live in a different table keyed by film rather than
    by position.
    """
    from moral_atlas import db as real_db

    headers = _user("Ada")
    share = client.post("/api/sessions", headers=headers).json()["share_token"]

    first = client.get(f"/api/shortlist/next?share_token={share}&since=0",
                       headers=headers).json()
    dealt = (first.get("queue") or [])
    assert dealt, "the deck should hand over cards to judge"
    judged = dealt[0]["id"]
    client.post("/api/shortlist/reactions",
                json={"share_token": share, "film_id": judged, "reaction": "no"},
                headers=headers)

    saved = client.put("/api/profile/stance",
                       json={"stance_id": "self", "weight": 0.6, "share_token": share},
                       headers=headers).json()
    assert saved["reordered"] is True

    with real_db.connect(read_only=True) as con:
        left = con.execute("SELECT count(*) n FROM session_shortlist_films").fetchone()["n"]
    assert left == 0, "the stored order should be gone, to be rebuilt on the next ask"

    again = client.get(f"/api/shortlist/next?share_token={share}&since=0",
                       headers=headers).json()
    ids = [film["id"] for film in (again.get("queue") or [])]
    assert judged not in ids, "a film already judged must not come back round"


def test_a_share_token_that_is_not_yours_reorders_nothing():
    headers = _user("Ada")
    intruder = _user("Sam")
    share = client.post("/api/sessions", headers=headers).json()["share_token"]
    out = client.put("/api/profile/stance",
                     json={"stance_id": "ruin", "weight": 0.5, "share_token": share},
                     headers=intruder).json()
    assert out["stance_id"] == "ruin"     # their own choice still saves
    assert out["reordered"] is False      # somebody else's deck does not move


def test_every_face_is_a_character_not_a_poster():
    """The screen asks which PERSON speaks to somebody, so it shows one.

    All three carry a character image now. The assertion is on the flag rather
    than on the URLs, so swapping a face does not break the test — but losing one
    to a poster fallback does, which is the regression worth catching.
    """
    from moral_atlas.web.stances import catalogue

    rows = {row["stance_id"]: row for row in catalogue()}
    assert all(row["shows_character"] for row in rows.values())
    # Independent of the film row: this database holds none of these films, so
    # anything falling back to a poster would have come back empty.
    assert all(row["film_title"] is None for row in rows.values())
    assert all(row["artwork_url"] for row in rows.values())


def test_the_weight_cannot_reach_the_top_of_its_range(isolated_web_database):
    """Full weight would drop the only part of the ranking that predicts enjoyment.

    The cap holds on the way in and on the way out, so a value written before it
    existed behaves the way the screen says rather than the way it was stored.
    """
    from moral_atlas.web.store import MAX_MORAL_WEIGHT, moral_stance, save_moral_stance

    headers = _user("Ada")
    body = client.put("/api/profile/stance",
                      json={"stance_id": "ruin", "weight": 1.0}, headers=headers).json()
    assert body["weight"] == MAX_MORAL_WEIGHT

    # A row written directly, as an older build would have left it.
    from moral_atlas import db as real_db
    user_id = client.get("/api/access/me", headers=headers).json()["id"]
    with real_db.connect() as con:
        con.execute("UPDATE users SET moral_weight=1.0 WHERE user_id=?", [user_id])
    assert moral_stance(user_id)[1] == MAX_MORAL_WEIGHT
