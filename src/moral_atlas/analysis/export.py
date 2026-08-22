"""Portable export of everything derived so far.

Two shapes, because a staging box may or may not want DuckDB:

  the .duckdb file itself   Copy it. This is what `infra/README.md` already
                            documents moving through S3, so a manual transfer
                            and the eventual automated one land the same object.

  a JSONL bundle            Self-describing, no DuckDB dependency, diffable,
                            and each table is one file so a partial transfer is
                            still useful.

The manifest is the important part. It records prompt versions, models, and what
each run cost, because a bundle whose provenance you cannot reconstruct is not
worth transferring — you will not be able to tell later whether two exports are
comparable or were produced by different prompts.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .. import db
from ..config import PROMPT_VERSION, settings

TABLES = ("films", "evidence", "skeletons", "propositions_raw",
          "item_bank", "scores", "runs")

# Evidence is by far the largest table and is fully reproducible from the
# public sources, so it is opt-in rather than default.
BULKY = {"evidence"}


def _rows(con, table: str) -> list[dict[str, Any]]:
    con.execute(f"SELECT * FROM {table}")
    cols = [d[0] for d in con.description]
    return [dict(zip(cols, r)) for r in con.fetchall()]


def export(out_dir: str, include_evidence: bool = False,
           copy_db: bool = True, progress=None) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {}
    with db.connect(read_only=True) as con:
        for table in TABLES:
            if table in BULKY and not include_evidence:
                counts[table] = -1          # present in db, deliberately skipped
                continue
            rows = _rows(con, table)
            counts[table] = len(rows)
            path = out / f"{table}.jsonl"
            with path.open("w") as fh:
                for row in rows:
                    fh.write(json.dumps(row, default=str) + "\n")
            if progress:
                progress(f"  {table:<18} {len(rows):>6} rows -> {path.name}")

    manifest = {
        "prompt_version": PROMPT_VERSION,
        "counts": {k: (None if v < 0 else v) for k, v in counts.items()},
        "evidence_included": include_evidence,
        "runs": [],
        "stage_completeness": {},
    }

    with db.connect(read_only=True) as con:
        for r in con.execute(
            "SELECT run_id, stage, model, prompt_version, n_calls, "
            "input_tokens, output_tokens, cost_usd FROM runs ORDER BY started_at"
        ).fetchall():
            manifest["runs"].append(dict(zip(
                ("run_id", "stage", "model", "prompt_version", "n_calls",
                 "input_tokens", "output_tokens", "cost_usd"), r)))

        n_films = con.execute("SELECT count(*) FROM films").fetchone()[0]
        prop_films = con.execute(
            "SELECT count(DISTINCT film_id) FROM propositions_raw").fetchone()[0]
        skel_films = con.execute(
            "SELECT count(DISTINCT film_id) FROM skeletons WHERE variant='full'"
        ).fetchone()[0]
        scored = con.execute(
            "SELECT count(DISTINCT film_id) FROM scores").fetchone()[0]

    # Stated plainly so nobody downstream mistakes an intermediate for a result.
    manifest["stage_completeness"] = {
        "films_ingested": n_films,
        "films_with_full_skeleton": skel_films,
        "films_with_propositions": prop_films,
        "films_scored": scored,
        "has_item_bank": counts.get("item_bank", 0) > 0,
        "has_analysis_results": scored > 0,
    }
    manifest["total_cost_usd"] = round(
        sum(r["cost_usd"] or 0 for r in manifest["runs"]), 2)

    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))

    if copy_db:
        src = settings().db_path
        if src.exists():
            shutil.copy2(src, out / "atlas.duckdb")
            manifest["duckdb_bytes"] = (out / "atlas.duckdb").stat().st_size

    return manifest
