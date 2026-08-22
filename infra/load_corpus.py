"""Swap the corpus tables of a live store, leaving the user tables alone.

Called by infra/load-corpus.sh, which stops the API around it. Kept as its own
file rather than a heredoc so it can be read, reviewed and tested like code.

The split below is the whole point of the script, so it is stated once, here:

  CORPUS_TABLES   derived from a sweep, reproducible, and the same on every
                  machine that has run one. Replaced wholesale.
  USER_TABLES     the record that somebody used the demo. Never written. Counted
                  before and after, and the counts printed, so "user data was
                  preserved" is something you can check rather than trust.

Rows are deleted and re-inserted rather than the tables dropped and recreated:
that keeps whatever schema the runner is on, so a store one migration ahead of
the snapshot does not silently lose a column.
"""
from __future__ import annotations

import os
import sqlite3
import sys

CORPUS_TABLES = ["dimensions", "evidence", "films", "item_bank", "item_dimensions",
                 "propositions_raw", "runs", "scores", "skeletons"]
USER_TABLES = ["users", "user_sessions", "movie_ratings", "test_results",
               "group_sessions", "session_members", "shortlist_reactions",
               "session_shortlist_films"]

LIVE = os.environ.get("ATLAS_LIVE", "/opt/atlas/data/atlas.sqlite")
INCOMING = os.environ.get("ATLAS_INCOMING", "/opt/atlas/data/incoming-corpus.sqlite")


def main() -> int:
    con = sqlite3.connect(LIVE)
    # Off deliberately: the user tables reference films, and for the moment
    # between the delete and the insert every one of those references dangles.
    # The orphan count at the end is the real check, and it runs after the
    # commit rather than during it.
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute("ATTACH DATABASE ? AS corpus", (INCOMING,))

    def count(schema: str, table: str) -> int | None:
        try:
            return con.execute(f'SELECT COUNT(*) FROM {schema}."{table}"').fetchone()[0]
        except sqlite3.Error:
            return None

    before_corpus = {t: count("main", t) for t in CORPUS_TABLES}
    before_users = {t: count("main", t) for t in USER_TABLES}

    con.execute("BEGIN")
    for table in CORPUS_TABLES:
        live_cols = [r[1] for r in con.execute(f'PRAGMA main.table_info("{table}")')]
        corp_cols = [r[1] for r in con.execute(f'PRAGMA corpus.table_info("{table}")')]
        if not live_cols or not corp_cols:
            print(f"  skip {table}: on runner={bool(live_cols)} in snapshot={bool(corp_cols)}")
            continue
        shared = [c for c in corp_cols if c in live_cols]
        ignored = [c for c in corp_cols if c not in live_cols]
        if ignored:
            print(f"  note {table}: snapshot has columns the runner does not, ignored: {ignored}")
        cols = ", ".join(f'"{c}"' for c in shared)
        con.execute(f'DELETE FROM main."{table}"')
        con.execute(f'INSERT INTO main."{table}" ({cols}) SELECT {cols} FROM corpus."{table}"')
    con.execute("COMMIT")

    after_corpus = {t: count("main", t) for t in CORPUS_TABLES}
    after_users = {t: count("main", t) for t in USER_TABLES}

    print("\ncorpus tables, replaced")
    for table in CORPUS_TABLES:
        print(f"  {table:<22} {str(before_corpus[table]):>7} -> {after_corpus[table]}")

    print("\nuser tables, untouched")
    changed = [t for t in USER_TABLES if before_users[t] != after_users[t]]
    for table in USER_TABLES:
        mark = "   <-- CHANGED" if table in changed else ""
        print(f"  {table:<22} {str(before_users[table]):>7} -> {after_users[table]}{mark}")

    blank = con.execute("SELECT COUNT(*) FROM films "
                        "WHERE description IS NULL OR TRIM(description)=''").fetchone()[0]
    orphans = con.execute(
        "SELECT COUNT(*) FROM movie_ratings r LEFT JOIN films f ON f.film_id=r.film_id "
        "WHERE f.film_id IS NULL").fetchone()[0]
    print(f"\nfilms with no description: {blank}   "
          "(every one of these renders as the generic placeholder)")
    print(f"ratings whose film is no longer present: {orphans}")
    con.close()

    if changed:
        print("\nFAILED: user tables changed: " + ", ".join(changed))
        return 1
    print("\nOK: corpus replaced, user data intact")
    return 0


if __name__ == "__main__":
    sys.exit(main())
