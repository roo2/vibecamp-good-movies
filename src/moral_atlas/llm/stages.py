"""The three LLM stages, each writing versioned rows into DuckDB."""
from __future__ import annotations

import json
import uuid
from typing import Any, Iterable

from .. import db
from ..config import PROMPT_VERSION
from ..sources import packet as packet_mod
from . import prompts
from .client import LLMClient
from .schemas import MoralSkeleton, PropositionSet, ScoreSet


def _user_block(p: packet_mod.Packet, extra: str = "") -> str:
    missing = (
        f"\nLAYERS DELIBERATELY WITHHELD IN THIS CONDITION: "
        f"{', '.join(p.layers_missing)}\n" if p.layers_missing else "\n"
    )
    return (
        f"FILM IDENTIFIERS\n{p.header}\n"
        f"EVIDENCE CONDITION: {p.variant} "
        f"(layers supplied: {', '.join(p.layers_present) or 'none'})"
        f"{missing}{extra}\n"
        f"===== EVIDENCE =====\n\n{p.body}\n"
    )


# --------------------------------------------------------------------------
# Stage 1 — moral skeleton
# --------------------------------------------------------------------------

def extract_skeletons(
    film_ids: Iterable[str], variants: Iterable[str],
    client: LLMClient, progress=None,
) -> str:
    jobs = [
        packet_mod.build(fid, v)
        for fid in film_ids for v in variants
    ]
    jobs = [p for p in jobs if p.usable]

    run_id = db.start_run(
        "skeleton", client.model, PROMPT_VERSION,
        {"variants": list(variants), "n_jobs": len(jobs)},
    )

    def work(p: packet_mod.Packet) -> tuple[packet_mod.Packet, MoralSkeleton]:
        sk = client.parse(
            system=prompts.SKELETON_SYSTEM,
            user=_user_block(p),
            output_model=MoralSkeleton,
            max_tokens=16000,
        )
        return p, sk

    def save(_p, res) -> None:
        p, sk = res
        with db.connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO skeletons "
                "(film_id, variant, run_id, data, model, prompt_version, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                [p.film_id, p.variant, run_id, sk.model_dump_json(),
                 client.model, PROMPT_VERSION, db.now()],
            )
        if progress:
            progress(f"skeleton  {p.film_id:<28} {p.variant}")

    def failed(p, e) -> None:
        if progress:
            progress(f"FAILED    {p.film_id:<28} {p.variant}  {type(e).__name__}: {e}")

    client.map(jobs, work, on_result=save, on_error=failed)
    db.finish_run(run_id, client.usage.as_dict())
    return run_id


# --------------------------------------------------------------------------
# Stage 2 — free-form proposition generation
# --------------------------------------------------------------------------

def generate_propositions(
    film_ids: Iterable[str], client: LLMClient,
    variant: str = "full", progress=None,
) -> str:
    """Generate the raw statement pool the item bank is cut from.

    Run on the richest variant available: we want the widest possible vocabulary
    here. Which propositions survive on *thin* evidence is a separate question,
    answered later by scoring, not by generation.
    """
    run_id = db.start_run(
        "propositions", client.model, PROMPT_VERSION, {"variant": variant},
    )

    jobs = []
    for fid in film_ids:
        p = packet_mod.build(fid, variant)
        if not p.usable:
            p = packet_mod.build(fid, "spine")
        if p.usable:
            jobs.append(p)

    def work(p: packet_mod.Packet):
        skeleton = _latest_skeleton(p.film_id, p.variant) or _latest_skeleton(p.film_id)
        extra = (
            f"\nMORAL SKELETON ALREADY EXTRACTED FROM THIS EVIDENCE:\n"
            f"{json.dumps(skeleton, indent=2)}\n" if skeleton else ""
        )
        ps = client.parse(
            system=prompts.PROPOSITIONS_SYSTEM,
            user=_user_block(p, extra),
            output_model=PropositionSet,
            max_tokens=16000,
        )
        return p, ps

    def save(_p, res) -> None:
        p, ps = res
        with db.connect() as con:
            for prop in ps.propositions:
                con.execute(
                    "INSERT OR REPLACE INTO propositions_raw "
                    "(prop_id, film_id, variant, run_id, text, stance, evidence, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    [uuid.uuid4().hex[:16], p.film_id, p.variant, run_id,
                     prop.text, prop.stance, prop.evidence, db.now()],
                )
        if progress:
            progress(f"propose   {p.film_id:<28} {len(ps.propositions)} statements")

    def failed(p, e) -> None:
        if progress:
            progress(f"FAILED    {p.film_id:<28} {type(e).__name__}: {e}")

    client.map(jobs, work, on_result=save, on_error=failed)
    db.finish_run(run_id, client.usage.as_dict())
    return run_id


# --------------------------------------------------------------------------
# Stage 3 — score films against the item bank
# --------------------------------------------------------------------------

def score_films(
    film_ids: Iterable[str], variants: Iterable[str], bank_version: str,
    client: LLMClient, progress=None,
) -> str:
    items = _load_bank(bank_version)
    if not items:
        raise RuntimeError(f"item bank {bank_version!r} is empty — run `atlas bank` first")

    # Byte-identical across every call in the run: this is the cache prefix,
    # and it is most of the reason a full sweep costs tens rather than hundreds.
    bank_block = "\n".join(f"{i['item_id']}. {i['text']}" for i in items)
    system = prompts.scoring_system(bank_block)

    jobs = [packet_mod.build(fid, v) for fid in film_ids for v in variants]
    jobs = [p for p in jobs if p.usable]

    run_id = db.start_run(
        "scoring", client.model, PROMPT_VERSION,
        {"bank_version": bank_version, "n_items": len(items),
         "variants": list(variants), "n_jobs": len(jobs)},
    )
    valid_ids = {i["item_id"] for i in items}

    def work(p: packet_mod.Packet):
        ss = client.parse(
            system=system,
            user=_user_block(p),
            output_model=ScoreSet,
            max_tokens=16000,
        )
        return p, ss

    def save(_p, res) -> None:
        p, ss = res
        kept = 0
        with db.connect() as con:
            for sc in ss.scores:
                if sc.item_id not in valid_ids:
                    continue  # hallucinated id — drop rather than store
                con.execute(
                    "INSERT OR REPLACE INTO scores "
                    "(film_id, item_id, bank_version, variant, run_id, value, "
                    "confidence, evidence) VALUES (?,?,?,?,?,?,?,?)",
                    [p.film_id, sc.item_id, bank_version, p.variant, run_id,
                     1 if sc.verdict == "affirms" else -1, sc.confidence, sc.evidence],
                )
                kept += 1
        if progress:
            progress(f"score     {p.film_id:<28} {p.variant:<13} {kept}/{len(items)} engaged")

    def failed(p, e) -> None:
        if progress:
            progress(f"FAILED    {p.film_id:<28} {p.variant}  {type(e).__name__}: {e}")

    client.map(jobs, work, on_result=save, on_error=failed)
    db.finish_run(run_id, client.usage.as_dict())
    return run_id


# --------------------------------------------------------------------------

def _latest_skeleton(film_id: str, variant: str | None = None) -> dict[str, Any] | None:
    q = ("SELECT data FROM skeletons WHERE film_id=? "
         + ("AND variant=? " if variant else "")
         + "ORDER BY created_at DESC LIMIT 1")
    args = [film_id] + ([variant] if variant else [])
    with db.connect(read_only=True) as con:
        row = con.execute(q, args).fetchone()
    return json.loads(row[0]) if row else None


def _load_bank(bank_version: str) -> list[dict[str, Any]]:
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT item_id, text FROM item_bank "
            "WHERE bank_version=? AND active ORDER BY item_id",
            [bank_version],
        ).fetchall()
    return [{"item_id": r[0], "text": r[1]} for r in rows]
