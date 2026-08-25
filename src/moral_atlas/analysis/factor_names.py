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

from typing import Any

from pydantic import BaseModel, Field

from .. import db
from ..config import PROMPT_VERSION
from ..llm.providers import SCORERS, client_for

# Enough of a group to characterise it without paying for all of it. Groups run
# to sixty items, and where there is a shared thread it is visible in far fewer;
# where there is not, more items would not rescue it.
SAMPLE = 40

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
    name: str = Field(description="The axis as 'A vs B', naming both ends.")
    question: str = Field(description="The moral question these share, as one sentence.")
    pole_high_label: str = Field(
        description="The affirming end as 1-3 words, e.g. 'Heroic self-sacrifice'.")
    pole_low_label: str = Field(
        description="The denying end as 1-3 words, and a real position rather "
                    "than a negation, e.g. 'Self-preservation' not 'Not heroic'.")
    pole_high: str = Field(description="What affirming these propositions asserts.")
    pole_low: str = Field(description="What denying them asserts.")
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

The propositions are listed with the ones NEAREST THE CENTRE of the group first.
Weight them accordingly: the opening lines are what the group is most about, and
a striking phrase further down is not the theme just because it is striking. If
the central propositions and the tail describe different things, that is a group
with no single theme, and coherent=false is the honest answer.

An axis has two ends and both of them are positions somebody holds. Name it so a
reader can see what it runs BETWEEN, because they will be shown their own place
on it as a point on a line, and a line has to be labelled at both ends.

  - `pole_high_label` and `pole_low_label` are those two ends, 1-3 words each.
    The low end must be a position in its own right, never the absence or the
    negation of the high one: "Self-preservation", not "Not self-sacrificing";
    "Absolute values", not "Non-relativist". If you cannot name the low end as
    something a person would own, you have probably named the high end as a
    topic rather than a stance — reword both.
  - `name` is the axis itself, written "<low> vs <high>" from those two labels,
    e.g. "Self-preservation vs heroic self-sacrifice".
  - `question` is the axis as a question with two defensible sides, not a topic.
  - `pole_high` and `pole_low` say, in a sentence each, what a work at that end
    claims. Phrase both so that someone holding that view would accept the
    wording as fair.

You did not choose these groupings and you are not being asked to improve them.
If a group's propositions genuinely do not share a moral question, set
coherent=false and give the closest description you can. A statistical factor
that resists naming is a real and useful outcome — do not manufacture a theme to
cover one.
"""


def _items_by_factor(
    groups: dict[str, int], texts: dict[str, str],
    distance: dict[str, float] | None = None,
) -> dict[int, list[str]]:
    """Each factor's propositions, nearest the centre of the group first.

    The order is the whole point, and getting it wrong produced a real bad name.
    These used to be sorted by item_id — which is bank insertion order, so the
    slice a namer saw was an arbitrary corner of the cluster rather than a
    reading of it. DeepSeek's largest factor opened, in that order, with
    "Sacrificing oneself for another is the highest act of love", and was duly
    called Self-preservation vs Heroic self-sacrifice; the items nearest its
    actual centre are about deception as survival, childhood damage and secrets
    kept. The namer named the corner it was shown.

    Sorted by distance to the group's centre, the sample is what the factor is
    most about, and a name that does not fit it is a name that does not fit.
    """
    out: dict[int, list[tuple[float, str]]] = {}
    for item_id, factor in groups.items():
        text = texts.get(item_id)
        if text:
            out.setdefault(factor, []).append(((distance or {}).get(item_id, 0.0), text))
    return {factor: [text for _d, text in sorted(rows)] for factor, rows in out.items()}


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
    grouped = _items_by_factor(report["groups"], texts, report.get("distance"))
    if not grouped:
        return []

    client = client or client_for(alias)
    blocks = []
    for factor, items in sorted(grouped.items()):
        listing = "\n".join(f"  - {text}" for text in items[:sample])
        more = (f"\n  ...and {len(items) - sample} more, further from the centre"
                if len(items) > sample else "")
        blocks.append(f"GROUP {factor} ({len(items)} propositions, most central first)"
                      f"\n{listing}{more}")

    result = client.parse(system=SYSTEM, user="\n\n".join(blocks),
                          output_model=FactorNames, max_tokens=16000)

    margins = report.get("margins") or []
    eigenvalues = report.get("eigenvalues") or []
    named = []
    for factor in result.factors:
        index = factor.factor_id
        if index not in grouped:
            continue  # a group the namer invented rather than read
        named.append({
            "factor_id": index,
            "name": factor.name.strip(),
            "question": factor.question.strip(),
            "pole_high": factor.pole_high.strip(),
            "pole_low": factor.pole_low.strip(),
            "pole_high_label": factor.pole_high_label.strip(),
            "pole_low_label": factor.pole_low_label.strip(),
            "coherent": bool(factor.coherent),
            "n_items": len(grouped[index]),
            "eigenvalue": eigenvalues[index] if index < len(eigenvalues) else None,
            "margin": margins[index] if index < len(margins) else None,
        })
        if progress:
            mark = "" if factor.coherent else "  [yellow](would not cohere)[/]"
            progress(f"  {factor.name}{mark}")
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
        con.executemany(
            "INSERT OR REPLACE INTO latent_factor_items (scorer, variant, bank_version, "
            "item_id, factor_id, loading) VALUES (?,?,?,?,?,?)",
            [(alias, variant, bank_version, item, factor, loadings.get(item))
             for item, factor in report["groups"].items()],
        )
    db.finish_run(run_id, usage or {})
    return run_id


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
    factors = sorted([_with_labels(dict(r)) for r in rows],
                     key=lambda f: -(f["eigenvalue"] or 0))
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
