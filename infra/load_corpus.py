"""Swap the corpus tables of a live store, leaving the user tables alone.

Called by infra/load-corpus.sh, which stops the API around it. Kept as its own
file rather than a heredoc so it can be read, reviewed and tested like code.

The split below is the whole point of the script, so it is stated once, here:

  the corpus       every table in the snapshot that is not named below.
                  Derived from a sweep, reproducible, and the same on every
                  machine that has run one. Replaced wholesale. Derived rather
                  than listed, because a list is a thing you forget to add to
                  and the failure is silent.
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

# The user tables are the ONLY list. Everything else in the snapshot is corpus
# and gets replaced.
#
# This used to be the other way round — an explicit allowlist of corpus tables —
# and it failed exactly as an allowlist does. `film_sets` and
# `film_set_members` shipped in the snapshot, loaded "successfully", and were
# not copied, because nobody had added them to a list two files away from where
# the tables are declared. Silent, and indistinguishable from a feature that
# simply did not work.
#
# Deriving it inverts the failure: a new corpus table is carried automatically,
# and the mistake you can now make is forgetting to declare something as USER
# data — which is loud, because it deletes rows somebody made.
USER_TABLES = ["users", "user_sessions", "movie_ratings", "test_results",
               "group_sessions", "session_members", "shortlist_reactions",
               "session_shortlist_films"]

# `films` first: everything else references it, and while foreign keys are off
# for the copy, loading the referent first keeps the orphan check at the end
# meaningful rather than transiently alarming.
FIRST = ["films"]

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

    incoming = [r[0] for r in con.execute(
        "SELECT name FROM corpus.sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    corpus_tables = [t for t in FIRST if t in incoming] + [
        t for t in incoming if t not in USER_TABLES and t not in FIRST]
    print(f"corpus tables in the snapshot: {len(corpus_tables)}")
    skipped = [t for t in incoming if t in USER_TABLES]
    if skipped:
        print(f"  leaving user tables alone: {', '.join(skipped)}")

    def count(schema: str, table: str) -> int | None:
        try:
            return con.execute(f'SELECT COUNT(*) FROM {schema}."{table}"').fetchone()[0]
        except sqlite3.Error:
            return None

    before_corpus = {t: count("main", t) for t in corpus_tables}
    before_users = {t: count("main", t) for t in USER_TABLES}

    con.execute("BEGIN")
    for table in corpus_tables:
        live_cols = [r[1] for r in con.execute(f'PRAGMA main.table_info("{table}")')]
        corp_cols = [r[1] for r in con.execute(f'PRAGMA corpus.table_info("{table}")')]
        if not corp_cols:
            print(f"  skip {table}: not in the snapshot")
            continue

        # Bring the runner's schema up to the snapshot's before copying.
        #
        # This used to be a manual step, and it failed silently in both
        # directions: a table the runner lacked was skipped with a one-line
        # note, and a COLUMN it lacked was quietly dropped from the copy — so a
        # snapshot carrying new derived data could load "successfully" and leave
        # the site with none of it. Creating what is missing makes a schema
        # change part of the deploy rather than something to remember.
        if not live_cols:
            ddl = con.execute(
                "SELECT sql FROM corpus.sqlite_master WHERE type='table' AND name=?",
                (table,)).fetchone()
            if not ddl or not ddl[0]:
                print(f"  skip {table}: no schema in the snapshot")
                continue
            con.execute(ddl[0])
            live_cols = [r[1] for r in con.execute(f'PRAGMA main.table_info("{table}")')]
            print(f"  created {table} on the runner")

        for column in corp_cols:
            if column not in live_cols:
                kind = next((r[2] for r in con.execute(f'PRAGMA corpus.table_info("{table}")')
                             if r[1] == column), "TEXT")
                con.execute(f'ALTER TABLE main."{table}" ADD COLUMN "{column}" {kind}')
                live_cols.append(column)
                print(f"  added {table}.{column} on the runner")

        shared = [c for c in corp_cols if c in live_cols]
        ignored = [c for c in live_cols if c not in corp_cols]
        if ignored:
            print(f"  note {table}: runner has columns the snapshot does not: {ignored}")
        cols = ", ".join(f'"{c}"' for c in shared)
        con.execute(f'DELETE FROM main."{table}"')
        con.execute(f'INSERT INTO main."{table}" ({cols}) SELECT {cols} FROM corpus."{table}"')
    con.execute("COMMIT")

    after_corpus = {t: count("main", t) for t in corpus_tables}
    after_users = {t: count("main", t) for t in USER_TABLES}

    print("\ncorpus tables, replaced")
    for table in corpus_tables:
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
