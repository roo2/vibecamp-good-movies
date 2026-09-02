"""The MovieLens side of the taste layer: the join, and the tag genome.

25 million ratings is far more than is needed. The useful part is every rating a
MovieLens user gave to a film WE hold, because those users are dense stand-ins
for the sparse raters this project actually has. The join is on IMDb id, which
is exact — MovieLens ships `links.csv` for precisely this — so none of the
title-matching guesswork that has burned this project before.

LICENCE. ml-25m is licensed for non-commercial research and may NOT be
redistributed. Nothing here writes ratings into the atlas database or the corpus
export: the callers store only aggregates over our own films — a similarity
matrix, and film positions on derived dimensions. The cache this module writes
does hold ratings verbatim, which is why it goes under `data/`, ignored whole by
git. Keep it that way.

The scan of ratings.csv takes minutes, so its result is cached. The cache is
keyed by the set of films it was built from: enlarge the corpus and it rebuilds
itself, because a join that silently predates twenty new films would place those
films nowhere and report no error.
"""
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from .. import db
from ..config import settings


@dataclass(frozen=True)
class Ratings:
    """Every MovieLens rating that lands on a film in our corpus."""

    users: np.ndarray          # MovieLens user id, per rating
    movies: np.ndarray         # MovieLens movie id, per rating
    stars: np.ndarray          # the rating itself, 0.5 - 5.0
    movie_ids: np.ndarray      # our films, as MovieLens ids, sorted
    film_ids: np.ndarray       # the same films, as our ids, aligned to movie_ids

    @property
    def film_of(self) -> dict[int, str]:
        return {int(m): str(f) for m, f in zip(self.movie_ids, self.film_ids)}

    @property
    def n_users(self) -> int:
        return int(len(np.unique(self.users)))


class MovieLensMissing(RuntimeError):
    """Raised rather than half-building a taste layer out of nothing."""


def require() -> Path:
    s = settings()
    if not s.has_movielens:
        raise MovieLensMissing(
            f"MovieLens ml-25m not found at {s.movielens_dir}. Download it from "
            "https://grouplens.org/datasets/movielens/25m/ and extract it there, "
            "or set MOVIELENS_DIR. It is licensed for non-commercial research and "
            "is deliberately not vendored into this repository.")
    return s.movielens_dir


def corpus_links() -> dict[int, str]:
    """MovieLens movie id -> our film id, for every film we can match."""
    ours: dict[int, str] = {}
    with db.connect(read_only=True) as con:
        for row in con.execute(
                "SELECT film_id, imdb_id FROM films "
                "WHERE imdb_id IS NOT NULL AND imdb_id<>''"):
            try:
                ours[int(str(row["imdb_id"]).lstrip("t"))] = row["film_id"]
            except ValueError:
                continue

    links: dict[int, str] = {}
    with open(require() / "links.csv", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                imdb = int(row["imdbId"])
            except ValueError:
                continue
            if imdb in ours:
                links[int(row["movieId"])] = ours[imdb]
    return links


def _fingerprint(links: dict[int, str]) -> str:
    """What the cache was built from — the exact set of joined films."""
    joined = ",".join(sorted(links.values()))
    return hashlib.sha256(joined.encode()).hexdigest()[:16]


def load(progress: Callable[[str], None] | None = None,
         rebuild: bool = False) -> Ratings:
    """Every rating on one of our films, from cache when the corpus is unchanged."""
    links = corpus_links()
    if not links:
        raise MovieLensMissing(
            "no film in the corpus could be matched to MovieLens — check that "
            "films carry imdb_id (`atlas backfill-metadata` fills them in)")
    cache = settings().derived_dir / "movielens-join.npz"
    stamp = _fingerprint(links)

    if cache.exists() and not rebuild:
        held = np.load(cache, allow_pickle=True)
        if str(held["fingerprint"]) == stamp:
            if progress:
                progress(f"  reusing the cached join ({len(held['users']):,} "
                         f"ratings on {len(links)} films)")
            return Ratings(held["users"], held["movies"], held["stars"],
                           held["movie_ids"], held["film_ids"])
        if progress:
            progress("  corpus has changed since the cached join — rescanning")

    keep = set(links)
    users, movies, stars = [], [], []
    total = 0
    # Hand-parsed rather than csv.reader: this loop runs 25 million times and the
    # reader's per-row object churn dominates everything else in the pipeline.
    with open(require() / "ratings.csv") as fh:
        fh.readline()
        for line in fh:
            total += 1
            u_end = line.index(",")
            m_end = line.index(",", u_end + 1)
            movie = int(line[u_end + 1:m_end])
            if movie in keep:
                users.append(int(line[:u_end]))
                movies.append(movie)
                stars.append(float(line[m_end + 1:line.index(",", m_end + 1)]))
            if progress and total % 5_000_000 == 0:
                progress(f"  scanned {total // 1_000_000}M ratings")

    order = sorted(links)
    out = Ratings(
        np.array(users, dtype=np.int32),
        np.array(movies, dtype=np.int32),
        np.array(stars, dtype=np.float32),
        np.array(order, dtype=np.int64),
        np.array([links[m] for m in order]),
    )
    np.savez_compressed(cache, users=out.users, movies=out.movies, stars=out.stars,
                        movie_ids=out.movie_ids, film_ids=out.film_ids,
                        fingerprint=np.array(stamp))
    if progress:
        progress(f"  scanned {total:,} ratings; kept {len(out.users):,} on "
                 f"{len(links)} of our films ({len(out.users)/max(total,1):.1%})")
        progress(f"  {out.n_users:,} MovieLens users touch our corpus")
    return out


def tag_genome(movie_ids: np.ndarray) -> tuple[dict[int, str], np.ndarray, np.ndarray]:
    """The 1,128-tag genome, for the films we hold.

    Returns the tag names, the relevance matrix for films that HAVE a full row,
    and the mask saying which films those were. The mask matters: the genome
    covers about a quarter of MovieLens, so naming evidence is drawn from a
    subset and the caller must not assume alignment with the full film list.
    """
    root = require()
    tags: dict[int, str] = {}
    with open(root / "genome-tags.csv") as fh:
        fh.readline()
        for line in fh:
            tid, name = line.rstrip("\n").split(",", 1)
            tags[int(tid)] = name.strip().strip('"')

    n_tags = max(tags)
    index = {int(m): i for i, m in enumerate(movie_ids)}
    scores = np.full((len(movie_ids), n_tags + 1), np.nan, dtype=np.float32)
    with open(root / "genome-scores.csv") as fh:
        fh.readline()
        for line in fh:
            a = line.index(",")
            b = line.index(",", a + 1)
            row = index.get(int(line[:a]))
            if row is not None:
                scores[row, int(line[a + 1:b])] = float(line[b + 1:])

    complete = ~np.isnan(scores[:, 1:]).any(axis=1)
    return tags, scores[complete][:, 1:], complete


def centred_matrix(ratings: Ratings, mask: np.ndarray | None = None):
    """Users x films, with each user centred on their own average.

    The centring is the whole point: without it, "rates everything highly"
    reads as agreement with everyone, and the first thing any factoring finds
    is how generous each rater is. Centred, only agreeing about which films are
    better THAN THAT USER'S OWN AVERAGE counts.

    Returns the sparse matrix and the column order (MovieLens ids), so callers
    can map columns back to our films.
    """
    from scipy import sparse

    users = ratings.users if mask is None else ratings.users[mask]
    movies = ratings.movies if mask is None else ratings.movies[mask]
    stars = ratings.stars if mask is None else ratings.stars[mask]

    cols = [int(m) for m in ratings.movie_ids]
    col_of = {m: i for i, m in enumerate(cols)}
    rows = np.searchsorted(np.unique(users), users)
    matrix = sparse.csr_matrix(
        (stars, (rows, [col_of[int(m)] for m in movies])),
        shape=(int(rows.max()) + 1, len(cols)), dtype=np.float32)

    counts = np.diff(matrix.indptr)
    means = np.divide(np.asarray(matrix.sum(axis=1)).ravel(), np.maximum(counts, 1))
    matrix.data -= np.repeat(means, counts)
    return matrix, cols
