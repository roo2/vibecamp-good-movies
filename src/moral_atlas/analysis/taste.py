"""The dimensions of TASTE: what kind of film someone is drawn to.

The moral axes were discovered by asking what films argue and correlating the
answers. This asks a different question of the same films — who likes them
together — and factors that instead. If preference has dimensions beyond the
moral ones, they are in here.

Method mirrors the moral pipeline deliberately, so the two are comparable:

  EXTRACT     common factors of the centred user-by-film matrix, by the same
              principal-axis-and-promax route the moral axes take. Each user is
              centred on their own average first, so "rates everything highly"
              produces no structure. Components (a truncated SVD) are still
              reachable with ATLAS_EXTRACTION=pca; they replicate as well but
              name far worse, which is why they are no longer the default.
  VALIDATE    split the USERS in half, factor each half separately, and check
              whether the same dimensions come back. A dimension that does not
              survive a change of sample is not a dimension. Congruence is
              Tucker's coefficient, matched greedily; 0.85 is the bar kept here.
  ORIENT      an SVD component's sign is arbitrary, so each named dimension is
              turned to face its anchor tag before anything is written. Without
              this step a rebuild silently swaps the pole labels.
  NAME        from `seeds/taste-dimensions.yaml`, with the tag evidence that
              earned each name stored beside it.

Nothing is named from the loadings alone. Naming what has not replicated is how
you end up believing in noise.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .. import db
from ..config import ROOT, settings
from . import latent, movielens

# How many components to pull out before asking which of them survive a split.
COMPONENTS = 24
# Tucker congruence between the two half-samples. Below this the "dimension" is
# an artefact of which users happened to be in the sample.
REPLICATION_FLOOR = 0.85
SEEDS = ROOT / "seeds" / "taste-dimensions.yaml"
SOURCE = ("factored from MovieLens ml-25m co-preference; named from the "
          "MovieLens tag genome")


@dataclass(frozen=True)
class Axes:
    loadings: np.ndarray       # film x component
    keep: list[int]            # components that replicated, as column indices
    variance: np.ndarray       # share of variance per component
    replication: np.ndarray    # Tucker congruence per component
    movie_ids: np.ndarray      # rows of `loadings`, as MovieLens ids


def _components(matrix, k: int, seed: int):
    """Truncated SVD: the principal components of co-preference."""
    from scipy.sparse.linalg import svds

    # svds starts from a random vector; without a fixed one the signs and the
    # order of near-equal components move between runs on identical input, and
    # this pipeline has already been bitten once by an unstable orientation.
    rng = np.random.default_rng(seed)
    v0 = rng.standard_normal(min(matrix.shape))
    _u, s, vt = svds(matrix, k=k, v0=v0)
    order = np.argsort(-s)
    return (vt[order].T * s[order]), s[order] ** 2 / (s ** 2).sum()


def film_correlation(matrix) -> np.ndarray:
    """Film-by-film correlation from the sparse centred user matrix.

    Computed from the Gram matrix rather than densified: 162,000 users by 646
    films will not fit, and the product that is needed is 646 x 646.
    """
    n = matrix.shape[0]
    gram = np.asarray((matrix.T @ matrix).todense(), dtype=float)
    mu = np.asarray(matrix.sum(axis=0)).ravel() / n
    covariance = gram / n - np.outer(mu, mu)
    sd = np.sqrt(np.clip(np.diag(covariance), 1e-12, None))
    return np.clip(covariance / np.outer(sd, sd), -1, 1)


def _factors(matrix, k: int):
    """Common factors: the same move the moral axes made, for the same reason.

    A component is a weighted sum of everything, so it absorbs whatever is
    peculiar to one film alongside what that film shares with others. Here that
    matters more than it did on the moral side, not less: films share only about
    a tenth of their rating variance, so nine tenths of what a component is built
    from is one film's own idiosyncratic appeal. Factoring the common part is
    what makes a dimension describable, and that is measured rather than assumed:
    the two solutions barely agree (0.81 at the closest pair, 0.2-0.6 for most),
    16 factors replicate against 10 components, and the best of the 1,128 human
    tags describes a factor at 0.67 against a component's 0.46.
    """
    load, _communalities = latent._principal_axis(film_correlation(matrix), k)
    pattern, _phi = latent._promax(load)
    # Rotation is free to reorder importance, so dimension 1 is only reliably the
    # largest if it is sorted afterwards. Seeded names are keyed by position.
    strength = (pattern ** 2).sum(axis=0)
    order = np.argsort(-strength)
    return pattern[:, order], strength[order] / pattern.shape[0]


def _embed(ratings: movielens.Ratings, mask: np.ndarray | None, k: int, seed: int):
    """Film loadings on k latent dimensions, from the given users."""
    matrix, _cols = movielens.centred_matrix(ratings, mask)
    if settings().extraction == "fa":
        return _factors(matrix, k)
    return _components(matrix, k, seed)


def _congruence(a: np.ndarray, b: np.ndarray) -> float:
    return abs(float(a @ b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def extract(ratings: movielens.Ratings | None = None, components: int = COMPONENTS,
            seed: int = 3, progress: Callable[[str], None] | None = None) -> Axes:
    """Factor co-preference, and keep only the dimensions that replicate."""
    ratings = ratings or movielens.load(progress=progress)
    full, variance = _embed(ratings, None, components, seed)

    rng = np.random.default_rng(seed)
    unique = np.unique(ratings.users)
    rng.shuffle(unique)
    half = set(unique[:len(unique) // 2].tolist())
    mask = np.fromiter((int(u) in half for u in ratings.users), bool, len(ratings.users))
    first, _ = _embed(ratings, mask, components, seed)
    second, _ = _embed(ratings, ~mask, components, seed)

    # Greedy matching: each dimension of the first half claims its best partner
    # in the second, and a claimed partner cannot be claimed twice. Without the
    # exclusion one strong dimension in the second half flatters several in the
    # first, and everything looks like it replicates.
    taken: set[int] = set()
    replication = []
    for k in range(components):
        best, who = 0.0, None
        for j in range(components):
            if j in taken:
                continue
            score = _congruence(first[:, k], second[:, j])
            if score > best:
                best, who = score, j
        if who is not None:
            taken.add(who)
        replication.append(best)

    keep = [k for k in range(components) if replication[k] >= REPLICATION_FLOOR]
    if progress:
        progress(f"  {full.shape[0]} films, {ratings.n_users:,} users, "
                 f"{components} components extracted")
        progress(f"  {len(keep)} replicate at {REPLICATION_FLOOR} or better")
    return Axes(full, keep, variance, np.array(replication), ratings.movie_ids)


def curated(path: Path | None = None) -> dict[int, dict[str, Any]]:
    """The hand-written names, keyed by dimension number (1-based)."""
    import yaml

    data = yaml.safe_load((path or SEEDS).read_text()) or {}
    out = {}
    for row in data.get("dimensions", []):
        out[int(row["dim_id"])] = {
            "pole_high": row.get("pole_high"),
            "pole_low": row.get("pole_low"),
            "status": row.get("status", "unnamed"),
            "anchor": row.get("anchor"),
        }
    return out


def orient(loadings: np.ndarray, column: int, correlations: np.ndarray,
           anchor: str | None, tags: dict[int, str]) -> tuple[np.ndarray, bool]:
    """Turn a component so its high pole is the anchor tag's end.

    Returns the (possibly negated) tag correlations and whether it flipped.
    `loadings` is modified in place, because everything downstream — the film
    positions, the adjusted moral scores — has to agree with the labels.
    """
    if not anchor:
        return correlations, False
    tag_id = next((t for t, name in tags.items() if name == anchor), None)
    if tag_id is None:
        raise ValueError(f"anchor tag {anchor!r} is not in the MovieLens genome")
    if correlations[tag_id - 1] >= 0:
        return correlations, False
    loadings[:, column] = -loadings[:, column]
    return -correlations, True


def store(axes: Axes, ratings: movielens.Ratings,
          progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Write the dimensions and every film's place on them."""
    tags, genome, complete = movielens.tag_genome(axes.movie_ids)
    n_tags = max(tags)
    names = curated()
    film_of = ratings.film_of
    now = db.now()

    loadings = axes.loadings.copy()
    dims, places, flipped = [], [], []
    for column in axes.keep:
        # Indexed by the component's OWN column, never by its position in
        # `keep`. `keep` is [0..10, 13, 14, 22]; using the position silently
        # reads column 11 for dimension 14 and raises nothing at all.
        dim_id = column + 1
        entry = names.get(dim_id, {"status": "unnamed"})

        values = loadings[complete, column]
        correlations = np.nan_to_num(np.array(
            [np.corrcoef(genome[:, t], values)[0, 1] for t in range(n_tags)]))
        correlations, did_flip = orient(loadings, column, correlations,
                                        entry.get("anchor"), tags)
        if did_flip:
            flipped.append(dim_id)
            if progress:
                progress(f"  dim {dim_id}: flipped to keep "
                         f"'{entry['pole_high']}' on {entry['anchor']!r}")

        order = np.argsort(correlations)
        dims.append((dim_id, entry.get("pole_high"), entry.get("pole_low"),
                     float(axes.variance[column]), float(axes.replication[column]),
                     float(np.abs(correlations).max()),
                     json.dumps([tags[t + 1] for t in order[-6:][::-1]]),
                     json.dumps([tags[t + 1] for t in order[:6]]),
                     entry.get("status", "unnamed"), SOURCE, now))
        for row, movie in enumerate(axes.movie_ids):
            places.append((film_of[int(movie)], dim_id, float(loadings[row, column])))

    db.init_db()
    with db.connect() as con:
        con.execute("DELETE FROM film_taste")
        con.execute("DELETE FROM taste_dimensions")
        con.executemany(
            "INSERT INTO taste_dimensions (dim_id, pole_high, pole_low, variance, "
            "replication, evidence, tags_high, tags_low, status, source, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)", dims)
        con.executemany(
            "INSERT INTO film_taste (film_id, dim_id, position) VALUES (?,?,?)",
            places)

    if progress:
        progress(f"  stored {len(dims)} dimensions, {len(places):,} film placements")
    return {"dimensions": len(dims), "placements": len(places),
            "films": len({p[0] for p in places}), "flipped": flipped,
            "named": sum(1 for d in dims if d[8] == "named")}
