"""Tests for scoring a viewer on the derived moral axes.

Two things need proving and they are quite different. The arithmetic is tested
on films whose stance is known by construction — an axis a film affirms on every
item, an axis it is split on — because the whole value of the score is that its
sign and its confidence mean what they say. The API tests then prove the
preferences a real session captures actually reach that arithmetic, which is
where the interesting wiring lives: the blind answers name pairs, not films, and
only the session's deck can turn one into the other.
"""
from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from moral_atlas.analysis import user_scores as us
from moral_atlas.web.app import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def never_touch_the_real_store(monkeypatch, tmp_path):
    """No test in this module may open the developer's actual atlas.

    Most tests here take a fixture that redirects the store, but not all:
    `test_moral_profile_needs_a_session` calls an endpoint with no fixture at
    all, and the session dependency opens the store to look the caller up. That
    created data/atlas.sqlite in the working tree. A store that exists only
    because the tests ran is a store that makes the next run behave differently
    from a fresh checkout — which is exactly how a real failure stays hidden
    locally and only shows up in CI.
    """
    from moral_atlas import db
    from moral_atlas.config import settings

    monkeypatch.setattr(db, "settings", lambda: replace(
        settings(), data_dir=tmp_path, cache_dir=tmp_path / "cache",
        db_path=tmp_path / "isolated.sqlite"))


# Two axes, and three films positioned on them by hand.
DIMENSIONS = [
    {"dim_id": 1, "name": "Payback or Mercy", "question": "Retribution or restraint?",
     "pole_high": "Wrongs demand an answer.", "pole_low": "Mercy is the higher response."},
    {"dim_id": 2, "name": "Telling or Sparing", "question": "Expose or conceal?",
     "pole_high": "Truth must be told.", "pole_low": "Concealment can be kindness."},
]


def stances(**films):
    return {film: {int(dim): list(values) for dim, values in axes.items()}
            for film, axes in films.items()}


# --------------------------------------------------------------------------
# The arithmetic
# --------------------------------------------------------------------------

def test_loving_a_film_moves_you_toward_what_it_asserts():
    film = stances(vengeance={1: [1.0] * 12})
    [payback, telling] = us.score_preferences(
        [us.Preference("vengeance", 1.0, "rating", "loved_it")], DIMENSIONS, film)
    assert payback.leaning == "high"
    assert payback.score == pytest.approx(12 / (12 + us.PRIOR_ITEMS), abs=1e-4)
    assert payback.stance == DIMENSIONS[0]["pole_high"]
    # An axis the film never engaged is reported, and reported as unknown.
    assert (telling.score, telling.evidence_items, telling.confidence) == (0.0, 0.0, 0.0)


def test_rejecting_a_film_moves_you_away_from_it():
    film = stances(vengeance={1: [1.0] * 12})
    [payback, _] = us.score_preferences(
        [us.Preference("vengeance", -1.0, "rating", "not_for_me")], DIMENSIONS, film)
    assert payback.leaning == "low"
    assert payback.score == pytest.approx(-12 / (12 + us.PRIOR_ITEMS), abs=1e-4)
    assert payback.stance == DIMENSIONS[0]["pole_low"]


def test_thin_evidence_is_shrunk_toward_the_middle():
    """Two unanimous items are not a conviction, and must not score like one."""
    thin = stances(sketch={1: [1.0, 1.0]})
    thick = stances(epic={1: [1.0] * 40})
    [thin_score, _] = us.score_preferences(
        [us.Preference("sketch", 1.0, "rating", "loved_it")], DIMENSIONS, thin)
    [thick_score, _] = us.score_preferences(
        [us.Preference("epic", 1.0, "rating", "loved_it")], DIMENSIONS, thick)
    assert thin_score.score < 0.25 < thick_score.score
    assert thin_score.confidence < 0.25 < thick_score.confidence
    assert thick_score.score < 1.0  # the prior never fully lets go


def test_a_film_split_on_an_axis_leaves_you_balanced():
    split = stances(argument={1: [1.0, -1.0, 1.0, -1.0, 1.0, -1.0]})
    [payback, _] = us.score_preferences(
        [us.Preference("argument", 1.0, "rating", "loved_it")], DIMENSIONS, split)
    assert payback.leaning == "balanced"
    assert payback.score == pytest.approx(0.0)
    # Balanced is not ignorance: the evidence was there and it cancelled.
    assert payback.evidence_items == 6.0
    assert payback.stance == us.BALANCED_STANCE


def test_films_you_have_not_seen_say_nothing_about_your_morals():
    film = stances(vengeance={1: [1.0] * 12})
    prefs = us.rating_preferences([("vengeance", "havent_seen")])
    assert prefs == []
    [payback, _] = us.score_preferences(prefs, DIMENSIONS, film)
    assert payback.evidence_items == 0.0


def test_only_the_latest_reaction_to_a_film_counts():
    """Ratings arrive newest first, and a person who changed their mind meant it."""
    prefs = us.rating_preferences([("vengeance", "not_for_me"), ("vengeance", "loved_it")])
    assert prefs == [us.Preference("vengeance", -1.0, "rating", "not_for_me")]


def test_a_blind_pair_pulls_toward_the_chosen_story_and_away_from_the_other():
    both = stances(chosen={1: [1.0] * 10}, rejected={1: [-1.0] * 10})
    prefs = us.pair_preferences("a", ["chosen", "rejected"], "pair-1")
    [payback, _] = us.score_preferences(prefs, DIMENSIONS, both)
    # Both halves point the same way once the rejected film's sign is flipped.
    assert payback.leaning == "high"
    assert payback.score == pytest.approx(10 / (10 + us.PRIOR_ITEMS), abs=1e-4)


def test_neither_is_an_answer_that_moves_nothing():
    both = stances(a={1: [1.0] * 10}, b={1: [-1.0] * 10})
    assert us.pair_preferences("neither", ["a", "b"]) == []
    [payback, _] = us.score_preferences([], DIMENSIONS, both)
    assert payback.evidence_items == 0.0


def test_a_pair_weighs_half_of_a_rating_on_each_side():
    """One contrast should not outweigh one wholehearted opinion."""
    film = stances(chosen={1: [1.0] * 10}, rejected={1: [1.0] * 10})
    pair = us.score_preferences(
        us.pair_preferences("a", ["chosen", "rejected"]), DIMENSIONS, film)[0]
    rating = us.score_preferences(
        [us.Preference("chosen", 1.0, "rating", "loved_it")], DIMENSIONS, film)[0]
    # The pair's two halves cancel here — both films assert the same thing — so
    # its total mass, not its net, is what to compare: 10 items either way.
    assert pair.evidence_items == rating.evidence_items == 10.0
    assert pair.score == pytest.approx(0.0)


# --------------------------------------------------------------------------
# Reading the scores off a real session
# --------------------------------------------------------------------------

@pytest.fixture
def scored_atlas(monkeypatch, tmp_path):
    """A web database that also carries an atlas: axes, a bank and film scores.

    Every film affirms axis 1 and denies axis 2, or the reverse, decided by the
    parity of its index — so a viewer's expected direction is known before the
    scorer runs.
    """
    from moral_atlas import db
    from moral_atlas.config import settings

    test_settings = replace(
        settings(), data_dir=tmp_path, cache_dir=tmp_path / "cache",
        db_path=tmp_path / "web.sqlite",
    )
    monkeypatch.setattr(db, "settings", lambda: test_settings)
    db.init_db()

    with db.connect() as con:
        for dimension in DIMENSIONS:
            con.execute(
                "INSERT INTO dimensions (dim_version, dim_id, name, question, pole_high, "
                "pole_low, n_dims, source, created_at) VALUES ('d1',?,?,?,?,?,2,'test',?)",
                [dimension["dim_id"], dimension["name"], dimension["question"],
                 dimension["pole_high"], dimension["pole_low"], db.now()],
            )
        for item in range(20):
            dim_id = 1 if item < 10 else 2
            con.execute(
                "INSERT INTO item_bank (item_id, bank_version, text, cluster_id, active) "
                "VALUES (?, 'b1', ?, ?, 1)", [f"I{item}", f"proposition {item}", item],
            )
            con.execute(
                "INSERT INTO item_dimensions (dim_version, bank_version, item_id, dim_id, "
                "polarity, fit, pass_name, created_at) VALUES ('d1','b1',?,?,1,0.9,'main',?)",
                [f"I{item}", dim_id, db.now()],
            )

    for index in range(20):
        db.upsert_film({
            "film_id": f"film-{index}", "title": f"Film {index}", "year": 2000 + index,
            "description": f"A spoiler-free story prompt number {index}.",
            # The named cards carry a poster, so the deck now requires five
            # eligible films to have one before it will deal a session.
            "artwork_url": f"https://example.invalid/{index}.jpg",
        })
    with db.connect() as con:
        for index in range(20):
            high_on_payback = index % 2 == 0
            for item in range(20):
                on_payback = item < 10
                con.execute(
                    "INSERT INTO scores (film_id, item_id, bank_version, variant, run_id, "
                    "value, confidence) VALUES (?,?, 'b1', 'spine', 'run-test', ?, 0.9)",
                    [f"film-{index}", f"I{item}",
                     1 if on_payback == high_on_payback else -1],
                )

        # The product reads DISCOVERED factors, not the LLM-derived dimension
        # set, so the same structure is mirrored into the tables it actually
        # queries: two factors over the same items, and the same verdicts under
        # the scorer the product is configured to read.
        for factor, dimension in ((1, DIMENSIONS[0]), (2, DIMENSIONS[1])):
            con.execute(
                "INSERT INTO latent_factors (scorer, variant, bank_version, factor_id, "
                "name, question, pole_high, pole_low, n_items, created_at) "
                "VALUES ('deepseek','subs','deepseek-subs',?,?,?,?,?,10,?)",
                [factor, dimension["name"], dimension["question"],
                 dimension["pole_high"], dimension["pole_low"], db.now()],
            )
        for item in range(20):
            con.execute(
                "INSERT INTO latent_factor_items (scorer, variant, bank_version, "
                "item_id, factor_id) VALUES ('deepseek','subs','deepseek-subs',?,?)",
                [f"I{item}", 1 if item < 10 else 2],
            )
        for index in range(20):
            high_on_payback = index % 2 == 0
            for item in range(20):
                on_payback = item < 10
                con.execute(
                    "INSERT INTO model_verdicts (scorer, model, film_id, item_id, "
                    "bank_version, variant, run_id, value, confidence, created_at) "
                    "VALUES ('deepseek','deepseek-chat',?,?,'deepseek-subs','subs','r',?,0.9,?)",
                    [f"film-{index}", f"I{item}",
                     1 if on_payback == high_on_payback else -1, db.now()],
                )
    return db


def _start_session(name: str = "Ada"):
    access = client.post("/api/access", json={"name": name}).json()
    headers = {"X-Session-Token": access["token"]}
    share_token = client.post("/api/sessions", headers=headers).json()["share_token"]
    return headers, share_token


def test_moral_profile_needs_a_session():
    assert client.get("/api/profile/moral").status_code == 401


def test_moral_profile_is_empty_but_complete_before_anyone_answers(scored_atlas):
    headers, _ = _start_session()
    profile = client.get("/api/profile/moral", headers=headers)
    assert profile.status_code == 200
    body = profile.json()
    assert [score["name"] for score in body["scores"]] == [d["name"] for d in DIMENSIONS]
    assert all(score["score"] == 0 and score["confidence"] == 0 for score in body["scores"])
    assert body["is_provisional"] is True
    assert body["evidence"] == {"films_rated": 0, "films_not_seen": 0, "pairs_answered": 0,
                                "films_used": 0, "films_without_scores": []}


def test_rated_films_score_the_user_on_every_axis(scored_atlas):
    headers, share_token = _start_session()
    films = client.get(f"/api/onboarding/films?share_token={share_token}",
                       headers=headers).json()["films"]
    for film in films:
        client.post("/api/onboarding/ratings", headers=headers, json={
            "film_id": film["id"],
            # Films with an even index affirm axis 1; love exactly those.
            "reaction": "loved_it" if int(film["id"].split("-")[1]) % 2 == 0 else "not_for_me",
            "session_share_token": share_token,
        })

    body = client.get("/api/profile/moral", headers=headers).json()
    payback, telling = body["scores"]
    assert payback["leaning"] == "high" and payback["score"] > 0
    assert telling["leaning"] == "low" and telling["score"] < 0
    assert payback["films"] == len(films)
    assert body["evidence"]["films_rated"] == len(films)
    assert body["evidence"]["films_used"] == len(films)
    assert body["is_provisional"] is False
    # The reading quotes the axis they committed to hardest, in its own words.
    strongest = max(body["scores"], key=lambda score: abs(score["score"]))
    assert body["summary"] == f"{strongest['name']} — {strongest['stance']}"


def test_unseen_films_are_counted_but_do_not_score(scored_atlas):
    headers, share_token = _start_session()
    films = client.get(f"/api/onboarding/films?share_token={share_token}",
                       headers=headers).json()["films"]
    for film in films:
        client.post("/api/onboarding/ratings", headers=headers, json={
            "film_id": film["id"], "reaction": "havent_seen",
            "session_share_token": share_token,
        })

    body = client.get("/api/profile/moral", headers=headers).json()
    assert body["evidence"] == {"films_rated": 0, "films_not_seen": len(films),
                                "pairs_answered": 0, "films_used": 0,
                                "films_without_scores": []}
    assert all(score["evidence_items"] == 0 for score in body["scores"])


def test_blind_pair_answers_are_traced_back_to_their_films(scored_atlas, monkeypatch):
    """The answers only say "pair-2"; the session's deck says which films that was."""
    # A real deck is fifteen films sampled at random, so it can deal a pair of
    # two odd-indexed films — and then neither answer to that pair affirms
    # axis 1, the leaning lands on "balanced", and this fails. Measured at one
    # run in two hundred, which is often enough to redden main and rare enough
    # to look like someone else's problem.
    #
    # What is under test is the tracing, not the sampling, so deal a fixed
    # deck: every pair holds exactly one even-indexed film, and the orientation
    # alternates so the choice below still exercises both branches.
    from moral_atlas.web import store as store_mod
    monkeypatch.setattr(store_mod, "build_session_deck", lambda: {
        "direct": [f"film-{index}" for index in range(10, 15)],
        "pairs": [["film-0", "film-1"], ["film-3", "film-2"], ["film-4", "film-5"],
                  ["film-7", "film-6"], ["film-8", "film-9"]],
    })
    headers, share_token = _start_session()
    questions = client.get(f"/api/test/questions?share_token={share_token}",
                           headers=headers).json()["questions"]
    with scored_atlas.connect(read_only=True) as con:
        deck = con.execute("SELECT deck_json FROM group_sessions WHERE share_token=?",
                           [share_token]).fetchone()["deck_json"]
    import json
    pairs = json.loads(deck)["pairs"]

    # Always pick whichever side is an even-indexed film: those affirm axis 1.
    answers = {f"pair-{index}": ("a" if int(film_ids[0].split("-")[1]) % 2 == 0 else "b")
               for index, film_ids in enumerate(pairs, start=1)}
    assert len(answers) == len(questions)
    saved = client.post("/api/test/results", headers=headers,
                        json={"answers": answers, "session_share_token": share_token})
    assert saved.status_code == 201

    body = client.get("/api/profile/moral", headers=headers).json()
    payback, telling = body["scores"]
    assert body["evidence"]["pairs_answered"] == len(pairs)
    assert body["evidence"]["films_used"] == 2 * len(pairs)
    assert payback["leaning"] == "high"
    assert telling["leaning"] == "low"


def test_the_profile_reports_which_model_read_the_films(scored_atlas):
    """There is no dimension-set parameter any more: the axes are whichever the
    configured scorer discovered, so the response says who that was instead of
    echoing a version the caller asked for."""
    headers, _ = _start_session()
    body = client.get("/api/profile/moral", headers=headers).json()
    assert body["dim_version"] == "deepseek"
    assert body["bank_version"] == "deepseek-subs"
    assert [score["name"] for score in body["scores"]] == [d["name"] for d in DIMENSIONS]


# --------------------------------------------------------------------------
# Ranking tonight's shortlist
# --------------------------------------------------------------------------

def _rate(user_id, index, reaction):
    from moral_atlas.web.store import save_movie_rating
    save_movie_rating(user_id, f"film-{index}", reaction)


def _new_user(name):
    from moral_atlas.web.store import create_session
    return create_session(name).user.id


def test_the_deck_is_ranked_by_what_the_viewer_believes(scored_atlas):
    """Even-index films affirm axis 1; someone who loves one should get more."""
    from moral_atlas.web.shortlist_service import ranked_shortlist

    viewer = _new_user("Ada")
    _rate(viewer, 0, "loved_it")          # film-0 affirms axis 1
    deck = ranked_shortlist([viewer], limit=6, variation=0)

    assert deck, "a scored viewer should get a deck"
    assert all(int(film["id"].split("-")[1]) % 2 == 0 for film in deck[:3]), \
        "films arguing what she believes should come first"
    assert deck == sorted(deck, key=lambda f: -f["agreement"])
    assert deck[0]["agreement"] > 0


def test_films_you_have_already_seen_are_not_on_tonights_list(scored_atlas):
    from moral_atlas.web.shortlist_service import ranked_shortlist

    viewer = _new_user("Ada")
    _rate(viewer, 0, "loved_it")
    _rate(viewer, 2, "not_for_me")
    _rate(viewer, 4, "havent_seen")
    ids = {film["id"] for film in ranked_shortlist([viewer], limit=20, variation=0)}

    assert "film-0" not in ids, "already seen and loved"
    assert "film-2" not in ids, "already seen and rejected"
    assert "film-4" in ids, "not having seen it is a qualification, not a bar"


def test_two_people_are_ranked_by_whoever_likes_the_film_least(scored_atlas):
    """The film one adores and the other cannot stand must not win on average."""
    from moral_atlas.web.shortlist_service import ranked_shortlist

    ada, bob = _new_user("Ada"), _new_user("Bob")
    _rate(ada, 0, "loved_it")             # Ada leans toward axis 1's high pole
    _rate(bob, 1, "loved_it")             # Bob leans the opposite way on both axes

    together = ranked_shortlist([ada, bob], limit=20, variation=0)
    alone = {film["id"]: film["agreement"] for film in ranked_shortlist([ada], limit=20, variation=0)}

    assert max(alone.values()) > together[0]["agreement"], \
        "adding someone who disagrees cannot improve the best match"
    for film in together:
        # `agreement` is the worst view of the film, so it can never flatter a
        # film by averaging away the person who dislikes it.
        assert film["agreement"] <= alone[film["id"]] + 1e-9


def test_the_shortlist_endpoint_ranks_for_everyone_in_the_session(scored_atlas):
    headers, share_token = _start_session()
    response = client.get(f"/api/shortlist/films?share_token={share_token}", headers=headers)
    assert response.status_code == 200
    films = response.json()["films"]
    assert films and all({"id", "title", "agreement"} <= set(film) for film in films)
    assert films == sorted(films, key=lambda f: -f["agreement"])


def test_the_shortlist_is_not_readable_from_outside_the_session(scored_atlas):
    _headers, share_token = _start_session("Ada")
    outsider = client.post("/api/access", json={"name": "Mallory"}).json()
    response = client.get(
        f"/api/shortlist/films?share_token={share_token}",
        headers={"X-Session-Token": outsider["token"]},
    )
    assert response.status_code == 404


def test_default_profile_falls_back_when_the_shared_map_has_not_been_derived(monkeypatch, tmp_path):
    from moral_atlas import db
    from moral_atlas.config import settings

    test_settings = replace(
        settings(), data_dir=tmp_path, cache_dir=tmp_path / "cache",
        db_path=tmp_path / "web.sqlite",
    )
    monkeypatch.setattr(db, "settings", lambda: test_settings)
    db.init_db()
    for index in range(15):
        # A description is what makes a film deck-eligible now that the research
        # corpus is far larger than the curated one, and this test needs a session.
        db.upsert_film({"film_id": f"film-{index}", "title": f"Film {index}",
                        "description": f"A spoiler-free story prompt number {index}.",
                        "artwork_url": f"https://example.invalid/{index}.jpg"})
    headers, _ = _start_session()
    response = client.get("/api/profile/moral", headers=headers)
    assert response.status_code == 200
    assert response.json()["scores"] == []
    assert response.json()["is_provisional"] is True


def test_the_deck_varies_between_runs_without_recommending_a_worse_film(scored_atlas):
    """Same two people, same beliefs — a different film out front, but a fitting one.

    The point of sampling the order rather than sorting it is that a product
    which answers "what should we watch" with the identical film every time is
    doing arithmetic at someone rather than recommending to them. What it must
    not do is trade that variety for a film the room actually disagrees with, so
    this asserts both halves: the leader moves, and every leader it produces is
    near the top of the honest ranking.
    """
    from moral_atlas.web.shortlist_service import ranked_shortlist

    viewer = _new_user("Ada")
    _rate(viewer, 0, "loved_it")

    ordered = ranked_shortlist([viewer], limit=None, variation=0)
    best = ordered[0]["agreement"]
    agreement_of = {film["id"]: film["agreement"] for film in ordered}

    leaders = {ranked_shortlist([viewer], limit=1)[0]["id"] for _ in range(40)}

    assert len(leaders) > 1, "40 runs that all lead with the same film is not variation"
    for film_id in leaders:
        assert best - agreement_of[film_id] <= 0.25, (
            f"{film_id} led the deck at {agreement_of[film_id]:.3f} against a best of "
            f"{best:.3f} — that is a worse film, not a different equally good one")


def test_variation_can_be_switched_off(scored_atlas):
    """The ranking underneath stays deterministic, so it can still be reasoned about."""
    from moral_atlas.web.shortlist_service import ranked_shortlist

    viewer = _new_user("Ada")
    _rate(viewer, 0, "loved_it")
    runs = [[film["id"] for film in ranked_shortlist([viewer], limit=8, variation=0)]
            for _ in range(5)]
    assert all(run == runs[0] for run in runs)
