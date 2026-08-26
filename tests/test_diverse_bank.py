"""The three pieces that widen the instrument: sampling, semantic cutting, batching.

Each test here pins a specific failure that was measured on the real corpus, so
a regression reads as the bug returning rather than as an assertion moving.
"""
from __future__ import annotations

import pytest

from moral_atlas.analysis import model_bias, sampling, semantic_bank
from moral_atlas.sources import wikidata


# --------------------------------------------------------------------------
# Choosing which films write the propositions
# --------------------------------------------------------------------------

def _film(fid, lang, country, year, genres=("drama film",)):
    import json
    return {"film_id": fid, "title": fid, "year": year,
            "original_language": lang, "origin_country": json.dumps([country]),
            "genres": json.dumps(list(genres))}


LOPSIDED = (
    [_film(f"us{i}", "English", "United States", 2000 + i % 5) for i in range(20)]
    + [_film("kr1", "Korean", "South Korea", 2019),
       _film("ir1", "Persian", "Iran", 2011),
       _film("jp1", "Japanese", "Japan", 1988)]
)


ENGLISH_ALREADY = {f"us{i}" for i in range(20)}


def test_sampling_reaches_the_rare_languages_first_once_english_is_covered():
    """The situation this exists for: 135 films harvested, 122 of them English.

    With English already saturated its marginal worth has collapsed, so every
    remaining pick should go to a language the set does not have. Note that on
    an EMPTY set every film here ties, and correctly so — with nothing chosen,
    no film is more informative than another.
    """
    picks = sampling.select(LOPSIDED, 3, already=ENGLISH_ALREADY)
    languages = [p["original_language"] for p in picks]
    assert set(languages) == {"Korean", "Persian", "Japanese"}, (
        f"expected the three unrepresented languages, got {languages}")


def test_sampling_never_returns_a_film_already_harvested():
    """Re-harvesting a film buys no coverage and costs a full scoring pass."""
    picks = sampling.select(LOPSIDED, 10, already=ENGLISH_ALREADY)
    assert not ({p["film_id"] for p in picks} & ENGLISH_ALREADY)


def test_sampling_stops_when_the_pool_runs_out():
    """Asking for more films than exist returns what there is, not an error."""
    picks = sampling.select(LOPSIDED, 500, already=ENGLISH_ALREADY)
    assert len(picks) == len(LOPSIDED) - len(ENGLISH_ALREADY)


def test_coverage_reports_how_lopsided_a_set_is():
    report = sampling.coverage(LOPSIDED)
    assert report["n_films"] == 23
    assert report["distinct"]["original_language"] == 4
    assert report["dominance"]["original_language"] == pytest.approx(20 / 23)


# --------------------------------------------------------------------------
# Cutting the harvest by meaning
# --------------------------------------------------------------------------

def test_polarity_blocking_keeps_a_negation_out_of_its_own_assertion():
    """Embeddings score these two at 0.59 — higher than the same claim reworded.

    Nothing is allowed to depend on the geometry getting that right, so the
    blocking has to separate them before any clustering happens.
    """
    from moral_atlas.analysis import bank as lexical

    assert lexical.polarity_class("The ends justify the means.") != \
        lexical.polarity_class("The ends do not justify the means.")


def test_a_single_member_neighbourhood_needs_no_model():
    """One sentence cannot contain two claims, so it must not cost a call."""
    class Exploding:
        def parse(self, **kwargs):
            raise AssertionError("a lone proposition was sent to the model")

    group = {"polarity": "plain",
             "members": [{"text": "Mercy is owed to the defeated.", "film_id": "f1"}]}
    out = semantic_bank.distinct_claims(group, Exploding())
    assert [c["text"] for c in out] == ["Mercy is owed to the defeated."]
    assert out[0]["films"] == {"f1"}


def test_support_counts_films_rather_than_sentences():
    """Two propositions from one film are one film's opinion, however worded.

    Counting sentences is what let a single talkative film look like agreement.
    """
    class Splitter:
        def parse(self, **kwargs):
            from moral_atlas.analysis.semantic_bank import Claim, ClaimSet
            return ClaimSet(claims=[Claim(text="Revenge is justified.", members=[1, 2, 3])])

    group = {"polarity": "plain", "members": [
        {"text": "Revenge is just.", "film_id": "f1"},
        {"text": "Vengeance is warranted.", "film_id": "f1"},
        {"text": "Payback is deserved.", "film_id": "f2"},
    ]}
    claim = semantic_bank.distinct_claims(group, Splitter())[0]
    assert claim["support"] == 2, "three sentences from two films is support 2"
    assert claim["films"] == {"f1", "f2"}


def test_consolidation_carries_film_support_across_the_second_pass():
    """The second pass reads claims, not propositions, so support must survive it.

    Losing it here would silently reset every item to support 1 and undo the
    only evidence the bank keeps about how widely a claim is raised.
    """
    claims = [{"text": "Revenge is justified.", "films": {"f1", "f2"}},
              {"text": "Vengeance is warranted.", "films": {"f3"}}]
    assert semantic_bank._films_of(claims[0]) == {"f1", "f2"}
    assert semantic_bank._films_of({"film_id": "f9"}) == {"f9"}
    assert semantic_bank._films_of({"text": "orphan"}) == set()


# --------------------------------------------------------------------------
# Batching the scoring
# --------------------------------------------------------------------------

def test_slices_cover_every_item_exactly_once():
    items = [{"item_id": f"I{n:03d}"} for n in range(97)]
    parts = list(model_bias._slices(items, 40))
    assert [len(p) for p in parts] == [40, 40, 17]
    assert [i["item_id"] for p in parts for i in p] == [i["item_id"] for i in items]


def test_the_batched_prompt_carries_the_film_and_not_the_bank():
    """The whole point of the arrangement: the film is the cacheable prefix.

    If the bank ever ends up in here, every slice resends the evidence and the
    dominant cost is multiplied by the number of slices.
    """
    from moral_atlas.llm import prompts

    system = prompts.scoring_batched_system("SUBTITLES: a line of dialogue")
    assert "SUBTITLES: a line of dialogue" in system
    assert "not_addressed" in system, "the silence instruction must survive batching"
    assert "slice" in system.lower(), "the model must know it is seeing part of a bank"


# --------------------------------------------------------------------------
# Metadata backfill
# --------------------------------------------------------------------------

def test_wikidata_folds_one_row_per_value_into_lists():
    """SPARQL returns the cross product, so three genres arrive as three rows."""
    rows = [
        {"imdb": {"value": "tt1"}, "genresLabel": {"value": "drama film"},
         "directorsLabel": {"value": "Some Director"}},
        {"imdb": {"value": "tt1"}, "genresLabel": {"value": "trial film"},
         "directorsLabel": {"value": "Some Director"}},
    ]
    folded = wikidata._fold(rows)
    assert folded["tt1"]["genres"] == ["drama film", "trial film"]
    assert folded["tt1"]["directors"] == ["Some Director"]


def test_wikidata_drops_unresolved_q_numbers():
    """A bare Q-number in a genre filter is worse than an empty one."""
    rows = [{"imdb": {"value": "tt2"}, "genresLabel": {"value": "Q12345"}},
            {"imdb": {"value": "tt2"}, "genresLabel": {"value": "epic film"}}]
    assert wikidata._fold(rows)["tt2"]["genres"] == ["epic film"]
