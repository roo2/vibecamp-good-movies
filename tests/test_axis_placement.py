"""The person-placement gate: does it reorder, and does it fail safe?

The gate decides which moral axes a person is read on, so its failure modes
matter more than its happy path. Two of these tests exist because the wrong
behaviour would be invisible: a missing verdict must not empty the compass, and
a stale verdict must not quietly gate on a corpus nobody has any more.
"""
from __future__ import annotations

from moral_atlas.analysis import axis_placement, user_scores


def _axes():
    return [{"dim_id": 1, "name": "A"}, {"dim_id": 2, "name": "B"},
            {"dim_id": 3, "name": "C"}, {"dim_id": 4, "name": "D"}]


def test_axes_that_place_people_come_first(monkeypatch):
    """The real case: axis 2 cannot place a person, axis 3 is the best at it."""
    monkeypatch.setattr(axis_placement, "load",
                        lambda *a: {1: True, 2: False, 3: True, 4: True})
    out = user_scores._placeable_first("s", "v", "b", _axes())
    assert [a["dim_id"] for a in out] == [1, 3, 4, 2]
    # The product takes the first two: the axis at noise no longer holds a slot.
    assert [a["dim_id"] for a in out[:2]] == [1, 3]


def test_order_within_each_group_is_preserved(monkeypatch):
    """The gate reorders across the pass/fail line and nowhere else.

    Margin still decides the order among axes that place people. If this sorted
    unstably, the compass order would drift between processes for no reason a
    reader could see.
    """
    monkeypatch.setattr(axis_placement, "load",
                        lambda *a: {1: False, 2: True, 3: False, 4: True})
    out = user_scores._placeable_first("s", "v", "b", _axes())
    assert [a["dim_id"] for a in out] == [2, 4, 1, 3]


def test_no_verdict_leaves_the_order_exactly_as_it_was(monkeypatch):
    """A corpus never measured this way must behave as it did before the gate."""
    monkeypatch.setattr(axis_placement, "load", lambda *a: None)
    out = user_scores._placeable_first("s", "v", "b", _axes())
    assert [a["dim_id"] for a in out] == [1, 2, 3, 4]


def test_nothing_is_ever_dropped(monkeypatch):
    """Even when every axis fails, the compass still has axes to show.

    Gating membership rather than order would hand a person an empty reading and
    tell them nothing about why.
    """
    monkeypatch.setattr(axis_placement, "load",
                        lambda *a: {1: False, 2: False, 3: False, 4: False})
    out = user_scores._placeable_first("s", "v", "b", _axes())
    assert sorted(a["dim_id"] for a in out) == [1, 2, 3, 4]


def test_load_refuses_a_verdict_whose_inputs_have_moved(monkeypatch):
    """A stale gate is worse than none: it silently reflects a vanished corpus."""
    class Row(dict):
        def __getitem__(self, k):
            return dict.__getitem__(self, k)

    monkeypatch.setattr(axis_placement, "fingerprint", lambda *a: "r9:u9:a9")

    class Con:
        def execute(self, *a):
            return self

        def fetchone(self):
            return Row(axes='[{"dim_id": 1, "places_people": true}]',
                       source_fingerprint="r1:u1:a1")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(axis_placement.db, "connect", lambda **k: Con())
    assert axis_placement.load("s", "v", "b") is None


def test_load_returns_nothing_when_no_axis_passes(monkeypatch):
    """All-fail is indistinguishable from unmeasured, and must not empty the read."""
    class Row(dict):
        def __getitem__(self, k):
            return dict.__getitem__(self, k)

    monkeypatch.setattr(axis_placement, "fingerprint", lambda *a: "same")

    class Con:
        def execute(self, *a):
            return self

        def fetchone(self):
            return Row(axes='[{"dim_id": 1, "places_people": false}]',
                       source_fingerprint="same")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(axis_placement.db, "connect", lambda **k: Con())
    assert axis_placement.load("s", "v", "b") is None


def test_fingerprint_does_not_depend_on_user_tables(monkeypatch):
    """The verdict has to stay valid where the raters are not.

    It is computed where the user records live and read where they do not: the
    corpus export DROPS user tables, and the demo box swaps derived tables in
    while keeping its own real ones. A fingerprint counting `movie_ratings`
    therefore never matches on any machine that reads it — the gate falls
    silently inert in exactly the place it exists for. This was shipped into an
    export once and caught by loading that export back.
    """
    seen = {}

    class Con:
        def execute(self, sql, params=None):
            seen["sql"] = sql
            return self

        def fetchall(self):
            return [{"factor_id": 0, "n_items": 30}, {"factor_id": 1, "n_items": 17}]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(axis_placement.db, "connect", lambda **k: Con())
    out = axis_placement.fingerprint("s", "v", "b")

    assert "movie_ratings" not in seen["sql"], "must not key on a droppable table"
    assert "users" not in seen["sql"]
    assert out == "0:30|1:17"


def test_fingerprint_changes_when_the_axes_are_re_derived(monkeypatch):
    """Re-derived axes DO invalidate the verdict — that is what it is about."""
    rows = [[{"factor_id": 0, "n_items": 30}], [{"factor_id": 0, "n_items": 41}]]

    class Con:
        def __init__(self, r):
            self.r = r

        def execute(self, *a, **k):
            return self

        def fetchall(self):
            return self.r

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(axis_placement.db, "connect", lambda **k: Con(rows[0]))
    first = axis_placement.fingerprint("s", "v", "b")
    monkeypatch.setattr(axis_placement.db, "connect", lambda **k: Con(rows[1]))
    assert axis_placement.fingerprint("s", "v", "b") != first


def test_the_atlas_reads_the_placement_verdict_rather_than_a_constant(monkeypatch):
    """The audit panel published a failure the pipeline had already reversed.

    It carried `axis3_person = 0.13` against a floor of 0.27 and marked that axis
    "measured, not plotted", under a heading explaining why the plot had two axes
    and not three — while the product plotted three and this test measured the
    same axis at 0.62, the highest of the three. Nothing failed, because the
    number was typed in beside the table rather than read from anywhere.

    So the route must serve the live verdict. If this helper stops returning it,
    the panel silently falls back to showing no verdict at all, which is wrong
    but at least not a false one.
    """
    import json

    from moral_atlas.web.routes import factors as route

    stored = [{"dim_id": 0, "label": "Fatalism vs Redemption", "reliability": 0.5,
               "noise_ceiling": 0.26, "places_people": True},
              {"dim_id": 1, "label": "Autonomy vs Order", "reliability": 0.1,
               "noise_ceiling": 0.25, "places_people": False}]

    class Con:
        def execute(self, *_a, **_k):
            return self

        def fetchone(self):
            return {"axes": json.dumps(stored)}

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(route.db, "connect", lambda **k: Con())
    out = route._placement_verdicts("deepseek", "subs", "dolphin-subs")
    assert [a["places_people"] for a in out] == [True, False]
    assert out[1]["reliability"] < out[1]["noise_ceiling"], \
        "a failing axis must arrive with the numbers that make it failing"


def test_no_hand_entered_person_placement_survives_in_findings():
    """Those keys asserted a verdict the pipeline reversed; nothing may quote them.

    `findings` is hand-maintained, so the guard has to be a test rather than a
    constraint. Placement now comes from `axis_placement` on every build.
    """
    from moral_atlas import db

    try:
        with db.connect(read_only=True) as con:
            keys = [r["key"] for r in con.execute(
                "SELECT key FROM findings WHERE key LIKE '%_person' OR key='person_floor'")]
    except Exception:
        return  # no store in this environment; nothing to protect
    assert not keys, f"superseded person-placement constants are back: {keys}"
