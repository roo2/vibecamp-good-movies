"""Tests for the dimension layer — the arithmetic and the blind-replicate wiring.

The claim "these axes are in the corpus" rests entirely on the numbers in
`dimensions.validate`, so those numbers are worth testing on data whose answer
is known by construction. No LLM is involved anywhere here.
"""
from __future__ import annotations

from moral_atlas.analysis import dimensions as dim


# --------------------------------------------------------------------------
# Agreement
# --------------------------------------------------------------------------

def test_kappa_is_one_for_identical_assignments():
    a = {"I1": 1, "I2": 2, "I3": 3, "I4": 1}
    assert dim.cohens_kappa(a, dict(a))["kappa"] == 1.0


def test_kappa_is_about_zero_for_chance_agreement():
    """Two labellings that agree only as often as their marginals predict.

    This is the case raw agreement flatters and kappa does not: both passes put
    most items on axis 1, so they agree 50% of the time while sharing nothing.
    """
    a = {f"I{i}": (1 if i < 5 else 2) for i in range(10)}
    # agrees on I0,I1 and I7,I8,I9 — five of ten, which is exactly what these
    # two sets of marginals predict by chance
    b = {"I0": 1, "I1": 1, "I2": 2, "I3": 2, "I4": 2,
         "I5": 1, "I6": 1, "I7": 2, "I8": 2, "I9": 2}
    k = dim.cohens_kappa(a, b)
    assert k["raw"] == 0.5
    assert k["chance"] == 0.5
    assert abs(k["kappa"]) < 1e-9


def test_kappa_ignores_items_only_one_pass_saw():
    """The replicate pass covers a sample, so overlap is the only fair basis."""
    a = {"I1": 1, "I2": 2, "I3": 3}
    b = {"I1": 1, "I2": 2}
    k = dim.cohens_kappa(a, b)
    assert k["n"] == 2 and k["agree"] == 2


# --------------------------------------------------------------------------
# Behavioural statistics
# --------------------------------------------------------------------------

def test_co_engagement_counts_pairs_sharing_an_axis():
    # one film engaging three items: two on axis 1, one on axis 2.
    # pairs = (a,b) same, (a,c) different, (b,c) different -> 1/3
    packets = {("f", "full"): [("a", 1), ("b", 1), ("c", -1)]}
    assign = {"a": 1, "b": 1, "c": 2}
    assert dim._co_engagement(packets, assign) == 1 / 3


def test_co_engagement_is_zero_when_no_two_items_share_an_axis():
    packets = {("f", "full"): [("a", 1), ("b", 1)]}
    assert dim._co_engagement(packets, {"a": 1, "b": 2}) == 0.0


def test_coherence_rewards_a_film_landing_on_one_pole():
    """Three items on one axis, all pointing the same way after polarity."""
    packets = {("f", "full"): [("a", 1), ("b", 1), ("c", -1)]}
    assign = {"a": 1, "b": 1, "c": 1}
    polarity = {"a": 1, "b": 1, "c": -1}   # c affirms the low pole, so -1 * -1 = +1
    value, cells = dim._coherence(packets, assign, polarity)
    assert cells == 1
    assert value == 1.0


def test_coherence_punishes_a_film_scattered_across_a_pole():
    packets = {("f", "full"): [("a", 1), ("b", -1), ("c", 1), ("d", -1)]}
    assign = dict.fromkeys("abcd", 1)
    polarity = dict.fromkeys("abcd", 1)
    value, _ = dim._coherence(packets, assign, polarity)
    assert value == 0.0


def test_coherence_skips_cells_below_the_minimum():
    """Two items is not evidence that a film has a position on an axis."""
    packets = {("f", "full"): [("a", 1), ("b", 1)]}
    _value, cells = dim._coherence(packets, {"a": 1, "b": 1}, {"a": 1, "b": 1})
    assert cells == 0


# --------------------------------------------------------------------------
# The null
# --------------------------------------------------------------------------

def test_permutation_null_holds_axis_sizes_fixed_and_is_seed_stable():
    """A shuffled label vector must be a permutation of the real one.

    That is what stops the test manufacturing significance out of lopsided
    groups: the null differs from the observed only in WHICH items sit on which
    axis, never in how big the axes are.
    """
    packets = {("f", "full"): [("a", 1), ("b", 1), ("c", 1), ("d", 1)]}
    ids = ["a", "b", "c", "d"]
    labels = [1, 1, 2, 2]
    seen: list[dict[str, int]] = []

    def capture(assign):
        seen.append(dict(assign))
        return dim._co_engagement(packets, assign)

    first = dim._permutation(0.5, capture, ids, labels, n=25, seed=1)
    assert all(sorted(a.values()) == sorted(labels) for a in seen)
    assert first["permutations"] == 25

    second = dim._permutation(0.5, lambda a: dim._co_engagement(packets, a),
                              ids, labels, n=25, seed=1)
    assert first["null_mean"] == second["null_mean"]     # same seed, same null


def test_permutation_reports_how_often_the_null_matched_the_observation():
    # Two overlapping packets, so which item sits on which axis actually moves
    # the statistic. (With a single packet the score depends only on the label
    # multiset, the null has zero variance, and z is reported as None.)
    packets = {("f1", "full"): [("a", 1), ("b", 1), ("c", 1)],
               ("f2", "full"): [("c", 1), ("d", 1)]}
    # 1.0 is unreachable: it would need all four items on one axis, and the
    # label vector holds two of each.
    out = dim._permutation(1.0, lambda a: dim._co_engagement(packets, a),
                           ["a", "b", "c", "d"], [1, 1, 2, 2], n=50, seed=2)
    assert out["n_at_least_observed"] == 0
    assert out["null_sd"] > 0
    assert out["z"] > 0


def test_permutation_reports_no_z_when_the_null_cannot_vary():
    """Honest silence beats a divide-by-zero dressed up as a result."""
    packets = {("f", "full"): [("a", 1), ("b", 1), ("c", 1), ("d", 1)]}
    out = dim._permutation(0.5, lambda a: dim._co_engagement(packets, a),
                           ["a", "b", "c", "d"], [1, 1, 2, 2], n=20, seed=2)
    assert out["null_sd"] == 0
    assert out["z"] is None


# --------------------------------------------------------------------------
# Blind replicate wiring
# --------------------------------------------------------------------------

class _FakeClient:
    """Answers with the dimension number it was shown, so the test can check
    that `assign` maps a renumbered answer back to the real axis."""

    model = "fake-model"

    def __init__(self, pick: int = 1):
        self.pick = pick
        self.systems: list[str] = []

    def parse(self, *, system, user, output_model, max_tokens=0, **_kw):
        self.systems.append(system)
        ids = [line.split(".", 1)[0] for line in user.splitlines() if ". " in line]
        return output_model(assignments=[
            {"item_id": i, "dim_id": self.pick, "polarity": 1, "fit": 0.9}
            for i in ids
        ])

    def map(self, items, fn, on_result=None, on_error=None):
        out = []
        for it in items:
            res = fn(it)
            out.append(res)
            if on_result:
                on_result(it, res)
        return out


DIMS = [
    {"dim_id": i, "name": f"axis {i}", "question": "q?",
     "pole_high": "high", "pole_low": "low"}
    for i in range(1, 5)
]
ITEMS = [{"item_id": f"I{i:03d}", "text": f"proposition {i}"} for i in range(1, 9)]


def test_assignment_without_shuffle_returns_the_dimension_the_model_chose():
    client = _FakeClient(pick=2)
    out = dim.assign("dtest", "btest", DIMS, client, items=ITEMS,
                     persist=False)
    assert {a["dim_id"] for a in out} == {2}
    assert len(out) == len(ITEMS)


def test_blind_replicate_renumbers_dimensions_and_maps_the_answer_back():
    """The point of the replicate: the model cannot agree by picking position 1.

    With a shuffle seed the axes are renumbered before the model sees them, so
    an answer of "1" means whichever real axis was placed first — and `assign`
    must translate it back. If it did not, agreement between the two passes
    would be meaningless.
    """
    client = _FakeClient(pick=1)
    out = dim.assign("dtest", "btest", DIMS, client, items=ITEMS,
                     pass_name="replicate", shuffle_seed=11, persist=False)

    shown = client.systems[0]
    # the axis presented as number 1 is the one every answer should map to
    first_line = [ln for ln in shown.splitlines() if ln.startswith("1. ")][0]
    expected_name = first_line.split(" — ")[0][3:]
    expected_id = next(d["dim_id"] for d in DIMS if d["name"] == expected_name)

    assert {a["dim_id"] for a in out} == {expected_id}


def test_shuffled_and_unshuffled_passes_agree_on_the_same_underlying_axis():
    """End to end: two passes that 'chose' the same real axis agree perfectly."""
    plain = dim.assign("dtest", "btest", DIMS, _FakeClient(pick=3), items=ITEMS,
                       persist=False)

    probe = _FakeClient(pick=1)
    dim.assign("dtest", "btest", DIMS, probe, items=ITEMS,
               pass_name="replicate", shuffle_seed=11, persist=False)
    order = [ln for ln in probe.systems[0].splitlines() if ln[:1].isdigit()]
    position_of_axis_3 = next(
        i for i, ln in enumerate(order, start=1) if ln.split(" — ")[0][3:] == "axis 3")

    shuffled = dim.assign("dtest", "btest", DIMS, _FakeClient(pick=position_of_axis_3),
                          items=ITEMS, pass_name="replicate", shuffle_seed=11,
                          persist=False)

    k = dim.cohens_kappa({a["item_id"]: a["dim_id"] for a in plain},
                         {a["item_id"]: a["dim_id"] for a in shuffled})
    assert k["agree"] == len(ITEMS)


def test_assignment_drops_items_and_axes_the_model_invented():
    """A hallucinated item id or axis number is dropped rather than stored."""
    class Rogue(_FakeClient):
        def parse(self, *, system, user, output_model, max_tokens=0, **_kw):
            return output_model(assignments=[
                {"item_id": "I001", "dim_id": 1, "polarity": 1, "fit": 0.9},
                {"item_id": "NOPE", "dim_id": 1, "polarity": 1, "fit": 0.9},
                {"item_id": "I002", "dim_id": 99, "polarity": 1, "fit": 0.9},
            ])

    out = dim.assign("dtest", "btest", DIMS, Rogue(), items=ITEMS, persist=False)
    assert [a["item_id"] for a in out] == ["I001"]


def test_polarity_is_normalised_to_plus_or_minus_one():
    class Sloppy(_FakeClient):
        def parse(self, *, system, user, output_model, max_tokens=0, **_kw):
            return output_model(assignments=[
                {"item_id": "I001", "dim_id": 1, "polarity": 0, "fit": 0.5},
                {"item_id": "I002", "dim_id": 1, "polarity": -3, "fit": 0.5},
            ])

    out = dim.assign("dtest", "btest", DIMS, Sloppy(), items=ITEMS, persist=False)
    assert sorted(a["polarity"] for a in out) == [-1, 1]
