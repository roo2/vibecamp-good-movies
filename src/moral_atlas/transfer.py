"""Moving the corpus between stores: into Postgres, and out to the deployed one.

Two jobs that are the same job.

`import_sqlite` is the one-off: the store spent its first year in a SQLite file
and every derived row in it — 273,015 verdicts, 37,559 neighbour pairs — is
expensive to reproduce and identical wherever it lands.

`push_corpus` is the one that runs every deploy. A sweep happens on a laptop,
where the API keys and the 60GB subtitle archive live, and its results have to
reach a server that has neither. This is that path, and it is a direct
connection to the target rather than a file in a bucket: the file was there
because the runner could not be reached from here, and Heroku can.

The rule both obey is the old one, restated:

  the corpus     every table that is not named in USER_TABLES. Derived from a
                 sweep, reproducible, the same on every machine that ran one.
                 Replaced.
  USER_TABLES    the record that somebody used the thing. Never written.
                 Counted before and after so "user data was preserved" is
                 something you can check rather than trust.

What changed with Postgres is that the foreign keys are now enforced, and the
old loader relied on them not being. It turned them off, replaced every table,
and printed a count of the ratings left pointing at nothing. That count can no
longer be non-zero, which is an improvement with a consequence: a film somebody
has rated cannot be deleted by a deploy. Those films are kept and named — see
`_replace_films`.
"""
from __future__ import annotations

from typing import Any, Iterable, Iterator, Sequence

from psycopg.rows import tuple_row

from . import db

# The only list. Everything else in the schema is corpus and gets replaced.
#
# This was once the other way round — an allowlist of corpus tables — and it
# failed as allowlists do: `film_sets` and `film_set_members` shipped, loaded
# "successfully", and were not copied, because nobody had added them to a list
# two files from where the tables are declared. Silent, and indistinguishable
# from a feature that did not work. Deriving it inverts the failure: a new
# corpus table is carried automatically, and the mistake left to make is
# forgetting to declare something as USER data — which is loud, because it
# deletes rows somebody made.
USER_TABLES = frozenset({
    "users", "user_sessions", "movie_ratings", "test_results", "group_sessions",
    "session_members", "shortlist_reactions", "session_shortlist_films",
})

# How many rows cross the wire at once. Large enough that the round trips
# disappear, small enough that a table of a million rows does not have to be
# held in memory twice.
BATCH = 5_000


def foreign_keys(con) -> list[tuple[str, str]]:
    """(child, parent) for every foreign key in the current schema."""
    rows = con.execute(
        "SELECT c.conrelid::regclass::text AS child, "
        "       c.confrelid::regclass::text AS parent "
        "FROM pg_constraint c "
        "JOIN pg_class t ON t.oid = c.conrelid "
        "JOIN pg_namespace n ON n.oid = t.relnamespace "
        "WHERE c.contype = 'f' AND n.nspname = current_schema()").fetchall()
    return [(r["child"].strip('"'), r["parent"].strip('"'))
            for r in rows if r["child"] != r["parent"]]


def dependency_order(con, tables: Iterable[str]) -> list[str]:
    """`tables`, parents before children.

    Insert in this order and delete in its reverse. Under SQLite the order was
    cosmetic — `films` went first because it read better in the log. Here it is
    the difference between a deploy and a foreign key violation.
    """
    wanted = list(tables)
    remaining = set(wanted)
    parents: dict[str, set[str]] = {t: set() for t in wanted}
    for child, parent in foreign_keys(con):
        if child in remaining and parent in remaining:
            parents[child].add(parent)

    out: list[str] = []
    placed: set[str] = set()
    while remaining:
        ready = sorted(t for t in remaining if parents[t] <= placed)
        if not ready:
            # A cycle. Nothing in this schema has one, but a schema is a living
            # thing: take the rest in name order rather than looping forever,
            # and let the database complain if it really matters.
            ready = sorted(remaining)
        for table in ready:
            out.append(table)
            placed.add(table)
            remaining.discard(table)
    return out


def _column_types(con, table: str) -> dict[str, str]:
    return {row["column_name"]: row["data_type"] for row in con.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = %s "
        "ORDER BY ordinal_position", [table])}


def _coerce(value: Any, kind: str) -> Any:
    """Make a SQLite value fit a Postgres column.

    SQLite types are per-value, not per-column, so a column declared INTEGER can
    hold the string "1" — and does, in a handful of places in the old store.
    Postgres will not have it. Only the cases that actually occur are handled;
    anything else is passed through so the database raises rather than this
    silently rewriting data.
    """
    if value is None:
        return None
    if kind in ("integer", "bigint", "smallint"):
        return int(value) if not isinstance(value, int) else value
    if kind in ("real", "double precision", "numeric"):
        return float(value)
    if kind == "boolean":
        return bool(value) if not isinstance(value, str) else value not in ("0", "", "f")
    if kind == "text" and not isinstance(value, (str, bytes)):
        return str(value)
    return value


def copy_into(con, table: str, columns: Sequence[str], rows: Iterator[Sequence[Any]],
              types: dict[str, str]) -> int:
    """Stream rows into `table` with COPY. Returns how many landed.

    COPY rather than INSERT because this moves a third of a million rows and the
    difference is minutes.
    """
    kinds = [types.get(c, "text") for c in columns]
    names = ", ".join(f'"{c}"' for c in columns)
    written = 0
    with con.cursor() as cur:
        with cur.copy(f'COPY "{table}" ({names}) FROM STDIN') as copy:
            for row in rows:
                # Rows arrive as tuples. A mapping would iterate its KEYS here
                # and copy the column names into the table, one per row, which
                # is exactly as loud as it sounds — but only for the tables
                # whose first column is not text.
                values = row.values() if hasattr(row, "values") else row
                copy.write_row([_coerce(v, k) for v, k in zip(values, kinds)])
                written += 1
    return written


def _batched(cursor, size: int = BATCH) -> Iterator[Sequence[Any]]:
    while True:
        chunk = cursor.fetchmany(size)
        if not chunk:
            return
        yield from chunk


# --- SQLite -> Postgres, once ---------------------------------------------

def import_sqlite(path: str, report=print) -> dict[str, int]:
    """Load an old SQLite store into the Postgres one, whole.

    Everything, not just the corpus: this runs against an empty database to
    stand the new environment up where the old one left off, so the demo's
    users keep their profiles and their shortlists.
    """
    import sqlite3

    source = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    lite_tables = {r[0] for r in source.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'")}

    counts: dict[str, int] = {}
    with db.connect() as con:
        db.init_schema(con)
        here = db.table_names(con)
        missing = sorted(lite_tables - here)
        if missing:
            report(f"  not in this schema, skipped: {', '.join(missing)}")

        ordered = dependency_order(con, sorted(lite_tables & here))
        for table in reversed(ordered):
            con.execute(f'DELETE FROM "{table}"')

        for table in ordered:
            types = _column_types(con, table)
            lite_columns = [r[1] for r in source.execute(f'PRAGMA table_info("{table}")')]
            shared = [c for c in lite_columns if c in types]
            dropped = [c for c in lite_columns if c not in types]
            if dropped:
                report(f"  {table}: columns not in this schema, dropped: {dropped}")
            if not shared:
                continue
            names = ", ".join(f'"{c}"' for c in shared)
            cursor = source.execute(f'SELECT {names} FROM "{table}"')
            counts[table] = copy_into(con, table, shared, _batched(cursor), types)
            report(f"  {table:<24} {counts[table]:>8,}")
    source.close()
    return counts


# --- Postgres -> Postgres, every deploy ------------------------------------

def _referencing_user_tables(con, table: str) -> list[str]:
    return sorted(child for child, parent in foreign_keys(con)
                  if parent == table and child in USER_TABLES)


def _replace_films(source, target, columns: Sequence[str], types: dict[str, str],
                   report) -> tuple[int, list[str]]:
    """Replace `films` without deleting one somebody has a rating for.

    Every other corpus table can be emptied and refilled, because nothing a user
    made points into it. `films` is pointed at from four user tables, so the
    delete has to spare whatever they still name. Those films are returned so
    the deploy can say which ones it kept — the honest answer to "I removed that
    film from the corpus and it is still on the site" is this list, and the fix
    is `atlas remove-film` against the target, which clears the ratings too.
    """
    names = ", ".join(f'"{c}"' for c in columns)

    target.execute("CREATE TEMP TABLE incoming_films (film_id TEXT PRIMARY KEY) "
                   "ON COMMIT DROP")
    cursor = source.cursor(row_factory=tuple_row)
    cursor.execute("SELECT film_id FROM films")
    copy_into(target, "incoming_films", ["film_id"], _batched(cursor),
              {"film_id": "text"})

    # Which user tables name a film is read from the constraints, not listed:
    # a table added later has to be covered without anyone remembering this
    # function exists.
    spoken_for = " OR ".join(
        f'EXISTS (SELECT 1 FROM "{t}" u WHERE u.film_id = f.film_id)'
        for t in _referencing_user_tables(target, "films")) or "FALSE"
    gone = ("NOT EXISTS (SELECT 1 FROM incoming_films i "
            "WHERE i.film_id = f.film_id)")

    held = [r["film_id"] for r in target.execute(
        f"SELECT f.film_id FROM films f WHERE {gone} AND ({spoken_for}) "
        f"ORDER BY f.film_id")]
    if held:
        report(f"  keeping {len(held)} film(s) this corpus drops but users have "
               f"touched: {', '.join(held[:5])}{'…' if len(held) > 5 else ''}")

    target.execute(f"DELETE FROM films f WHERE {gone} AND NOT ({spoken_for})")

    # Upsert rather than delete-and-insert, because the rows that stayed are
    # still referenced and cannot be removed even for an instant.
    updates = ", ".join(f'"{c}"=EXCLUDED."{c}"' for c in columns if c != "film_id")
    target.execute('CREATE TEMP TABLE incoming_rows (LIKE films) ON COMMIT DROP')
    cursor = source.cursor(row_factory=tuple_row)
    cursor.execute(f'SELECT {names} FROM films')
    moved = copy_into(target, "incoming_rows", columns, _batched(cursor), types)
    target.execute(f'INSERT INTO films ({names}) SELECT {names} FROM incoming_rows '
                   f'ON CONFLICT (film_id) DO UPDATE SET {updates}')
    return moved, held


def push_corpus(target_url: str, report=print) -> dict[str, Any]:
    """Copy the corpus from this machine's store into the one at `target_url`.

    One transaction on the target: either the whole corpus lands or none of it
    does, and the site never serves a half-swapped atlas. The old loader could
    not promise that — it worked table by table against a file the API had been
    stopped for.
    """
    target = db.Connection.connect(db.normalise_url(target_url),
                                   row_factory=db._row_factory, autocommit=False)
    try:
        with db.connect(read_only=True) as source:
            db.init_schema(target)
            target.commit()

            here = db.table_names(source)
            there = db.table_names(target)
            corpus = sorted((here & there) - USER_TABLES)
            only_here = sorted(here - there - USER_TABLES)
            if only_here:
                report(f"  not on the target, skipped: {', '.join(only_here)}")

            before_users = _counts(target, sorted(USER_TABLES & there))

            ordered = dependency_order(target, corpus)
            moved: dict[str, int] = {}
            held: list[str] = []

            # Children first, so nothing is deleted while something still points
            # at it. `films` is not emptied at all — see `_replace_films`.
            for table in reversed(ordered):
                if table != "films":
                    target.execute(f'DELETE FROM "{table}"')

            for table in ordered:
                types = _column_types(target, table)
                columns = [c for c in _column_types(source, table) if c in types]
                dropped = [c for c in _column_types(source, table) if c not in types]
                if dropped:
                    report(f"  {table}: not on the target, dropped: {dropped}")
                if not columns:
                    continue
                if table == "films":
                    moved[table], held = _replace_films(
                        source, target, columns, types, report)
                else:
                    names = ", ".join(f'"{c}"' for c in columns)
                    cursor = source.cursor(row_factory=tuple_row)
                    cursor.execute(f'SELECT {names} FROM "{table}"')
                    moved[table] = copy_into(target, table, columns,
                                             _batched(cursor), types)
                report(f"  {table:<24} {moved.get(table, 0):>8,}")

            after_users = _counts(target, sorted(USER_TABLES & there))
            changed = [t for t in before_users if before_users[t] != after_users[t]]
            if changed:
                target.rollback()
                raise RuntimeError(
                    "refusing: this would have written user tables: "
                    + ", ".join(changed))
            target.commit()
        return {"moved": moved, "held": held, "users": after_users}
    except BaseException:
        target.rollback()
        raise
    finally:
        target.close()


def _counts(con, tables: Sequence[str]) -> dict[str, int]:
    return {t: con.execute(f'SELECT COUNT(*) AS n FROM "{t}"').fetchone()["n"]
            for t in tables}
