"""The source A/B: does the evidence you feed it change the answer?

This is the $10 experiment. Same films, same propositions, different evidence
conditions — measured rather than argued about.

The headline splits disagreement into two kinds, because they mean very
different things:

    FLIP     both conditions took a position and they took OPPOSITE positions.
             The cheap source is not merely thin, it is WRONG. Flips are
             corrupt data and they poison a factor analysis silently.

    SILENCE  one condition took a position and the other did not engage at all.
             The cheap source is thin, not wrong. This is missing data, which
             the salience mask already models honestly.

A 20% disagreement rate made almost entirely of silence is a very different
verdict from a 20% rate made of flips. The first says "summaries are shallow but
sound"; the second says "summaries are actively misleading" — and only the
second justifies processing subtitles for the whole corpus.
"""
from __future__ import annotations

import itertools
from collections import defaultdict
from typing import Any

from .. import db


def _score_map(bank_version: str, run_id: str | None = None) -> dict[str, dict[str, dict[str, int]]]:
    """{film_id: {variant: {item_id: value}}} for the most recent scoring run."""
    q = ("SELECT film_id, variant, item_id, value FROM scores WHERE bank_version=?")
    args: list[Any] = [bank_version]
    if run_id:
        q += " AND run_id=?"
        args.append(run_id)

    out: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(dict))
    with db.connect(read_only=True) as con:
        for film_id, variant, item_id, value in con.execute(q, args).fetchall():
            out[film_id][variant][item_id] = int(value)
    return out


def compare(
    bank_version: str, reference: str = "subs", run_id: str | None = None,
) -> dict[str, Any]:
    """Compare every variant against the reference condition.

    `subs` is the reference because it is the only condition with no summariser
    between the film and the model.
    """
    data = _score_map(bank_version, run_id)

    variants: set[str] = set()
    for per_variant in data.values():
        variants.update(per_variant)
    others = sorted(v for v in variants if v != reference)

    report: dict[str, Any] = {
        "bank_version": bank_version,
        "reference": reference,
        "n_films": 0,
        "variants": {},
        "per_item": {},
    }

    item_stats: dict[str, dict[str, int]] = defaultdict(
        lambda: {"flip": 0, "silence": 0, "agree": 0}
    )

    for variant in others:
        agree = flip = silence_ref_only = silence_var_only = 0
        films_compared = 0
        per_film: dict[str, dict[str, int]] = {}

        for film_id, per_variant in data.items():
            ref = per_variant.get(reference)
            cur = per_variant.get(variant)
            if not ref or not cur:
                continue
            films_compared += 1
            f_agree = f_flip = f_sil = 0

            for item_id in set(ref) | set(cur):
                a, b = ref.get(item_id), cur.get(item_id)
                if a is not None and b is not None:
                    if a == b:
                        agree += 1; f_agree += 1
                        item_stats[item_id]["agree"] += 1
                    else:
                        flip += 1; f_flip += 1
                        item_stats[item_id]["flip"] += 1
                elif a is not None:
                    silence_ref_only += 1; f_sil += 1
                    item_stats[item_id]["silence"] += 1
                else:
                    silence_var_only += 1; f_sil += 1
                    item_stats[item_id]["silence"] += 1

            per_film[film_id] = {"agree": f_agree, "flip": f_flip, "silence": f_sil}

        both = agree + flip
        union = both + silence_ref_only + silence_var_only
        report["variants"][variant] = {
            "films_compared": films_compared,
            "items_both_engaged": both,
            "agree": agree,
            "flip": flip,
            "missed_by_this_variant": silence_ref_only,
            "extra_in_this_variant": silence_var_only,
            # Of the items where BOTH took a position, how often did they
            # contradict each other. This is the number that decides the project.
            "flip_rate": round(flip / both, 4) if both else None,
            # Of what the reference engaged, how much this variant simply missed.
            "silence_rate": round(
                silence_ref_only / (agree + flip + silence_ref_only), 4
            ) if (agree + flip + silence_ref_only) else None,
            "overall_disagreement": round((flip + silence_ref_only + silence_var_only) / union, 4)
            if union else None,
            "verdict": _verdict(flip / both if both else 0.0),
            "per_film": per_film,
        }

    report["n_films"] = len(data)
    report["per_item"] = {
        item_id: {
            **stats,
            "flip_rate": round(stats["flip"] / (stats["flip"] + stats["agree"]), 3)
            if (stats["flip"] + stats["agree"]) else None,
        }
        for item_id, stats in item_stats.items()
    }
    return report


def _verdict(flip_rate: float) -> str:
    if flip_rate < 0.10:
        return ("summaries agree with the film's own words — use the cheap source "
                "for the sweep and spend the budget elsewhere")
    if flip_rate < 0.25:
        return ("mixed — fetch subtitles for the propositions listed in "
                "summary_resistant_items, keep summaries for the rest")
    return ("summaries are actively misleading at this rate — subtitles required "
            "for the whole corpus")


def summary_resistant_items(report: dict[str, Any], top: int = 25) -> list[dict[str, Any]]:
    """Propositions the cheap sources get WRONG most often.

    The practically useful output: if the overall rate lands in the middle, these
    are the items worth paying for subtitles on, and the rest can ride on the
    summary.
    """
    rows = [
        {"item_id": k, **v} for k, v in report["per_item"].items()
        if v.get("flip_rate") is not None and (v["flip"] + v["agree"]) >= 3
    ]
    rows.sort(key=lambda r: (-r["flip_rate"], -r["flip"]))

    with db.connect(read_only=True) as con:
        texts = dict(con.execute(
            "SELECT item_id, text FROM item_bank WHERE bank_version=?",
            [report["bank_version"]],
        ).fetchall())
    for r in rows:
        r["text"] = texts.get(r["item_id"], "?")
    return rows[:top]


def displacement(
    bank_version: str, parent_id: str, child_id: str, run_id: str | None = None,
) -> dict[str, Any]:
    """The targeted editor-bias probe.

    A revision and its source text have Wikipedia summaries written by different
    fandoms. If editor slant is large anywhere it is largest there, and it would
    show up as a displacement vector that is bigger measured from summaries than
    measured from the films' own dialogue.
    """
    data = _score_map(bank_version, run_id)
    out: dict[str, Any] = {"parent": parent_id, "child": child_id, "by_variant": {}}

    for variant in ("spine", "spine_themes", "subs", "full"):
        p = data.get(parent_id, {}).get(variant)
        c = data.get(child_id, {}).get(variant)
        if not p or not c:
            continue
        shared = set(p) & set(c)
        if not shared:
            continue
        moved = [i for i in shared if p[i] != c[i]]
        out["by_variant"][variant] = {
            "shared_items": len(shared),
            "moved": len(moved),
            # Magnitude of the moral displacement between source and retelling.
            "displacement": round(
                sum(abs(p[i] - c[i]) for i in shared) / (2 * len(shared)), 4
            ),
            "flipped_items": moved[:20],
        }

    mags = {v: d["displacement"] for v, d in out["by_variant"].items()}
    if "spine" in mags and "subs" in mags and mags["subs"]:
        out["summary_inflation"] = round(mags["spine"] / mags["subs"], 3)
        out["reading"] = (
            "summary exaggerates the moral distance between source and retelling"
            if out["summary_inflation"] > 1.15 else
            "summary understates the moral distance"
            if out["summary_inflation"] < 0.85 else
            "summary and dialogue agree on the size of the displacement"
        )
    return out


def coverage(bank_version: str, run_id: str | None = None) -> list[dict[str, Any]]:
    """How many items each variant engaged, per film.

    A variant engaging far fewer items is thin rather than wrong; read this
    alongside flip_rate before concluding anything.
    """
    data = _score_map(bank_version, run_id)
    rows = []
    for film_id, per_variant in sorted(data.items()):
        row: dict[str, Any] = {"film_id": film_id}
        for variant, items in per_variant.items():
            row[variant] = len(items)
        rows.append(row)
    return rows
