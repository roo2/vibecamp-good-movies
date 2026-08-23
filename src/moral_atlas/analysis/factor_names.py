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
SAMPLE = 28


class FactorName(BaseModel):
    factor_id: int
    name: str = Field(description="2-4 words, plain English, no jargon.")
    question: str = Field(description="The moral question these share, as one sentence.")
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

  - `name` is 2-4 plain words a non-specialist would understand at a glance.
  - `question` is the axis as a question with two defensible sides, not a topic.
  - `pole_high` is what a work affirming these propositions claims; `pole_low`
    is what a work denying them claims. Phrase both so that someone holding that
    view would accept the wording as fair.

You did not choose these groupings and you are not being asked to improve them.
If a group's propositions genuinely do not share a moral question, set
coherent=false and give the closest description you can. A statistical factor
that resists naming is a real and useful outcome — do not manufacture a theme to
cover one.
"""


def _items_by_factor(groups: dict[str, int], texts: dict[str, str]) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for item_id, factor in sorted(groups.items()):
        text = texts.get(item_id)
        if text:
            out.setdefault(factor, []).append(text)
    return out


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
    grouped = _items_by_factor(report["groups"], texts)
    if not grouped:
        return []

    client = client or client_for(alias)
    blocks = []
    for factor, items in sorted(grouped.items()):
        listing = "\n".join(f"  - {text}" for text in items[:sample])
        more = f"\n  ...and {len(items) - sample} more" if len(items) > sample else ""
        blocks.append(f"GROUP {factor} ({len(items)} propositions)\n{listing}{more}")

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
            "question, pole_high, pole_low, n_items, eigenvalue, margin, model, run_id, "
            "created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(alias, variant, bank_version, f["factor_id"], f["name"], f["question"],
              f["pole_high"], f["pole_low"], f["n_items"], f["eigenvalue"], f["margin"],
              model, run_id, db.now()) for f in named],
        )
        con.executemany(
            "INSERT OR REPLACE INTO latent_factor_items (scorer, variant, bank_version, "
            "item_id, factor_id) VALUES (?,?,?,?,?)",
            [(alias, variant, bank_version, item, factor)
             for item, factor in report["groups"].items()],
        )
    db.finish_run(run_id, usage or {})
    return run_id


def load(alias: str, variant: str = "subs", bank_version: str = "b1") -> list[dict[str, Any]]:
    db.init_db()
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT factor_id, name, question, pole_high, pole_low, n_items, eigenvalue, "
            "margin, model FROM latent_factors WHERE scorer=? AND variant=? AND bank_version=? "
            "ORDER BY factor_id", [alias, variant, bank_version],
        ).fetchall()
    return [dict(r) for r in rows]


def bank_texts(bank_version: str = "b1") -> dict[str, str]:
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT item_id, text FROM item_bank WHERE bank_version=? AND active=1",
            [bank_version],
        ).fetchall()
    return {r["item_id"]: r["text"] for r in rows}
