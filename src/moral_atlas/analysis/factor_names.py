"""Name the axes the films produced, instead of asking for axes and getting them.

The difference from `dimensions.derive` is the order of operations, and it is the
whole point. There, a model is handed 694 propositions and asked for eight moral
dimensions — so the count is a parameter, the grouping is the model's judgement,
and the resulting axes cannot be evidence about the corpus, because a model asked
for eight will always return eight.

Here the model is not asked what the axes are. `latent` decides that: how many
factors clear a permutation null, and which items load onto each. By the time a
model is involved the number and the membership are settled, and the only
remaining question is linguistic — these propositions get answered the same way
by the same films, so what are they about?

That makes the naming falsifiable in a way the deriving never was. A group whose
items have nothing in common produces a name that reads as a list of unrelated
things, and `coherent` is the namer's own admission of it. An axis that cannot be
named is a finding about the factor rather than a failure of the namer.

WHY THE NAMES DIFFER BETWEEN MODELS. They should, and not because the namers
disagree about English. A scorer that engages 272 items on a film and one that
engages 6 have measured different corpora; the response matrices differ, so the
factors differ, so the groups handed to the namer differ. The name is downstream
of all of it. Comparing names across models therefore compares what each model's
verdicts made of the same films — which is the question — rather than comparing
two models' taste in phrasing.

The namer is deliberately the same model that produced the verdicts. One house
namer would tidy the language and hide the thing worth seeing: if DeepSeek's
factors are only nameable in DeepSeek's terms, that is a result.
"""
from __future__ import annotations

import json

from typing import Any

from pydantic import BaseModel, Field

from .. import db
from ..config import PROMPT_VERSION
from ..llm.providers import SCORERS, client_for

# Enough of a group to characterise it without paying for all of it. Groups run
# to sixty items, and where there is a shared thread it is visible in far fewer;
# where there is not, more items would not rescue it.
SAMPLE = 40

# Below this, a proposition's loading says almost nothing about what an axis
# means. Measured on the leading axis, 7 of its 23 propositions fall here — and
# they include the ones a reader would pick out as most obviously on-theme,
# which is exactly the trap: "there is a right order that precedes individual
# choice" loads +0.17 where "the state has the right to take a person's life"
# loads +0.56. Showing both as equals invites a name drawn from the wrong one.
MIN_WEIGHT_TO_NAME = 0.20

# There is no display threshold any more, and there should not have been one. A
# factor either beats the permutation null or it does not, and `latent` already
# applies that test at 5%; anything stored here has passed it. The 25% bar on top
# was picked to keep a list short, which is a layout problem wearing the clothes
# of a statistical one — it hid real findings from the page whose entire job is
# to show them, and the number itself came from nowhere.
#
# The product still shows a handful, because a person reading their own compass
# is not auditing a corpus. That limit lives in `user_scores.PRODUCT_AXES`, where
# it is honestly a presentation choice.


class FactorName(BaseModel):
    factor_id: int
    # NO high/low here, deliberately. Which end of a factor is "high" is a
    # convention this code owns — the first list shown is the positive-loading
    # end, always — and asking a model to track it as well produced an axis
    # whose labels were swapped onto the wrong descriptions: "Cynical realism"
    # captioned "humans are capable of selfless virtue". It failed only on the
    # factor where one end was unobserved and the model had to reason about a
    # side it could not see. The names below are anchored to the two LISTS,
    # which the model can see, and the code maps lists to poles.
    first_label: str = Field(
        description="Two or three words naming the position the FIRST list of "
                    "propositions asserts. A stance somebody would own, never "
                    "the negation of the other end.")
    second_label: str = Field(
        description="The same for the SECOND list — or, if that list is empty, "
                    "for the position a work would hold that denied every "
                    "proposition in the first.")
    first: str = Field(description="One sentence: what a work at the first end claims.")
    second: str = Field(description="One sentence: what a work at the second end claims. "
                                    "Say here if that end was inferred rather than observed.")
    question: str = Field(description="The moral question these share, as one sentence.")
    coherent: bool = Field(
        description="False if these propositions do not actually share a moral "
                    "question and any name would be a stretch.")


class FactorNames(BaseModel):
    factors: list[FactorName]


SYSTEM = """\
You are reading groups of moral propositions that were sorted by STATISTICS, not
by meaning. Each group contains propositions that the same films answered the
same way — affirming together, denying together, or passing over together.

For each group, say what its propositions have in common as a moral question.

Each group is given to you SPLIT INTO ITS TWO ENDS. Films at one end of the axis
affirm the first list; films at the other end affirm the second. That split is
not a suggestion — it is what the statistics found, and it is the axis. Read the
two lists against each other and name what they disagree ABOUT.

A group may arrive with one end empty. That means every proposition in it points
the same way, so the axis has only been observed from one side. It is still an
axis and BOTH LABELS MUST STILL BE REAL POSITIONS: name the unobserved end as
the stance a film would hold that denied all of those propositions. Never write
"none", "empty", "not observed" or anything of that shape into a label — a
reader is shown these two words at the ends of a line, and a placeholder there
is worse than a guess. Say that the end was inferred rather than observed in its
`first` or `second` sentence instead, where there is room to explain it.

Within each end the propositions are listed STRONGEST FIRST, and the number in
brackets is how strongly that proposition belongs to this axis. Weight them by
it: one at [0.55] tells you three times as much about what the axis means as one
at [0.18], and a striking phrase near the bottom is not the theme just because
it is striking. Propositions too faint to characterise the axis are not shown at
all, though they still count toward where a film sits. If the central propositions and the tail describe different things,
that is a group with no single theme, and coherent=false is the honest answer.

An axis has two ends and both of them are positions somebody holds. Name it so a
reader can see what it runs BETWEEN, because they will be shown their own place
on it as a point on a line, and a line has to be labelled at both ends.

  - `first_label` names the position the FIRST list asserts; `second_label` the
    SECOND. Two or three words each. Each must be a position in its own right,
    never the absence or negation of the other: "Self-preservation", not "Not
    self-sacrificing"; "Absolute values", not "Non-relativist". If you cannot
    name one of them as something a person would own, you have probably named
    the other as a topic rather than a stance — reword both.
  - `first` and `second` say, in a sentence each, what a work at that end
    claims. Phrase both so someone holding that view would accept the wording
    as fair. Keep each sentence with its own label: the commonest failure here
    is describing one end and captioning it with the other's name.
  - `question` is the axis as a question with two defensible sides, not a topic.

You are NOT asked which end is high or low, or to write the axis's name. Those
are decided from the statistics and assembled around your labels.

You did not choose these groupings and you are not being asked to improve them.
If a group's propositions genuinely do not share a moral question, set
coherent=false and give the closest description you can. A statistical factor
that resists naming is a real and useful outcome — do not manufacture a theme to
cover one.
"""


def _items_by_factor(
    groups: dict[str, int], texts: dict[str, str],
    distance: dict[str, float] | None = None,
    loading: dict[str, float] | None = None,
    weights: dict[str, float] | None = None,
) -> dict[int, tuple[list[tuple[float, str]], list[tuple[float, str]]]]:
    """Each factor's propositions, the ones that define it most first.

    The order is the whole point, and getting it wrong produced a real bad name.
    These used to be sorted by item_id — which is bank insertion order, so the
    slice a namer saw was an arbitrary corner of the cluster rather than a
    reading of it. DeepSeek's largest factor opened, in that order, with
    "Sacrificing oneself for another is the highest act of love", and was duly
    called Self-preservation vs Heroic self-sacrifice; the items nearest its
    actual centre are about deception as survival, childhood damage and secrets
    kept. The namer named the corner it was shown.

    SPLIT BY POLE. An axis has two ends, and which end a proposition belongs to
    is its loading's SIGN — that is what reverse-keying means. The namer used to
    get one flat list and was asked to name both ends from it, which on the
    largest factor here meant 17 of 37 propositions asserting the opposite pole
    with nothing marking them. It was not reading a mislabelled axis; it was
    guessing the split and then naming its guess, which is why the same groups
    could come back coherent one hour and incoherent the next.

    ORDERED BY WEIGHT, NOT BY DISTANCE FROM THE CENTRE. Those are different
    measures and only one answers "what is this axis about". Distance is how far
    an item sits from its cluster's centroid across every factor; the LOADING is
    how strongly it defines THIS one. Ordered by distance, the proposition that
    most defines the leading axis — "the state has the right to take a person's
    life as punishment", loading +0.56 — appeared seventh, while "there is a
    right order that precedes individual choice", loading +0.17, was read as
    central because it happened to sit near a centroid.

    That matters because the namer is told to weight the opening lines most.
    Being shown a thematically obvious but statistically weak proposition first
    is how an axis gets named for something it is not chiefly measuring.

    The weight is shown as well as sorted on, so both the model and anyone
    reading the transcript can see that the top item counts three times what the
    bottom one does rather than inferring it from position.
    """
    weights = weights or {}
    out: dict[int, dict[bool, list[tuple[float, float, str]]]] = {}
    for item_id, factor in groups.items():
        text = texts.get(item_id)
        if not text:
            continue
        signed = (loading or {}).get(item_id, 1.0)
        weight = abs(weights.get(item_id, signed))
        bucket = out.setdefault(factor, {True: [], False: []})
        bucket[signed >= 0].append((-weight, weight, text))
    return {factor: ([(w, t) for _s, w, t in sorted(rows[True])],
                     [(w, t) for _s, w, t in sorted(rows[False])])
            for factor, rows in out.items()}


def name_factors(
    report: dict[str, Any], texts: dict[str, str], client=None,
    alias: str | None = None, sample: int = SAMPLE, progress=None,
) -> list[dict[str, Any]]:
    """Name each factor `latent.analyse` found. One call, all groups.

    One call rather than one per factor, so the namer sees the groups side by
    side. Shown a single group in isolation it will find a theme in anything and
    the names come back overlapping; shown all of them it has to tell them
    apart, which is the property the axes actually need.
    """
    alias = alias or report["scorer"]
    grouped = _items_by_factor(report["groups"], texts, report.get("distance"),
                               report.get("loading"), report.get("loading"))
    if not grouped:
        return []

    client = client or client_for(alias)
    blocks = []
    for factor, (high, low) in sorted(grouped.items()):
        def side(rows: list[tuple[float, str]], label: str) -> str:
            # Too faint to be evidence about what the axis is. They still COUNT
            # toward a film's position, where a hundred small weights add up;
            # they just should not be shown to something asked what the axis
            # means, where they read as equal in authority to a proposition
            # carrying three times their weight.
            strong = [r for r in rows if r[0] >= MIN_WEIGHT_TO_NAME]
            dropped = len(rows) - len(strong)
            if not strong:
                return (f"  {label}: none — every proposition in this group points "
                        f"one way." if not rows else
                        f"  {label}: {len(rows)} propositions, all too weakly "
                        f"related to this axis to characterise it.")
            shown = "\n".join(f"    [{w:.2f}] {text}" for w, text in strong[:sample])
            extra = (f"\n    ...and {len(strong) - sample} more, carrying less weight"
                     if len(strong) > sample else "")
            tail = (f"\n    ({dropped} further propositions omitted: weight below "
                    f"{MIN_WEIGHT_TO_NAME})" if dropped else "")
            return f"  {label} ({len(strong)} of {len(rows)}):\n{shown}{extra}{tail}"
        blocks.append(
            f"GROUP {factor} — {len(high) + len(low)} propositions, "
            f"most central first within each end\n"
            + side(high, "ONE END affirms these") + "\n"
            + side(low, "THE OTHER END affirms these"))

    result = client.parse(system=SYSTEM, user="\n\n".join(blocks),
                          output_model=FactorNames, max_tokens=16000)

    margins = report.get("margins") or []
    eigenvalues = report.get("eigenvalues") or []
    dominant = {int(k): int(v) for k, v in (report.get("dominant") or {}).items()}
    named = []
    for factor in result.factors:
        index = factor.factor_id
        if index not in grouped:
            continue  # a group the namer invented rather than read
        named.append({
            "factor_id": index,
            # Built, not taken. Written low-then-high so it reads in the same
            # order as the line a reader is shown, with the labels the code
            # assigned rather than whichever order the model chose.
            "name": f"{factor.second_label.strip()} vs {factor.first_label.strip()}",
            "question": factor.question.strip(),
            # The first list is the positive-loading end, so it is the HIGH
            # pole. Assigned here rather than asked for, and the name is built
            # from the labels rather than taken from the model — every previous
            # naming run wrote it in the opposite order from the one requested,
            # 24 times out of 25.
            "pole_high": factor.first.strip(),
            "pole_low": factor.second.strip(),
            "pole_high_label": factor.first_label.strip(),
            "pole_low_label": factor.second_label.strip(),
            "coherent": bool(factor.coherent),
            # Both ends. `grouped[index]` is a (one end, the other) pair now,
            # so len() of it is 2 — which is the count that briefly reached the
            # database and made every axis look like it rested on two
            # propositions.
            "n_items": sum(len(side) for side in grouped[index]),
            # The eigenvalue of the factor this GROUP loads on, not of the
            # group's arbitrary k-means label. Ordering the axes by the latter
            # put a cluster of eleven propositions at the top of the product
            # carrying the largest eigenvalue in the corpus by accident.
            "eigenvalue": (eigenvalues[dominant[index]]
                           if index in dominant and dominant[index] < len(eigenvalues)
                           else (eigenvalues[index] if index < len(eigenvalues) else None)),
            # And the margin of that same factor. This read `margins[index]`
            # while the line above read `eigenvalues[dominant[index]]`, so a
            # group carried one factor's eigenvalue beside another's margin —
            # and the product orders its axes by MARGIN. The 23-proposition
            # group was published as the corpus's most certain axis at +267%
            # while holding the third factor's eigenvalue of 4.69.
            "margin": (margins[dominant[index]]
                       if index in dominant and dominant[index] < len(margins)
                       else (margins[index] if index < len(margins) else None)),
        })
        if progress:
            mark = "" if factor.coherent else "  [yellow](would not cohere)[/]"
            progress(f"  {factor.second_label.strip()} vs "
                     f"{factor.first_label.strip()}{mark}")
    return named


def persist(
    alias: str, report: dict[str, Any], named: list[dict[str, Any]],
    bank_version: str = "b1", model: str | None = None, usage: dict[str, Any] | None = None,
) -> str:
    variant = report.get("variant") or "all"
    estimator = "strict"
    model = model or SCORERS[alias].model
    run_id = db.start_run(
        "factor-names", model, PROMPT_VERSION,
        {"scorer": alias, "variant": variant, "bank_version": bank_version,
         "n_factors": len(named), "films": report["films"], "items": report["items"]},
    )
    with db.connect() as con:
        for table in ("latent_factors", "latent_factor_items"):
            con.execute(f"DELETE FROM {table} WHERE scorer=? AND variant=? AND bank_version=?",
                        [alias, variant, bank_version])
        con.executemany(
            "INSERT INTO latent_factors (scorer, variant, bank_version, factor_id, name, "
            "question, pole_high, pole_low, pole_high_label, pole_low_label, coherent, "
            "estimator, n_items, eigenvalue, margin, model, run_id, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(alias, variant, bank_version, f["factor_id"], f["name"], f["question"],
              f["pole_high"], f["pole_low"], f.get("pole_high_label"), f.get("pole_low_label"),
              int(bool(f.get("coherent", True))), estimator, f["n_items"], f["eigenvalue"],
              f["margin"], model, run_id, db.now()) for f in named],
        )
        loadings = report.get("loading") or {}
        # `loading` is the signed value on the factor an item was FILED under.
        # `loadings` is every factor's, so a proposition that speaks to two axes
        # can count on both. Both are stored: direction still comes from the
        # first, weight now comes from the second.
        every = report.get("loadings") or {}
        con.executemany(
            "INSERT OR REPLACE INTO latent_factor_items (scorer, variant, bank_version, "
            "item_id, factor_id, loading, loadings) VALUES (?,?,?,?,?,?,?)",
            [(alias, variant, bank_version, item, factor, loadings.get(item),
              json.dumps(every[item]) if item in every else None)
             for item, factor in report["groups"].items()],
        )
    db.finish_run(run_id, usage or {})
    return run_id


def by_support(factor: dict[str, Any]) -> tuple[float, float, int, str, int]:
    """How well supported an axis is — the one ordering used everywhere.

    Three screens show these groups: the atlas, the compass a person gets, and
    a film's own reading. They were sorting differently, so the axis a reader
    met first changed depending on where they met it, and nothing on any of
    them explained why. One key, imported by all three.

    MARGIN first: how far the factor's eigenvalue clears the 95th percentile of
    a null built by permuting each proposition's own column. That is the
    directest statement of how sure we are the axis is there at all, and it is
    what a reader deserves to meet first.

    Not eigenvalue, which is a different question — how much of the corpus's
    variation a factor accounts for — and which on the current reading gives a
    different order outright: the axis clearing chance by 262% accounts for less
    variation than one clearing it by 24%. Size and certainty are not the same
    thing, and the ordering should promise certainty.

    Then eigenvalue, then the number of propositions behind it. Groups are
    matched to factors one-to-one, so these no longer separate facets of one
    factor from each other — they break ties between genuinely distinct
    factors that cleared the null by the same margin, which the corpus does
    produce.

    Then the name, and finally the factor's own id, so the order is TOTAL. Two
    axes equal on everything else would otherwise keep whatever order they
    arrived in — stable while one query feeds them, and silently different the
    day another does. A shared key is only shared if it decides every pair.
    """
    return (-(factor.get("margin") or 0.0),
            -(factor.get("eigenvalue") or 0.0),
            -(factor.get("n_items") or 0),
            str(factor.get("name") or ""),
            int(factor.get("factor_id") or 0))


def load(alias: str, variant: str = "subs", bank_version: str = "b1",
         min_margin: float | None = None) -> list[dict[str, Any]]:
    """Every named factor, strongest first by eigenvalue.

    `min_margin` still filters if a caller asks, but nothing does by default:
    each of these already cleared the null.
    """
    db.init_db()
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT factor_id, name, question, pole_high, pole_low, pole_high_label, "
            "pole_low_label, coherent, estimator, n_items, eigenvalue, margin, model "
            "FROM latent_factors "
            "WHERE scorer=? AND variant=? AND bank_version=? ORDER BY factor_id",
            [alias, variant, bank_version],
        ).fetchall()
    factors = sorted([_with_labels(dict(r)) for r in rows], key=by_support)
    if min_margin is None:
        return factors
    # A margin of None predates the measurement rather than failing it, so it is
    # kept: dropping it would hide axes for being old.
    return [f for f in factors if f["margin"] is None or f["margin"] >= min_margin]


def _with_labels(factor: dict[str, Any]) -> dict[str, Any]:
    """Fill in pole labels for rows named before the convention existed.

    A name like "Moral relativism vs. absolute values" already carries both ends;
    splitting it is exact when it is written that way and harmless when it is
    not, because the fallback is the axis name itself rather than a guess.
    """
    if factor.get("pole_high_label") and factor.get("pole_low_label"):
        factor["coherent"] = None if factor["coherent"] is None else bool(factor["coherent"])
        return factor
    name = (factor.get("name") or "").strip()
    low, high = None, None
    for separator in (" vs. ", " vs ", " versus ", " or "):
        if separator in name.lower():
            index = name.lower().index(separator)
            low, high = name[:index].strip(), name[index + len(separator):].strip()
            break
    factor["pole_low_label"] = factor.get("pole_low_label") or low or name
    factor["pole_high_label"] = factor.get("pole_high_label") or high or name
    factor["coherent"] = None if factor.get("coherent") is None else bool(factor["coherent"])
    return factor


def bank_texts(bank_version: str = "b1") -> dict[str, str]:
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT item_id, text FROM item_bank WHERE bank_version=? AND active=1",
            [bank_version],
        ).fetchall()
    return {r["item_id"]: r["text"] for r in rows}


def estimator_for(alias: str, variant: str = "subs", bank_version: str = "b1") -> str:
    """Which reading produced the stored factors, so the detail can match it.

    The names live in the database and the groups behind them are recomputed on
    demand. If those two disagree about how to read the responses, every axis
    gets a name from one clustering and its propositions from another — which
    looks exactly like a mislabelled axis and raises no error at all.
    """
    db.init_db()
    with db.connect(read_only=True) as con:
        row = con.execute(
            "SELECT estimator FROM latent_factors WHERE scorer=? AND variant=? "
            "AND bank_version=? LIMIT 1", [alias, variant, bank_version],
        ).fetchone()
    return (row["estimator"] if row and row["estimator"] else "dense")
