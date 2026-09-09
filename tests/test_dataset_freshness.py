"""Tests for noticing that the published snapshot has gone stale.

The atlas page serves a committed file on the published site, so "somebody
forgot to rebuild it" is a silent error that can be arbitrarily large — the page
looks fine and reports numbers from whenever it was last built. These tests
cover the two ways that goes wrong: the check not noticing, and the check
reassuring while a sweep is actively writing.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from moral_atlas.analysis import dataset


@pytest.fixture
def store(monkeypatch, tmp_path):
    from moral_atlas import db
    from moral_atlas.config import settings

    test_settings = replace(settings(), data_dir=tmp_path, cache_dir=tmp_path / "cache",)
    monkeypatch.setattr(db, "settings", lambda: test_settings)
    db.init_db()
    for index in range(4):
        db.upsert_film({"film_id": f"film-{index}", "title": f"Film {index}"})
    with db.connect() as con:
        con.execute("INSERT INTO item_bank (item_id, bank_version, text, active) "
                    "VALUES ('I1','b1','A proposition.',1)")
        con.execute("INSERT INTO scores (film_id, item_id, bank_version, variant, run_id, "
                    "value) VALUES ('film-0','I1','b1','spine','r',1)")
    return db


def test_totals_report_what_a_snapshot_can_be_checked_against(store):
    counts = dataset.totals("d1", "b1")
    assert counts["films"] == 4
    assert counts["bank_items"] == 1
    assert counts["scores"] == 1


def test_totals_move_when_the_store_does(store):
    before = dataset.totals("d1", "b1")
    store.upsert_film({"film_id": "film-99", "title": "Late Arrival"})
    after = dataset.totals("d1", "b1")
    assert after["films"] == before["films"] + 1, \
        "a check built on these must see a film that arrived after the snapshot"


def test_counts_notice_writes_that_a_timestamp_would_not(store):
    """The reason this compares counts rather than mtimes.

    Under SQLite this was about WAL: a write landed in atlas.sqlite-wal and the
    main file's mtime could sit still through an entire sweep, so a staleness
    check reading mtimes would report "current" while the corpus was being
    rewritten underneath it. There is no file to stat at all now, which makes
    the same point permanently: counts are the only thing there is to compare.
    """
    before = dataset.totals("d1", "b1")

    for index in range(20):
        store.upsert_film({"film_id": f"bulk-{index}", "title": f"Bulk {index}"})

    after = dataset.totals("d1", "b1")
    assert after["films"] == before["films"] + 20
    assert after["films"] > before["films"], "the counts are what notice"


def test_totals_are_scoped_to_the_versions_asked_for(store):
    with store.connect() as con:
        con.execute("INSERT INTO item_bank (item_id, bank_version, text, active) "
                    "VALUES ('I9','b2','Another bank.',1)")
    assert dataset.totals("d1", "b1")["bank_items"] == 1
    assert dataset.totals("d1", "b2")["bank_items"] == 1
