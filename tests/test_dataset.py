"""The published dataset.

Two things matter enough to pin down. The first is that the index stays small:
the evidence travels now, but a visitor reading a chart must not be made to
download forty subtitle tracks to do it, so the text lives in per-film files
beside the index rather than inside it. The second is that it is honest about
provenance — a film's position depends on which evidence it was read from, so
the document has to say which, per film, every time.

The rest is ordinary arithmetic, tested on a store built by hand so the expected
answer is known rather than asserted against whatever the pipeline last did.
"""
from __future__ import annotations

import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from moral_atlas import db
from moral_atlas.analysis import dataset
from moral_atlas.config import settings
from moral_atlas.web.app import app


def _save_skeleton(film_id, variant, run_id, data, model="claude-opus-5", prompt="p1"):
    """What `llm.stages` writes, without going near an API."""
    with db.connect() as con:
        con.execute(
            "INSERT OR REPLACE INTO skeletons "
            "(film_id, variant, run_id, data, model, prompt_version, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            [film_id, variant, run_id, json.dumps(data), model, prompt, db.now()],
        )


def _skeleton(**overrides):
    base = {
        "legitimacy_source": "Consent of the governed.",
        "opening_power": "The council.", "closing_power": "The commons.",
        "what_is_restored": "The household.", "what_is_overturned": "The council.",
        "antagonist": "The magistrate", "antagonist_origin_given": True,
        "antagonist_origin": "A grievance from the war.",
        "antagonist_fate": "destroyed",
        "protagonist_flaw": "Pride.", "protagonist_change": "Learns to listen.",
        "interiority_granted": ["The daughter"], "interiority_withheld": ["The magistrate"],
        "punished": ["The magistrate"], "forgiven": ["The brother"],
        "final_image": "A lit window.", "final_spoken_line": "Come inside.",
        "tonal_register": "sincere", "depicts_but_does_not_endorse": False,
        "endorsement_evidence": "The ending affirms it.",
        "source_text": "", "inverts_source_how": "",
        "evidence_quotes": ["Come inside."], "unsupported_fields": ["source_text"],
        "confidence": 0.9,
    }
    base.update(overrides)
    return base


@pytest.fixture()
def store(monkeypatch, tmp_path):
    """A small store whose every expected answer is known by construction."""
    test_settings = replace(
        settings(), data_dir=tmp_path, cache_dir=tmp_path / "cache",
        db_path=tmp_path / "dataset.sqlite",
    )
    monkeypatch.setattr(db, "settings", lambda: test_settings)
    monkeypatch.setattr(dataset, "db", db)
    db.init_db()

    db.upsert_film({"film_id": "a", "title": "Film A", "year": 1999,
                    "description": "A spoiler-free prompt.", "seed_note": "battery"})
    db.upsert_film({"film_id": "b", "title": "Film B", "year": 2004,
                    "description": "Another prompt."})

    # Film A exists under two conditions; the richer one must win, and be named.
    _save_skeleton("a", "spine", "run-1",
                   _skeleton(legitimacy_source="Read from the plot alone."))
    _save_skeleton("a", "full", "run-2",
                   _skeleton(legitimacy_source="Read from everything."))
    _save_skeleton("b", "spine", "run-1",
                   _skeleton(antagonist_fate="reconciled", antagonist_origin_given=False,
                             depicts_but_does_not_endorse=True))
    return db


@pytest.fixture()
def scored_store(store):
    """Two items on one axis, scored so the mean is a number we can predict."""
    with db.connect() as con:
        con.execute(
            "INSERT INTO dimensions (dim_version, dim_id, name, question, pole_high, pole_low) "
            "VALUES ('d1', 1, 'Payback or Mercy', 'How are accounts settled?', 'Mercy', 'Payback')")
        for item_id in ("I1", "I2"):
            con.execute(
                "INSERT INTO item_bank (item_id, bank_version, text, cluster_id, active) "
                "VALUES (?, 'b1', 'A proposition.', 1, 1)", [item_id])
            con.execute(
                "INSERT INTO item_dimensions "
                "(dim_version, bank_version, item_id, dim_id, polarity, fit, pass_name, model) "
                "VALUES ('d1', 'b1', ?, 1, 1, 0.8, 'main', 'claude-opus-5')", [item_id])
        # Film A: +1 and -1 → net 0.0 over 2 items.
        con.execute("INSERT INTO scores (film_id, item_id, bank_version, variant, run_id, value, confidence) "
                    "VALUES ('a', 'I1', 'b1', 'full', 'r', 1, 0.9)")
        con.execute("INSERT INTO scores (film_id, item_id, bank_version, variant, run_id, value, confidence) "
                    "VALUES ('a', 'I2', 'b1', 'full', 'r', -1, 0.9)")
        # Film B: one item only, +1 → net 1.0.
        con.execute("INSERT INTO scores (film_id, item_id, bank_version, variant, run_id, value, confidence) "
                    "VALUES ('b', 'I1', 'b1', 'spine', 'r', 1, 0.9)")
    return db


# --------------------------------------------------------------------------
# The index stays small; the evidence travels beside it
# --------------------------------------------------------------------------

def test_the_index_carries_no_evidence_text(store):
    """A chart reader must not pay for forty dialogue tracks to read a chart."""
    db.upsert_evidence("a", "subtitles", "A LINE OF DIALOGUE " * 200)
    payload = dataset.build()
    assert "A LINE OF DIALOGUE" not in json.dumps(payload)


def test_the_index_says_what_evidence_exists_without_carrying_it(store):
    db.upsert_evidence("a", "subtitles", "A line of dialogue.", meta=None)
    db.upsert_evidence("a", "plot", "A plot summary.")
    film = next(f for f in dataset.build()["films"] if f["id"] == "a")
    # Thinnest layer first, so the panel reads plot before dialogue.
    assert [layer["layer"] for layer in film["evidence_layers"]] == ["plot", "subtitles"]
    assert [layer["label"] for layer in film["evidence_layers"]] == [
        "Plot summary", "Dialogue track"]
    assert all("content" not in layer for layer in film["evidence_layers"])


def test_film_evidence_returns_the_text_in_full(store):
    db.upsert_evidence("a", "subtitles", "A line of dialogue.",
                       source_url="https://opus.example/a")
    document = dataset.film_evidence("a")
    assert document["title"] == "Film A"
    assert document["layers"][0]["content"] == "A line of dialogue."
    assert document["layers"][0]["source_url"] == "https://opus.example/a"


def test_film_evidence_is_none_for_an_unknown_film(store):
    assert dataset.film_evidence("no-such-film") is None


def test_a_film_with_no_evidence_yet_reports_an_empty_layer_list(store):
    document = dataset.film_evidence("b")
    assert document is not None and document["layers"] == []


def test_write_puts_each_film_beside_the_index(store, tmp_path):
    db.upsert_evidence("a", "subtitles", "A line of dialogue.")
    path, payload = dataset.write(tmp_path / "api" / "atlas.json")
    beside = tmp_path / "api" / "atlas" / "a.json"
    assert beside.exists()
    assert json.loads(beside.read_text())["layers"][0]["content"] == "A line of dialogue."
    # Only films that have evidence get a file.
    assert not (tmp_path / "api" / "atlas" / "b.json").exists()
    assert payload["_written"]["evidence_files"] == 1


def test_write_can_leave_the_evidence_out(store, tmp_path):
    db.upsert_evidence("a", "subtitles", "A line of dialogue.")
    dataset.write(tmp_path / "api" / "atlas.json", include_evidence=False)
    assert not (tmp_path / "api" / "atlas").exists()


def test_grounding_quotes_are_capped_rather_than_unbounded(store):
    """Quotation for analysis is kept; a subtitle track by degrees is not."""
    _save_skeleton("a", "full", "run-3", _skeleton(
        evidence_quotes=["x" * 900] + [f"quote {i}" for i in range(40)]))
    film = next(f for f in dataset.build()["films"] if f["id"] == "a")
    quotes = film["skeleton"]["evidence_quotes"]
    assert len(quotes) == dataset.MAX_QUOTES
    assert max(len(q) for q in quotes) <= dataset.MAX_QUOTE_CHARS + 1  # +1 for the ellipsis


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------

def test_richest_variant_wins_and_is_named(store):
    film = next(f for f in dataset.build()["films"] if f["id"] == "a")
    assert film["variant"] == "full"
    assert film["variant_label"] == "Everything"
    assert film["skeleton"]["legitimacy_source"] == "Read from everything."


def test_the_newest_run_of_a_condition_wins(store):
    """The table is keyed by run, so re-running leaves the old row in place."""
    _save_skeleton("a", "full", "run-9",
                   _skeleton(legitimacy_source="The re-run reading."))
    film = next(f for f in dataset.build()["films"] if f["id"] == "a")
    assert film["skeleton"]["legitimacy_source"] == "The re-run reading."


def test_a_richer_condition_beats_a_newer_poor_one(store):
    """Recency only breaks ties within a condition; it never outranks evidence."""
    _save_skeleton("a", "spine", "run-9",
                   _skeleton(legitimacy_source="A newer but thinner reading."))
    film = next(f for f in dataset.build()["films"] if f["id"] == "a")
    assert film["variant"] == "full"
    assert film["skeleton"]["legitimacy_source"] == "Read from everything."


def test_a_film_read_only_from_plot_says_so(store):
    film = next(f for f in dataset.build()["films"] if f["id"] == "b")
    assert film["variant"] == "spine"
    assert film["variant_label"] == "Plot only"


# --------------------------------------------------------------------------
# Arithmetic
# --------------------------------------------------------------------------

def test_profiles_are_the_mean_signed_verdict_per_axis(scored_store):
    films = {f["id"]: f for f in dataset.build()["films"]}
    assert films["a"]["profile"] == [
        {"dim_id": 1, "net": 0.0, "n_items": 2, "variant": "full"}]
    assert films["b"]["profile"] == [
        {"dim_id": 1, "net": 1.0, "n_items": 1, "variant": "spine"}]


def test_dimensions_carry_their_share_of_the_bank(scored_store):
    dims = dataset.build()["dimensions"]
    assert [(d["name"], d["n_items"]) for d in dims] == [("Payback or Mercy", 2)]
    assert dims[0]["mean_fit"] == 0.8


def test_totals_count_what_is_actually_there(scored_store):
    totals = dataset.build()["totals"]
    assert totals["films"] == 2
    assert totals["films_with_skeleton"] == 2
    assert totals["films_with_full_skeleton"] == 1
    assert totals["films_profiled"] == 2
    assert totals["bank_items"] == 2
    assert totals["scores"] == 3


def test_a_store_with_no_analysis_still_builds(store):
    """A half-run pipeline reports itself rather than failing to render."""
    payload = dataset.build()
    assert payload["dimensions"] == []
    assert all(film["profile"] == [] for film in payload["films"])
    assert payload["totals"]["films"] == 2


def test_a_film_with_no_skeleton_is_present_and_empty(store):
    db.upsert_film({"film_id": "c", "title": "Film C", "year": 2020})
    film = next(f for f in dataset.build()["films"] if f["id"] == "c")
    assert film["skeleton"] is None
    assert "variant" not in film


# --------------------------------------------------------------------------
# The seam the interface reads
# --------------------------------------------------------------------------

def test_write_produces_the_file_the_interface_fetches(scored_store, tmp_path):
    path, payload = dataset.write(tmp_path / "public" / "api" / "atlas.json")
    assert path.exists()
    assert json.loads(path.read_text())["totals"] == payload["totals"]


def test_api_serves_one_film_evidence(store):
    from moral_atlas.web.routes import atlas as atlas_route
    atlas_route._cache["key"] = None
    db.upsert_evidence("a", "subtitles", "A line of dialogue.")
    client = TestClient(app)

    body = client.get("/api/atlas/films/a").json()
    assert body["layers"][0]["content"] == "A line of dialogue."
    assert client.get("/api/atlas/films/no-such-film").status_code == 404


def test_api_serves_the_same_document(scored_store):
    from moral_atlas.web.routes import atlas as atlas_route
    atlas_route._cache["key"] = None            # the fixture swapped the store
    body = TestClient(app).get("/api/atlas").json()
    assert body["totals"]["films"] == 2
    assert [f["title"] for f in body["films"]] == ["Film A", "Film B"]
