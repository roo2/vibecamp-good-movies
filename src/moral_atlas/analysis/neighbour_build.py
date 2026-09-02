"""Build the film-to-film co-preference table that `neighbours` reads.

Kept apart from `neighbours` on purpose. That module states that nothing in it
reads the ratings corpus at runtime — only the aggregate table — and it should
go on being true of the module the web app imports. This one is the offline
half, run by `atlas taste-build`, and the API never touches it.

What gets stored is a similarity matrix over OUR films: an aggregate statistic,
not the ratings. Two guards on what may influence a recommendation:

  MIN_SUPPORT  a correlation over a handful of shared raters is noise wearing a
               decimal point. Pairs under this are dropped outright.
  TOP_K        only each film's strongest neighbours are kept. The tail of a
               similarity row is mostly noise, and storing it whole would let
               500 near-zero terms outvote the 50 that mean something.
"""
from __future__ import annotations

from typing import Any, Callable

import numpy as np

from .. import db
from . import movielens

MIN_SUPPORT, TOP_K = 50, 60
SOURCE = "MovieLens ml-25m (GroupLens), non-commercial research use"


def build(ratings: movielens.Ratings | None = None,
          min_support: int = MIN_SUPPORT, top_k: int = TOP_K,
          progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Derive co-preference similarity and replace `film_neighbours`."""
    ratings = ratings or movielens.load(progress=progress)
    film_of = ratings.film_of

    matrix, cols = movielens.centred_matrix(ratings)
    n_films = len(cols)

    # Support is counted on the UNCENTRED pattern: how many raters saw both
    # films, regardless of what they thought. Centring changes the values, never
    # who rated what.
    present = matrix.copy()
    present.data = np.ones_like(present.data)
    support = np.asarray((present.T @ present).todense())

    norms = np.sqrt(np.asarray(matrix.multiply(matrix).sum(axis=0)).ravel())
    norms[norms == 0] = 1.0
    similarity = np.asarray((matrix.T @ matrix).todense(), dtype=np.float32) / \
        np.outer(norms, norms)
    np.fill_diagonal(similarity, 0.0)
    similarity[support < min_support] = 0.0

    upper = np.triu_indices(n_films, 1)
    stats = {
        "films": n_films,
        "users": int(matrix.shape[0]),
        "median_support": int(np.median(support[upper])),
        "below_floor": float((support[upper] < min_support).mean()),
    }
    if progress:
        progress(f"  {n_films} films, {stats['users']:,} users, median "
                 f"{stats['median_support']} shared raters per pair")
        progress(f"  pairs below the {min_support}-rater floor: "
                 f"{stats['below_floor']:.1%}")

    now = db.now()
    rows = []
    for i in range(n_films):
        # Ranked by ABSOLUTE similarity: a strong negative — the same people
        # reliably disagree about these two — is as much information as a strong
        # positive, and the scorer uses the sign.
        for j in np.argsort(-np.abs(similarity[i]))[:top_k]:
            if similarity[i, j] == 0.0:
                continue
            rows.append((film_of[cols[i]], film_of[cols[j]],
                         float(similarity[i, j]), int(support[i, j]), SOURCE, now))

    db.init_db()
    with db.connect() as con:
        con.execute("DELETE FROM film_neighbours")
        con.executemany(
            "INSERT OR REPLACE INTO film_neighbours "
            "(film_id, neighbour_id, similarity, support, source, created_at) "
            "VALUES (?,?,?,?,?,?)", rows)

    stats["links"] = len(rows)
    stats["placed"] = len({r[0] for r in rows})
    if progress:
        progress(f"  stored {len(rows):,} neighbour links for {stats['placed']} "
                 f"films (top {top_k} each)")
    return stats
