"""Does the moral structure survive changing the model that found it?

The scoring audit in `model_bias` holds the bank fixed and swaps the scorer. That
tests the last step and takes the first two on trust — but the propositions were
written by one model, and the axes were derived by one model reading that
model's writing. If the eight axes are a fact about films, another model reading
the same forty films should find something recognisably similar. If they are a
fact about Claude, it should not.

Three stages, mirroring the pipeline, each cut once per model:

    HARVEST   the same prompt, the same evidence, the same films — write the
              moral propositions this film takes a position on.
    DERIVE    each model reads ITS OWN harvest and names n axes in it. Its own,
              deliberately: asking a model to find axes in Claude's propositions
              would test reading comprehension, not moral structure.
    ASSIGN    each model then places the SHARED b1 bank on its own axes.

That last stage is what makes the comparison statistical rather than impressionistic.
Two models' axis *names* cannot be compared — "Payback or Mercy" and "Justice and
Forgiveness" might be the same axis or might not, and deciding by eye is exactly
the kind of judgement this project exists to replace. But once both models have
sorted the identical 694 items into their own boxes, the two partitions are
comparable without reference to any label at all:

    ARI / NMI     do the models group the same items together, correcting for
                  the agreement any two partitions of the same size get free?
    HUNGARIAN     which axis of A corresponds to which axis of B, matched by
                  item overlap rather than by name, and how good is the match?
    K-SWEEP       run the whole thing at k = 4, 6, 8, 10, 12. If eight axes are
                  really in the material, cross-model agreement should peak
                  near eight. If agreement is flat in k, then "eight" was a
                  number we supplied and the models politely returned.

The k-sweep is the honest form of "do eight clusters emerge". Nobody can ask an
LLM "how many axes are there?" and trust the answer — it will produce whatever
number it is asked for, which is why `derive_system` takes n_dims. Asking instead
at which k independent models most agree turns an unanswerable question into a
measurable one.

Everything writes to `model_*` tables and never to the atlas proper.
"""
from __future__ import annotations

import random
import statistics as st
import uuid
from collections import defaultdict
from typing import Any, Iterable

from .. import db
from ..config import PROMPT_VERSION
from ..llm import prompts
from ..llm.providers import SCORERS, client_for
from ..llm.schemas import PropositionSet
from ..sources import packet as packet_mod
from . import dimensions as dim_mod

SHARED_BANK = "b1"


# --------------------------------------------------------------------------
# Stage 1 — harvest propositions, one model at a time
# --------------------------------------------------------------------------

def harvest(
    alias: str, film_ids: Iterable[str], variant: str = "full",
    client=None, progress=None,
) -> dict[str, Any]:
    """Run the unchanged harvesting prompt under one model."""
    db.init_db()  # the model_* tables postdate most databases
    scorer = SCORERS[alias]
    packets = [p for p in (packet_mod.build(f, variant) for f in film_ids) if p.usable]
    if not packets:
        raise RuntimeError(f"no usable {variant!r} packets for those films")

    client = client or client_for(alias)
    run_id = db.start_run(
        "model-propose", scorer.model, PROMPT_VERSION,
        {"scorer": alias, "variant": variant, "n_films": len(packets)},
    )
    stats = {"scorer": alias, "model": scorer.model, "run_id": run_id,
             "films": len(packets), "propositions": 0, "failed": 0}

    def work(p):
        return p, client.parse(system=prompts.PROPOSITIONS_SYSTEM,
                               user=_user_block(p), output_model=PropositionSet,
                               max_tokens=8000)

    def save(_p, result):
        p, harvested = result
        with db.connect() as con:
            con.executemany(
                "INSERT OR REPLACE INTO model_propositions (scorer, model, prop_id, film_id, "
                "variant, run_id, text, stance, prompt_version, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                [(alias, scorer.model, uuid.uuid4().hex[:16], p.film_id, variant, run_id,
                  prop.text, prop.stance, PROMPT_VERSION, db.now())
                 for prop in harvested.propositions],
            )
        stats["propositions"] += len(harvested.propositions)
        if progress:
            progress(f"{alias:<10} {p.film_id:<28} {len(harvested.propositions)} statements")

    def failed(p, error):
        stats["failed"] += 1
        if progress:
            progress(f"[red]FAILED[/]   {alias:<10} {p.film_id}  {type(error).__name__}: {error}")

    client.map(packets, work, on_result=save, on_error=failed)
    db.finish_run(run_id, client.usage.as_dict())
    stats["usage"] = client.usage.as_dict()
    return stats


def _user_block(p) -> str:
    from ..llm.stages import _user_block as build
    return build(p)


def own_propositions(alias: str) -> list[tuple[str, str]]:
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT film_id, text FROM model_propositions WHERE scorer=? ORDER BY prop_id",
            [alias],
        ).fetchall()
    return [(r["film_id"], r["text"]) for r in rows]


# --------------------------------------------------------------------------
# Stage 2 — each model names the axes in its own harvest
# --------------------------------------------------------------------------

def derive_axes(
    alias: str, dim_version: str, n_dims: int = 8, client=None, progress=None,
) -> list[dict[str, Any]]:
    db.init_db()
    scorer = SCORERS[alias]
    texts = [text for _film, text in own_propositions(alias)]
    if not texts:
        raise RuntimeError(f"{alias} has harvested nothing — run `atlas model-propose` first")

    client = client or client_for(alias)
    listing = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
    result = client.parse(
        system=dim_mod.derive_system(n_dims),
        user=f"The propositions:\n\n{listing}",
        output_model=dim_mod.DimensionSet,
        max_tokens=16000,
    )
    dims = [d.model_dump() for d in result.dimensions]
    run_id = db.start_run(
        "model-axes", scorer.model, PROMPT_VERSION,
        {"scorer": alias, "dim_version": dim_version, "n_dims": n_dims,
         "from_propositions": len(texts)},
    )
    with db.connect() as con:
        con.execute("DELETE FROM model_axes WHERE scorer=? AND dim_version=?",
                    [alias, dim_version])
        con.executemany(
            "INSERT INTO model_axes (scorer, model, dim_version, dim_id, name, question, "
            "pole_high, pole_low, n_dims, source, run_id, prompt_version, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(alias, scorer.model, dim_version, d["dim_id"], d["name"], d["question"],
              d["pole_high"], d["pole_low"], len(dims), f"own:{len(texts)}props",
              run_id, PROMPT_VERSION, db.now()) for d in dims],
        )
    db.finish_run(run_id, client.usage.as_dict())
    if progress:
        progress(f"{alias:<10} named {len(dims)} axes from {len(texts)} of its own propositions")
    return dims


def axis_names(alias: str, dim_version: str) -> dict[int, str]:
    """Readable names for whichever table this scorer's axes live in.

    The incumbent's are in `dimensions` rather than `model_axes`, and a report
    that prints "opus axis 4" for want of a join is unreadable exactly where it
    matters most.
    """
    axes = load_axes(alias, dim_version)
    if axes:
        return {a["dim_id"]: a["name"] for a in axes}
    if alias == INCUMBENT:
        with db.connect(read_only=True) as con:
            version = _incumbent_version(con, dim_version)
        if version:
            return {d["dim_id"]: d["name"] for d in dim_mod.load_dimensions(version)}
    return {}


def load_axes(alias: str, dim_version: str) -> list[dict[str, Any]]:
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT dim_id, name, question, pole_high, pole_low FROM model_axes "
            "WHERE scorer=? AND dim_version=? ORDER BY dim_id", [alias, dim_version],
        ).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# Stage 3 — every model sorts the SAME items into its own axes
# --------------------------------------------------------------------------

def assign_shared(
    alias: str, dim_version: str, bank_version: str = SHARED_BANK,
    client=None, batch_size: int = 60, progress=None,
) -> int:
    """Place the shared bank on this model's axes, so partitions are comparable."""
    db.init_db()
    dims = load_axes(alias, dim_version)
    if not dims:
        raise RuntimeError(f"{alias} has no {dim_version} axes — run `atlas model-axes` first")
    items = dim_mod.bank_items(bank_version)
    client = client or client_for(alias)
    system = dim_mod.assign_system(dims)
    valid = {d["dim_id"] for d in dims}
    run_id = db.start_run(
        "model-assign", SCORERS[alias].model, PROMPT_VERSION,
        {"scorer": alias, "dim_version": dim_version, "bank_version": bank_version},
    )

    batches = [items[i:i + batch_size] for i in range(0, len(items), batch_size)]
    kept: list[tuple] = []

    def work(batch):
        listing = "\n".join(f"{it['item_id']}. {it['text']}" for it in batch)
        return client.parse(system=system, user=f"Assign these items:\n\n{listing}",
                            output_model=dim_mod.AssignmentSet, max_tokens=16000)

    def save(_batch, result):
        for a in result.assignments:
            if a.dim_id in valid:
                kept.append((alias, dim_version, bank_version, a.item_id, a.dim_id,
                             1 if a.polarity >= 0 else -1, a.fit, run_id, db.now()))
        if progress:
            progress(f"{alias:<10} {len(kept)}/{len(items)} items placed")

    def failed(batch, error):
        if progress:
            progress(f"[red]FAILED[/]   {alias} batch of {len(batch)}: {error}")

    client.map(batches, work, on_result=save, on_error=failed)
    known = {it["item_id"] for it in items}
    kept = [row for row in kept if row[3] in known]
    with db.connect() as con:
        con.execute("DELETE FROM model_axis_items WHERE scorer=? AND dim_version=? "
                    "AND bank_version=?", [alias, dim_version, bank_version])
        con.executemany(
            "INSERT OR REPLACE INTO model_axis_items (scorer, dim_version, bank_version, "
            "item_id, dim_id, polarity, fit, run_id, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            kept,
        )
    db.finish_run(run_id, client.usage.as_dict())
    return len(kept)


def partitions(
    dim_version: str, bank_version: str = SHARED_BANK,
) -> dict[str, dict[str, int]]:
    """{scorer: {item_id: dim_id}} — the comparable objects.

    Claude's own `item_dimensions` assignment is folded in under the incumbent's
    alias so the existing d1 work is part of the comparison rather than beside it.
    """
    db.init_db()
    out: dict[str, dict[str, int]] = defaultdict(dict)
    with db.connect(read_only=True) as con:
        for row in con.execute(
            "SELECT scorer, item_id, dim_id FROM model_axis_items "
            "WHERE dim_version=? AND bank_version=?", [dim_version, bank_version],
        ):
            out[row["scorer"]][row["item_id"]] = row["dim_id"]

        # The incumbent already partitioned this bank, into `item_dimensions`,
        # before any of this existed. Folding it in at the matching k means the
        # comparison starts from work already paid for rather than re-deriving
        # Claude's axes to sit beside themselves.
        incumbent = _incumbent_version(con, dim_version)
        if incumbent:
            for row in con.execute(
                "SELECT item_id, dim_id FROM item_dimensions WHERE dim_version=? "
                "AND bank_version=? AND pass_name=?",
                [incumbent, bank_version, dim_mod.MAIN_PASS],
            ):
                out[INCUMBENT][row["item_id"]] = row["dim_id"]
    return dict(out)


INCUMBENT = "opus"


def _incumbent_version(con, dim_version: str) -> str | None:
    """The atlas's own dimension set, if it has the same number of axes.

    Comparing an 8-axis partition with a 12-axis one would report a difference
    the models never disagreed about, so the incumbent only joins a comparison
    at its own k.
    """
    if not dim_version.startswith("k") or not dim_version[1:].isdigit():
        return None
    row = con.execute(
        "SELECT dim_version FROM dimensions GROUP BY dim_version "
        "HAVING COUNT(*)=? ORDER BY dim_version LIMIT 1", [int(dim_version[1:])],
    ).fetchone()
    return row["dim_version"] if row else None
