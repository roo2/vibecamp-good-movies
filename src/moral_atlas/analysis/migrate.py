"""One-way migration of an existing DuckDB store into SQLite.

Kept as real code rather than a throwaway script because the data it moves cost
actual money to produce — skeletons alone were $22 — and a migration that
silently drops rows is worse than one that refuses to run.

Every table is copied and then re-counted from the destination. A mismatch
raises rather than warns.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import db

TABLES = ("films", "evidence", "runs", "skeletons", "propositions_raw",
          "item_bank", "scores")


def migrate(duckdb_path: str | Path, progress=None) -> dict[str, Any]:
    try:
        import duckdb as ddb
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "Reading the old store needs the duckdb package: "
            "pip install 'moral-atlas[migrate]'"
        ) from e

    src = Path(duckdb_path)
    if not src.exists():
        raise FileNotFoundError(f"no such DuckDB file: {src}")

    db.init_db()
    report: dict[str, Any] = {"source": str(src), "tables": {}}
    con = ddb.connect(str(src), read_only=True)

    try:
        for table in TABLES:
            try:
                con.execute(f"SELECT * FROM {table}")
            except Exception:            # table absent in the old file
                report["tables"][table] = {"source": 0, "copied": 0, "skipped": True}
                continue

            cols = [d[0] for d in con.description]
            rows = con.fetchall()

            payload = []
            for row in rows:
                record = dict(zip(cols, row))
                for key, value in list(record.items()):
                    # DuckDB list columns arrive as Python lists; SQLite needs JSON.
                    if key in db.LIST_COLUMNS:
                        record[key] = json.dumps(list(value)) if value is not None else None
                    elif isinstance(value, (list, dict)):
                        record[key] = json.dumps(value)
                    elif hasattr(value, "isoformat"):
                        record[key] = value.isoformat()
                payload.append([record[c] for c in cols])

            with db.connect() as dest:
                dest.executemany(
                    f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) "
                    f"VALUES ({','.join('?' * len(cols))})",
                    payload,
                )

            with db.connect(read_only=True) as dest:
                copied = dest.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]

            report["tables"][table] = {"source": len(rows), "copied": copied,
                                       "skipped": False}
            if progress:
                progress(f"  {table:<18} {len(rows):>6} -> {copied:>6}")

            if copied != len(rows):
                raise RuntimeError(
                    f"{table}: read {len(rows)} rows from DuckDB but destination "
                    f"holds {copied}. Refusing to continue with a partial migration."
                )
    finally:
        con.close()

    report["total_rows"] = sum(t["copied"] for t in report["tables"].values())
    return report
