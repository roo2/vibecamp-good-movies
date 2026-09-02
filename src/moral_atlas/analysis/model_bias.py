"""Whose morals are in the scores?

The atlas rests on a claim it has never tested: that when a model reads a film
and votes on 694 moral propositions, the verdict is a property of the film. Every
number in the database came from one model — `claude-opus-5` — so an equally good
explanation of the whole corpus is that we have measured the moral opinions of
one model, carefully, forty times.

The design that separates those two explanations is a substitution. The bank, the
evidence packet, the rubric and the film are held byte-identical; only the scorer
changes. What survives is the film. What moves is the scorer.

Four things get measured, and they answer different questions:

    ENGAGEMENT   how many items each scorer thinks the film takes a position on
                 at all. A model that engages half as much is not more careful,
                 it is measuring something narrower, and everything downstream
                 inherits that.
    REFUSAL      how often a scorer declines. This is the guardrail question put
                 directly: a model that will not say what Schindler's List
                 argues about obedience has not given a neutral answer, it has
                 given a missing one, and missingness is not evenly distributed
                 across the moral axes.
    AGREEMENT    Cohen's kappa on the (film, item) cells two scorers both voted
                 on. Chance-corrected because the verdicts are lopsided —
                 roughly two affirms per denial — so raw agreement flatters any
                 pair of models that mostly say "affirms".
    LEAN         the interesting one. Averaging each scorer's polarity-adjusted
                 verdicts within a moral axis gives the direction that scorer
                 pushes the corpus as a whole. If two models read the same forty
                 films and one lands the corpus systematically higher on
                 "Conscience Against the Rules", that difference cannot be a
                 property of the films, because the films were identical.

LEAN is reported per axis and as a difference from the incumbent, because the
absolute number is not meaningful on its own — a corpus of forty mostly-humanist
films should lean humanist for everybody. Only the gap between scorers reading
the same corpus isolates the scorer.

Nothing here writes to `scores`. See the comment on `model_verdicts` in db.py:
an audit that moves the thing it audits is worthless.
"""
from __future__ import annotations

import statistics as st
from collections import defaultdict
from typing import Any, Iterable

from .. import db
from ..config import PROMPT_VERSION
from ..llm import prompts
from ..llm.providers import Refusal, SCORERS, client_for
from ..llm.schemas import VERDICT_TO_INT, ScoreSet
from ..sources import packet as packet_mod
from . import dimensions as dim_mod

INCUMBENT = "opus"


# --------------------------------------------------------------------------
# Running a scorer over the corpus
# --------------------------------------------------------------------------

# How many propositions one call is asked to judge. A verdict is an act of
# attention, and a call asked for three hundred of them at once spends very
# little on each; at forty the model can weigh a proposition against the film
# rather than skim it. Above the bank size this does nothing, so a small bank
# still runs in one call and the old cache arrangement still applies.
BATCH_ITEMS = 40


def _slices(items: list[dict[str, Any]], size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def scan(
    alias: str, film_ids: Iterable[str], bank_version: str = "b1",
    variant: str = "spine", client=None, progress=None,
    batch_size: int | None = None,
) -> dict[str, Any]:
    """Score every film with one scorer, into `model_verdicts`.

    The prompt is `prompts.scoring_system` unchanged. That is the whole point:
    if the comparison used a prompt tuned per model, the differences it found
    would be differences between prompts.
    """
    scorer = SCORERS[alias]
    items = _bank(bank_version)
    if not items:
        raise RuntimeError(f"item bank {bank_version!r} is empty — run `atlas bank` first")
    system = prompts.scoring_system("\n".join(f"{i['item_id']}. {i['text']}" for i in items))
    valid = {i["item_id"] for i in items}

    packets = [p for p in (packet_mod.build(film_id, variant) for film_id in film_ids) if p.usable]
    if not packets:
        raise RuntimeError(f"no usable {variant!r} packets for those films")

    client = client or client_for(alias)
    run_id = db.start_run(
        "model-bias", scorer.model, PROMPT_VERSION,
        {"scorer": alias, "bank_version": bank_version, "variant": variant,
         "n_films": len(packets), "n_items": len(items)},
    )
    stats = {"scorer": alias, "model": scorer.model, "run_id": run_id,
             "films": len(packets), "scored": 0, "refused": 0, "failed": 0,
             # Propositions that were asked about twice and answered neither
             # time. Reported rather than absorbed: unanswered is not silence.
             "unanswered": 0, "lost_slices": 0,
             # Films the call succeeded for that produced NO verdicts at all.
             # These counted as "scored" and wrote nothing, so a run could
             # report "scored 25, refused 0, failed 0" while four films silently
             # entered the corpus unmeasured. Zero engagement is occasionally
             # real, but it is far more often transient — all four seen doing it
             # scored normally on a retry — so it is surfaced, not absorbed.
             "empty": [] }

    batched = bool(batch_size) and len(items) > batch_size

    def work(p):
        if not batched:
            return p, client.parse(system=system, user=_user_block(p),
                                   output_model=ScoreSet, max_tokens=16000)
        # The film is the cached prefix here and the propositions vary, which is
        # the reverse of the single-call path — see `scoring_batched_system`.
        # These slices run in SEQUENCE deliberately: the second call is what
        # makes the first one's evidence cheap, and issuing them together would
        # have every one of them miss. Concurrency is across films, above.
        film_system = prompts.scoring_batched_system(_user_block(p))

        def ask(part):
            listing = "\n".join(f"{i['item_id']}. {i['text']}" for i in part)
            return client.parse(
                system=film_system,
                user=f"Judge these {len(part)} propositions:\n\n{listing}",
                output_model=ScoreSet,
                # 40 verdicts with evidence strings overran 8000 and the reply
                # was cut mid-object, which surfaces as "no usable structured
                # output" rather than as truncation.
                max_tokens=16000,
            ).scores

        collected = []
        for part in _slices(items, batch_size):
            # A slice that fails must not take the film down with it. One bad
            # slice used to raise out of `work` and mark the whole packet
            # failed, discarding every slice that had already succeeded — in one
            # 150-film run that turned scattered slice errors into 58 lost
            # films, most of which had 19 good slices in hand.
            try:
                scores = ask(part)
            except Exception as error:
                stats["lost_slices"] += 1
                stats["unanswered"] += len(part)
                if progress:
                    # The TYPE alone is not a diagnosis. Printing only
                    # "HTTPStatusError" across 1,682 dropped slices said nothing
                    # about which HTTP error, which is the whole question.
                    progress(f"[yellow]{p.film_id}: slice of {len(part)} failed, "
                             f"keeping the rest — {type(error).__name__}: "
                             f"{str(error)[:160]}[/]")
                continue
            # A slice that comes back short is the one failure mode this
            # arrangement adds, and it is silent: an item the model simply
            # omitted is indistinguishable downstream from one it judged
            # `not_addressed`, which is exactly the ambiguity `not_addressed`
            # was introduced to remove. Measured on Troy, one slice of 40 came
            # back with 34. So ask again for what is missing, and count what
            # never arrives rather than letting it read as silence.
            answered = {s.item_id for s in scores}
            missing = [i for i in part if i["item_id"] not in answered]
            if missing:
                for s in ask(missing):
                    if s.item_id not in answered:
                        scores.append(s)
                        answered.add(s.item_id)
                still = [i for i in missing if i["item_id"] not in answered]
                stats["unanswered"] += len(still)
                if still and progress:
                    progress(f"[yellow]{p.film_id}: {len(still)} of {len(part)} "
                             f"never answered[/]")
            collected.extend(scores)
        return p, ScoreSet(scores=collected)

    def save(_p, result):
        p, scoreset = result
        # `not_addressed` is dropped rather than stored as zero: absence is
        # recorded by the row not existing, which is what every reader expects.
        # It is offered to the model anyway, because the alternative — hoping it
        # stays silent — produced denials whose own evidence read "Not relevant."
        rows = [(alias, scorer.model, p.film_id, s.item_id, bank_version, variant, run_id,
                 VERDICT_TO_INT[s.verdict], s.confidence, s.evidence, db.now())
                for s in scoreset.scores
                if s.item_id in valid and VERDICT_TO_INT.get(s.verdict)]
        with db.connect() as con:
            # Clear this film's previous verdicts first. INSERT OR REPLACE only
            # touches rows the new run writes, so an item the model used to
            # answer and now calls `not_addressed` kept its old verdict — and a
            # re-scored film silently became a mixture of two runs. Measured on
            # a six-film trial: 162 of 570 rows were survivors of the run before.
            con.execute(
                "DELETE FROM model_verdicts WHERE scorer=? AND film_id=? "
                "AND bank_version=? AND variant=?",
                [alias, p.film_id, bank_version, variant],
            )
            con.executemany(
                "INSERT OR REPLACE INTO model_verdicts (scorer, model, film_id, item_id, "
                "bank_version, variant, run_id, value, confidence, evidence, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows,
            )
        stats["scored"] += 1
        if not rows:
            stats["empty"].append(p.film_id)
        if progress:
            progress(f"{alias:<12} {p.film_id:<28} {len(rows):>3}/{len(items)} engaged")

    def failed(p, error):
        refused = isinstance(error, Refusal)
        stats["refused" if refused else "failed"] += 1
        with db.connect() as con:
            con.execute(
                "INSERT INTO model_refusals (scorer, model, film_id, variant, run_id, "
                "detail, created_at) VALUES (?,?,?,?,?,?,?)",
                [alias, scorer.model, p.film_id, variant, run_id,
                 f"{type(error).__name__}: {error}"[:500], db.now()],
            )
        if progress:
            progress(f"[{'yellow' if refused else 'red'}]"
                     f"{'REFUSED' if refused else 'FAILED'}[/]   {alias:<12} {p.film_id}")

    client.map(packets, work, on_result=save, on_error=failed)
    db.finish_run(run_id, client.usage.as_dict())
    stats["usage"] = client.usage.as_dict()
    return stats


def _bank(bank_version: str) -> list[dict[str, Any]]:
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT item_id, text FROM item_bank WHERE bank_version=? AND active "
            "ORDER BY item_id", [bank_version],
        ).fetchall()
    return [{"item_id": r["item_id"], "text": r["text"]} for r in rows]


def _user_block(p) -> str:
    from ..llm.stages import _user_block as build
    return build(p)


# --------------------------------------------------------------------------
# Reading the verdicts back
# --------------------------------------------------------------------------

def verdicts(bank_version: str = "b1") -> dict[str, dict[tuple[str, str], int]]:
    """{scorer: {(film, item): value}}, with the incumbent read from `scores`.

    The incumbent's existing rows live in `scores` and are not re-run: it has
    already scored the corpus, and paying to do it again would only add
    sampling noise to the one column we have most of.
    """
    db.init_db()  # the audit tables postdate most databases; read-only cannot create them
    out: dict[str, dict[tuple[str, str], int]] = defaultdict(dict)
    with db.connect(read_only=True) as con:
        for row in con.execute(
            "SELECT scorer, film_id, item_id, value FROM model_verdicts WHERE bank_version=?",
            [bank_version],
        ):
            out[row["scorer"]][(row["film_id"], row["item_id"])] = row["value"]
        for row in con.execute(
            "SELECT film_id, item_id, value FROM scores WHERE bank_version=?", [bank_version],
        ):
            out[INCUMBENT].setdefault((row["film_id"], row["item_id"]), row["value"])
    return dict(out)


def refusal_counts(bank_version: str = "b1") -> dict[str, int]:
    db.init_db()
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT r.scorer, COUNT(*) n FROM model_refusals r GROUP BY r.scorer"
        ).fetchall()
    return {row["scorer"]: row["n"] for row in rows}


def report(
    bank_version: str = "b1", dim_version: str = "d1", scorers: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Engagement, refusals, pairwise agreement and per-axis lean, as data."""
    seen = verdicts(bank_version)
    if scorers:
        seen = {alias: cells for alias, cells in seen.items() if alias in scorers}
    if not seen:
        raise RuntimeError("no verdicts yet — run `atlas model-scan` first")

    assignments = dim_mod.load_assignments(dim_version, bank_version, dim_mod.MAIN_PASS)
    names = {d["dim_id"]: d["name"] for d in dim_mod.load_dimensions(dim_version)}
    refusals = refusal_counts(bank_version)

    out: dict[str, Any] = {
        "bank_version": bank_version, "dim_version": dim_version,
        "incumbent": INCUMBENT, "scorers": {}, "agreement": {}, "lean": {}, "divergence": [],
    }

    for alias, cells in sorted(seen.items()):
        films = {film for film, _item in cells}
        out["scorers"][alias] = {
            "posture": SCORERS[alias].posture if alias in SCORERS else "unknown",
            "films": len(films),
            "verdicts": len(cells),
            "items_per_film": round(len(cells) / len(films), 1) if films else 0,
            "affirm_share": round(sum(1 for v in cells.values() if v > 0) / len(cells), 3) if cells else None,
            "refusals": refusals.get(alias, 0),
        }

    # -- pairwise agreement, on the cells both scorers actually voted on ----
    aliases = sorted(seen)
    for i, a in enumerate(aliases):
        for b in aliases[i + 1:]:
            shared = set(seen[a]) & set(seen[b])
            if not shared:
                continue
            agreed = sum(1 for cell in shared if seen[a][cell] == seen[b][cell])
            kappa = dim_mod.cohens_kappa(
                {str(c): seen[a][c] for c in shared}, {str(c): seen[b][c] for c in shared})
            out["agreement"][f"{a} vs {b}"] = {
                "shared_cells": len(shared),
                "raw": round(agreed / len(shared), 3),
                "kappa": round(kappa["kappa"], 3) if kappa["kappa"] is not None else None,
            }

    # -- per-axis lean, and the gap from the incumbent ---------------------
    for alias, cells in seen.items():
        by_axis: dict[int, list[float]] = defaultdict(list)
        for (_film, item), value in cells.items():
            assignment = assignments.get(item)
            if assignment:
                by_axis[assignment["dim_id"]].append(assignment["polarity"] * value)
        out["lean"][alias] = {
            names.get(dim_id, str(dim_id)): {"lean": round(st.mean(values), 3), "n": len(values)}
            for dim_id, values in sorted(by_axis.items())
        }

    base = out["lean"].get(INCUMBENT, {})
    for alias, axes in out["lean"].items():
        if alias == INCUMBENT:
            continue
        for axis, row in axes.items():
            if axis in base:
                out["divergence"].append({
                    "scorer": alias, "axis": axis,
                    "gap": round(row["lean"] - base[axis]["lean"], 3),
                    "scorer_lean": row["lean"], "incumbent_lean": base[axis]["lean"],
                    "n": row["n"],
                })
    out["divergence"].sort(key=lambda row: -abs(row["gap"]))
    return out
