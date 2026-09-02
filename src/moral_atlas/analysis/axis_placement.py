"""Can a PERSON be placed on this axis? The gate the margin cannot supply.

Margin asks whether an axis is really there in the FILMS. That is necessary and
it is not sufficient, because the compass does a different job: shown someone's
film choices, say where they sit. An axis can be solidly present in the corpus
and still be unable to tell one person from another, and such an axis makes a
bad compass reading — a confident-looking marker placed by noise.

That is not hypothetical. On the 2026-09 corpus the axis holding the product's
second slot, "Intrinsic vs Utilitarian", places people at 0.142 against its own
noise ceiling of 0.210 — it cannot. It reached that slot by clearing the null by
22% where the axis behind it cleared by 20%: a two-point gap, which is a tie,
and the tie was being broken by the wrong question. The axis it displaced,
"Authority vs Autonomy", is the best of all four at placing a person (0.604).

WHY NOT SELECT ON IDEOLOGICAL SEPARATION. Because the project reports that these
axes separate ideological lists. Choosing axes for doing that would make the
finding a consequence of the selection rather than evidence about the world.
Nothing here reads a film set.

METHOD is variance components, because the obvious alternative is broken here: a
rater answers a fixed deck, so splitting their answers in half partitions one
small sample and the halves come out mechanically anti-correlated. The tell was
a positive control — split-half on the rater's own loved-rate, which must
replicate — coming back NEGATIVE. So: how much of the spread in a rater's
per-film contributions is BETWEEN raters versus WITHIN one, with the reliability
of a whole profile following by Spearman-Brown.

The null deals each rater the same NUMBER of films at random from the same pool.
That destroys person identity while preserving how much anyone answered, so an
axis cannot look reliable merely because some people rated more films.

Computed where the raters are — the demo box — and stored, because the answer
has to be available on machines that hold the corpus but no user records. The
stored row carries a fingerprint of its inputs and `load` refuses a stale one,
for the same reason `taste_null` does: a gate that silently reflects a corpus
nobody has any more is worse than no gate.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable

from .. import db

# A rater who answered fewer than this tells us too little to place at all, and
# including them adds only within-rater noise to the variance components.
MIN_RATINGS = 5

# How many random deals to build the noise ceiling from.
NULL_DRAWS = 60

# Profiles are reported at this length so the number means "a reliability for
# the deck a real person actually answers", not for one film.
PROFILE_FILMS = 20


def fingerprint(scorer: str, variant: str, bank_version: str) -> str:
    """What the stored verdict was computed from."""
    with db.connect(read_only=True) as con:
        ratings = con.execute("SELECT COUNT(*) n FROM movie_ratings").fetchone()["n"]
        raters = con.execute(
            "SELECT COUNT(DISTINCT user_id) n FROM movie_ratings").fetchone()["n"]
        axes = con.execute(
            "SELECT COUNT(*) n FROM latent_factors WHERE scorer=? AND variant=? "
            "AND bank_version=?", [scorer, variant, bank_version]).fetchone()["n"]
    return f"r{ratings}:u{raters}:a{axes}"


def _icc(groups: list[list[float]]) -> tuple[float, float]:
    """One-way random-effects ICC for unequal group sizes."""
    import numpy as np

    groups = [np.asarray(g, float) for g in groups if len(g) >= 2]
    k = len(groups)
    if k < 2:
        return float("nan"), 0.0
    n = sum(len(g) for g in groups)
    grand = np.concatenate(groups).mean()
    between = sum(len(g) * (g.mean() - grand) ** 2 for g in groups) / (k - 1)
    within = sum(((g - g.mean()) ** 2).sum() for g in groups) / (n - k)
    size = (n - sum(len(g) ** 2 for g in groups) / n) / (k - 1)
    variance = (between - within) / size
    return ((variance / (variance + within)) if (variance + within) > 0 else 0.0), size


def _brown(icc: float, n: float) -> float:
    import numpy as np

    if not np.isfinite(icc) or icc <= 0:
        return 0.0
    return n * icc / (1 + (n - 1) * icc)


def compute(scorer: str, variant: str, bank_version: str,
            progress: Callable[[str], None] | None = None) -> dict[str, Any] | None:
    """Reliability and noise ceiling per axis. None when there is nothing to read."""
    import numpy as np

    from . import user_scores

    axes = user_scores.factor_axes(scorer, variant, bank_version, limit=None)
    stances = user_scores.factor_stances(scorer, variant, bank_version)
    if not axes:
        return None
    axis_ids = [a["dim_id"] for a in axes]

    placed: dict[str, list[float]] = {}
    for film, row in stances.items():
        values = [sum(row[d]) / len(row[d]) if row.get(d) else None for d in axis_ids]
        if all(v is not None for v in values):
            placed[film] = values

    raw: dict[str, list[tuple[str, str]]] = defaultdict(list)
    with db.connect(read_only=True) as con:
        for row in con.execute("SELECT user_id, film_id, reaction FROM movie_ratings "
                               "ORDER BY submitted_at DESC"):
            raw[row["user_id"]].append((row["film_id"], row["reaction"]))

    # The product's own weighting, so this measures the instrument as shipped.
    ratings: dict[str, list[tuple[str, float]]] = {}
    for uid, rows in raw.items():
        mine = [(p.film_id, p.weight) for p in user_scores.rating_preferences(rows)
                if p.weight and p.film_id in placed]
        if len(mine) >= MIN_RATINGS:
            ratings[uid] = mine
    if len(ratings) < 20:
        if progress:
            progress(f"  only {len(ratings)} raters have {MIN_RATINGS}+ usable "
                     f"ratings — too few to place an axis against noise")
        return None

    users = list(ratings)
    rng = random.Random(7)

    def reliability(assignment: dict[str, list[tuple[str, float]]], k: int) -> float:
        icc, size = _icc([[w * placed[f][k] for f, w in assignment[u]] for u in assignment])
        return _brown(icc, PROFILE_FILMS if size <= 0 else size)

    def dealt() -> dict[str, list[tuple[str, float]]]:
        pool = [item for u in users for item in ratings[u]]
        rng.shuffle(pool)
        out, at = {}, 0
        for u in users:
            out[u] = pool[at:at + len(ratings[u])]
            at += len(ratings[u])
        return out

    # The control has to pass or nothing below can be read.
    loved = {u: [1.0 if r == "loved_it" else 0.0 for _f, r in raw[u]
                 if r in user_scores.SEEN_REACTIONS] for u in users}
    control, _size = _icc([loved[u] for u in users if len(loved[u]) >= 2])

    out = []
    for k, axis in enumerate(axes):
        observed = reliability(ratings, k)
        null = np.array([reliability(dealt(), k) for _ in range(NULL_DRAWS)])
        ceiling = float(np.percentile(null, 95))
        out.append({
            "dim_id": axis["dim_id"],
            "label": axis.get("label") or axis.get("name") or str(axis["dim_id"]),
            "reliability": float(observed),
            "noise_ceiling": ceiling,
            "places_people": bool(observed > ceiling),
        })
        if progress:
            progress(f"  {out[-1]['label'][:34]:36}{observed:6.3f}  ceiling "
                     f"{ceiling:.3f}  "
                     f"{'places people' if out[-1]['places_people'] else 'AT NOISE'}")

    return {"raters": len(users), "control": float(control), "axes": out}


def store(scorer: str, variant: str, bank_version: str,
          result: dict[str, Any]) -> None:
    db.init_db()
    with db.connect() as con:
        con.execute(
            "INSERT OR REPLACE INTO axis_placement (scorer, variant, bank_version, "
            "raters, control, axes, source_fingerprint, computed_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            [scorer, variant, bank_version, result["raters"], result["control"],
             json.dumps(result["axes"]), fingerprint(scorer, variant, bank_version),
             datetime.now(timezone.utc).isoformat()])


def load(scorer: str, variant: str, bank_version: str) -> dict[int, bool] | None:
    """dim_id -> whether it can place a person, or None if nothing usable.

    Returns None rather than a default when the row is missing OR its inputs
    have moved, so a caller falls back to its previous behaviour instead of
    silently gating on a verdict computed for a corpus that no longer exists.
    """
    try:
        with db.connect(read_only=True) as con:
            row = con.execute(
                "SELECT axes, source_fingerprint FROM axis_placement WHERE scorer=? "
                "AND variant=? AND bank_version=?",
                [scorer, variant, bank_version]).fetchone()
    except Exception:
        return None
    if not row:
        return None
    if row["source_fingerprint"] != fingerprint(scorer, variant, bank_version):
        return None
    try:
        axes = json.loads(row["axes"] or "[]")
    except Exception:
        return None
    verdicts = {int(a["dim_id"]): bool(a["places_people"]) for a in axes}
    # If nothing passes, the gate has nothing to say and must not empty the
    # compass. Better the old ordering than no axes at all.
    return verdicts if any(verdicts.values()) else None
