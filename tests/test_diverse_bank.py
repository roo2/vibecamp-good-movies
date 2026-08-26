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


# --------------------------------------------------------------------------
# Does the instrument reproduce itself?
# --------------------------------------------------------------------------

def _planted(n_films, n_items, k, engagement, rng, noise):
    """Films x items where each item is driven by exactly one of k factors."""
    import numpy as np

    scores = rng.normal(size=(n_films, k))
    owner = np.arange(n_items) % k
    signal = scores[:, owner] + rng.normal(scale=noise, size=(n_films, n_items))
    values = np.where(signal >= 0, 1.0, -1.0)
    # Zero is the missing marker for this estimator, so silence is punched in
    # rather than being a value the signal could take.
    return np.where(rng.random((n_films, n_items)) < engagement, values, 0.0)


def test_split_half_overlap_is_near_chance_on_noise():
    """Two halves of structureless data must not look like they agree."""
    import numpy as np
    from moral_atlas.analysis import latent

    rng = np.random.default_rng(3)
    values = np.where(rng.random((300, 60)) < 0.6,
                      rng.choice([-1.0, 1.0], size=(300, 60)), 0.0)
    result = latent.split_half_overlap(values, k=5, reps=6)
    assert result["overlap"] < 4 * result["chance"], (
        f"noise reproduced itself at {result['overlap']:.2f}")


def test_split_half_overlap_recovers_planted_structure():
    """And real structure must come back from both halves, or the measure is useless."""
    import numpy as np
    from moral_atlas.analysis import latent

    rng = np.random.default_rng(3)
    planted = _planted(400, 60, k=4, engagement=0.85, rng=rng, noise=0.35)
    result = latent.split_half_overlap(planted, k=4, reps=6)
    # The threshold is set where the measure DISCRIMINATES rather than at some
    # ideal: planted structure lands near 0.74 here and noise near 0.08. For
    # scale, the real deepseek corpus scores 0.21 at k=5 against a chance floor
    # of 0.02 — above chance, nowhere near reproducible.
    assert result["overlap"] > 0.6, (
        f"planted factors only reproduced at {result['overlap']:.2f}")


def test_each_group_is_signed_by_the_factor_it_actually_loads_on():
    """k-means labels are arbitrary integers, not factor indices.

    The code used to read `loadings[members, factor]` — cluster 3's loading on
    eigenvector 3 — as though a cluster's label named a factor. On the real
    corpus none of the twenty clusters had a label matching the eigenvector its
    members load on, and the column being read held a median 20% of the group's
    signal. That sign decides which propositions are reverse-keyed, and the
    matching eigenvalue decides which axes the product calls strongest.
    """
    import numpy as np
    from moral_atlas.analysis import latent

    rng = np.random.default_rng(11)
    # Three well-separated factors; which label k-means gives each is arbitrary.
    planted = _planted(300, 45, k=3, engagement=0.9, rng=rng, noise=0.25)
    items = [f"I{n:03d}" for n in range(45)]
    groups, _distance, loading, dominant = latent.item_groups(planted, items, 3)

    assert set(dominant) == {0, 1, 2}, "every non-empty group needs a factor"
    corr = latent._pairwise_correlation(latent._film_centred(planted))
    values, vectors = np.linalg.eigh(corr)
    order = np.argsort(values)[::-1][:3]
    loadings = vectors[:, order] * np.sqrt(np.clip(values[order], 0, None))

    for label, factor in dominant.items():
        members = [i for i, item in enumerate(items) if groups[item] == label]
        profile = np.abs(loadings[members].mean(axis=0))
        assert factor == int(np.argmax(profile)), (
            f"group {label} was signed by factor {factor}, but loads on "
            f"{int(np.argmax(profile))}")
        # and the signed value must be that column's magnitude, up to orientation
        assert np.allclose(sorted(abs(loading[items[i]]) for i in members),
                           sorted(abs(loadings[members, factor])))


def test_the_product_never_shows_two_facets_of_one_factor():
    """Eight of the twenty groups load on the first factor alone.

    Listing several of them side by side implies several independent readings
    of a person when they are one reading rephrased, and nothing on the screen
    lets a reader tell. Groups sharing a factor share its eigenvalue, so that is
    what deduplicates them; the group with the most propositions stands for it.
    """
    import sqlite3

    from moral_atlas.analysis import user_scores

    def row(**kw):
        return kw

    rows = [row(factor_id=1, name="a", question="?", pole_high="h", pole_low="l",
                pole_high_label="A", pole_low_label="B", eigenvalue=68.2),
            row(factor_id=2, name="b", question="?", pole_high="h", pole_low="l",
                pole_high_label="C", pole_low_label="D", eigenvalue=68.2),
            row(factor_id=3, name="c", question="?", pole_high="h", pole_low="l",
                pole_high_label="E", pole_low_label="F", eigenvalue=31.4)]

    class FakeCursor:
        def fetchall(self): return rows

    class FakeCon:
        def execute(self, *a, **k): return FakeCursor()

    import contextlib
    from moral_atlas import db as db_mod
    original = db_mod.connect
    db_mod.connect = lambda *a, **k: contextlib.nullcontext(FakeCon())
    try:
        axes = user_scores.factor_axes("s", "v", "b", limit=None)
    finally:
        db_mod.connect = original
    assert len(axes) == 2, f"two distinct factors, got {[a['dim_id'] for a in axes]}"
    assert [a["dim_id"] for a in axes] == [1, 3]


def test_a_proposition_every_film_agrees_with_is_not_a_dimension():
    """And it is worse than useless, which is why it must be removed by hand.

    Film-centring subtracts each film's own affirm rate, so a unanimously
    affirmed item's centred value becomes `constant - film_mean` — a negated
    copy of how agreeable the film is. On the real corpus those items correlate
    -1.00 with the film's affirm rate and carried a mean absolute loading of
    1.00 against 0.34 for everything else: the correction for acquiescence was
    building an acquiescence factor out of them.
    """
    import numpy as np

    from moral_atlas.analysis import latent

    rng = np.random.default_rng(5)
    contested = np.where(rng.random((80, 6)) < 0.5, 1.0, -1.0)
    unanimous = np.ones((80, 4))                      # every film affirms
    matrix = np.hstack([contested, unanimous])
    items = [f"I{n:03d}" for n in range(matrix.shape[1])]

    # Rebuilt through the same rule response_matrix applies.
    def kept(min_disagreement):
        out = []
        for j, item in enumerate(items):
            v = matrix[:, j][matrix[:, j] != 0]
            share = (v > 0).mean()
            if min(share, 1 - share) >= min_disagreement:
                out.append(item)
        return out

    assert len(kept(latent.MIN_DISAGREEMENT)) == 6, "the four unanimous items must go"
    assert len(kept(0.0)) == 10, "and the rule must be what removes them, not chance"
    assert 0 < latent.MIN_DISAGREEMENT < 0.5, "a share of the minority side, not a count"


def test_every_screen_orders_the_axes_the_same_way():
    """Three screens show these groups; they used to sort differently.

    The atlas, a person's compass and a film's own reading each listed the axes
    in their own order, so which axis a reader met first depended on where they
    met it and nothing explained why. They now share one key, and the product's
    shortlist must be a SUBSEQUENCE of the atlas order — same sequence, fewer
    entries — rather than merely overlapping with it.
    """
    from moral_atlas.analysis import factor_names

    factors = [
        {"factor_id": 1, "name": "b axis", "eigenvalue": 11.6, "n_items": 8},
        {"factor_id": 2, "name": "a axis", "eigenvalue": 11.6, "n_items": 20},
        {"factor_id": 3, "name": "c axis", "eigenvalue": 6.0, "n_items": 14},
        {"factor_id": 4, "name": "d axis", "eigenvalue": 6.0, "n_items": 7},
        {"factor_id": 5, "name": "e axis", "eigenvalue": None, "n_items": 3},
    ]
    ordered = sorted(factors, key=factor_names.by_support)
    assert [f["factor_id"] for f in ordered] == [2, 1, 3, 4, 5], (
        "eigenvalue first, then propositions behind it, then the name")

    # A missing eigenvalue must sort last rather than first, which is what a
    # bare `-(None or 0)` would do if the fallback were ever removed.
    assert ordered[-1]["factor_id"] == 5

    # The key must be TOTAL, or the order depends on which query fed it. Two
    # axes identical on every visible field still have to come out the same way
    # whichever order they arrived in.
    same = [{"factor_id": 9, "name": "x", "eigenvalue": 1.0, "n_items": 2},
            {"factor_id": 8, "name": "x", "eigenvalue": 1.0, "n_items": 2}]
    forwards = [f["factor_id"] for f in sorted(same, key=factor_names.by_support)]
    backwards = [f["factor_id"] for f in sorted(reversed(same), key=factor_names.by_support)]
    assert forwards == backwards == [8, 9]


def test_the_product_shortlist_is_a_subsequence_of_the_atlas_order():
    """Taking one axis per factor must not resequence what is left."""
    from moral_atlas.analysis import factor_names

    factors = [
        {"factor_id": 1, "name": "a", "eigenvalue": 11.6, "n_items": 20},
        {"factor_id": 2, "name": "b", "eigenvalue": 11.6, "n_items": 8},
        {"factor_id": 3, "name": "c", "eigenvalue": 6.7, "n_items": 11},
        {"factor_id": 4, "name": "d", "eigenvalue": 6.0, "n_items": 14},
    ]
    atlas = [f["factor_id"] for f in sorted(factors, key=factor_names.by_support)]

    seen, product = set(), []
    for f in sorted(factors, key=factor_names.by_support):
        if f["eigenvalue"] in seen:
            continue
        seen.add(f["eigenvalue"])
        product.append(f["factor_id"])

    positions = [atlas.index(fid) for fid in product]
    assert positions == sorted(positions), (
        f"product order {product} is not a subsequence of atlas order {atlas}")


def test_comparing_two_readers_counts_only_what_both_answered():
    """Agreement over items only one reader engaged would be meaningless.

    And it is direction that is compared, not strength: whether a film holds a
    position firmly or in passing is a judgement the graded scale invites and
    two readers calibrate differently, while affirm-versus-deny is the claim the
    instrument actually makes.
    """
    import contextlib

    from moral_atlas import db as db_mod
    from moral_atlas.analysis import film_compare

    bank = [{"item_id": "I1", "text": "one"}, {"item_id": "I2", "text": "two"},
            {"item_id": "I3", "text": "three"}]
    verdicts = {
        "a": [{"item_id": "I1", "value": 2, "confidence": 0.9, "evidence": "x"},
              {"item_id": "I2", "value": -1, "confidence": 0.9, "evidence": "y"}],
        "b": [{"item_id": "I1", "value": 1, "confidence": 0.9, "evidence": "z"},
              {"item_id": "I2", "value": 1, "confidence": 0.9, "evidence": "w"},
              {"item_id": "I3", "value": 1, "confidence": 0.9, "evidence": "v"}],
    }

    class Cursor:
        def __init__(self, rows): self.rows = rows
        def fetchall(self): return self.rows
        def fetchone(self): return self.rows[0] if self.rows else None
        def __iter__(self): return iter(self.rows)

    class Con:
        def execute(self, sql, args=None):
            if "item_bank" in sql: return Cursor(bank)
            if "FROM films" in sql: return Cursor([{"title": "F", "year": 2000}])
            return Cursor(verdicts[args[0]])

    original = db_mod.connect
    db_mod.connect = lambda *a, **k: contextlib.nullcontext(Con())
    try:
        out = film_compare.compare("f1", ["a", "b"], "bank")
    finally:
        db_mod.connect = original

    assert out["engaged"] == {"a": 2, "b": 3}
    assert out["shared"] == 2, "I3 was answered by one reader only"
    assert out["only"] == {"a": 0, "b": 1}
    # I1: +2 vs +1 is the SAME side despite differing strength.
    assert out["agreed"] == 1
    assert [r["item_id"] for r in out["split"]] == ["I2"]
