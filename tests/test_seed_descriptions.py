"""Curated blind-story copy and its deploy-time data migration."""
from __future__ import annotations

from dataclasses import replace

import pytest

from moral_atlas import db
from moral_atlas.config import settings
from moral_atlas.sources import seed


def isolated_store(monkeypatch, tmp_path):
    test_settings = replace(
        settings(), data_dir=tmp_path, cache_dir=tmp_path / "cache",
        db_path=tmp_path / "atlas.sqlite",
    )
    monkeypatch.setattr(db, "settings", lambda: test_settings)


def test_description_migration_updates_existing_rows_and_inserts_new_ones(
    monkeypatch, tmp_path,
):
    isolated_store(monkeypatch, tmp_path)
    db.init_db()
    db.upsert_film({
        "film_id": "legacy-lion-id", "title": "The Lion King", "year": 1994,
        "runtime": 88, "tmdb_id": 8587, "genres": ["Animation", "Drama"],
        "artwork_url": "https://example.test/lion.jpg",
        "description": "Old difficult copy.",
    })
    seed_file = tmp_path / "films.yaml"
    seed_file.write_text(
        "films:\n"
        "  - title: The Lion King\n"
        "    year: 1994\n"
        "  - title: The Matrix\n"
        "    year: 1999\n",
        encoding="utf-8",
    )

    first = seed.sync_seed_films(str(seed_file))
    assert first == {"inserted": 1, "updated": 1, "unchanged": 0}
    lion = db.get_film("legacy-lion-id")
    assert lion["description"] == seed.DESCRIPTIONS["The Lion King"]
    assert lion["runtime"] == 88, "the migration must preserve corpus metadata"
    assert lion["tmdb_id"] == 8587
    assert lion["genres"] == ["Animation", "Drama"]
    assert lion["artwork_url"] == "https://example.test/lion.jpg"
    assert db.get_film("the-matrix-1999")["description"] == seed.DESCRIPTIONS["The Matrix"]

    second = seed.sync_seed_films(str(seed_file))
    assert second == {"inserted": 0, "updated": 0, "unchanged": 2}


def test_blind_story_descriptions_stay_short():
    too_long = {
        title: len(description.split())
        for title, description in seed.DESCRIPTIONS.items()
        if len(description.split()) > 20
    }
    assert too_long == {}


def test_description_migration_refuses_to_replace_a_colliding_film(
    monkeypatch, tmp_path,
):
    isolated_store(monkeypatch, tmp_path)
    db.init_db()
    db.upsert_film({
        "film_id": "the-matrix-1999", "title": "A Different Film", "year": 2001,
        "runtime": 123, "description": "Keep me.",
    })
    seed_file = tmp_path / "films.yaml"
    seed_file.write_text(
        "films:\n  - title: The Matrix\n    year: 1999\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Refusing to replace existing film"):
        seed.sync_seed_films(str(seed_file))

    untouched = db.get_film("the-matrix-1999")
    assert untouched["title"] == "A Different Film"
    assert untouched["runtime"] == 123
    assert untouched["description"] == "Keep me."


def test_the_curated_fifty_pass_the_check_the_generated_ones_face():
    """The hand-written cards are the specification, so they must survive it.

    If a rule rejects one of these, the rule is wrong — that is the whole basis
    on which a generated card is allowed into the same pool.
    """
    from moral_atlas.llm import stages

    failures = {
        title: stages.describe_problems(description, title)
        for title, description in seed.DESCRIPTIONS.items()
        if stages.describe_problems(description, title)
    }
    assert failures == {}


def test_house_style_check_catches_what_a_model_reaches_for():
    from moral_atlas.llm import stages

    def problems(sentence, title="Some Film"):
        return " | ".join(stages.describe_problems(sentence, title))

    assert "names" in problems(
        "A young lion named Simba must return to Pride Rock and take his throne.")
    assert "title" in problems(
        "A young ruler flees his kingdom after a death he is blamed for.",
        title="A Young Ruler")
    assert "at most" in problems(
        "A young ruler flees the kingdom after a death he is blamed for, wanders "
        "far from home for years, and then must decide whether to return and "
        "take back what was taken from him.")
    assert "at least" in problems("A man makes a choice.")
    assert "more than one sentence" in problems(
        "A young ruler flees his home. He must decide whether to return and claim it.")
    assert "rates or resolves" in problems(
        "A young ruler bravely returns home and takes back the throne that is his.")
    assert "criticism vocabulary" in problems(
        "A story that explores themes of duty and inherited power in a fallen kingdom.")
    assert problems(
        "A young leader must face his past and decide whether to save the home "
        "he left behind.") == ""


def test_generated_cards_are_stamped_and_curated_ones_are_not_overwritten(
    monkeypatch, tmp_path,
):
    isolated_store(monkeypatch, tmp_path)
    db.init_db()
    db.upsert_film({"film_id": "f1", "title": "A Film", "year": 2000,
                    "description": "Hand written.", "description_source": "curated"})
    db.upsert_film({"film_id": "f1", "title": "A Film", "year": 2000, "runtime": 99})

    film = db.get_film("f1")
    assert film["description"] == "Hand written.", "a metadata refresh must not erase copy"
    assert film["description_source"] == "curated"
    assert film["runtime"] == 99

    db.set_film_description_source("f1", "generated:some-model:p2:plot")
    assert db.get_film("f1")["description_source"] == "generated:some-model:p2:plot"
