"""Every film's moral position, with taste taken out.

The raw position confounds two things a reader cannot separate by eye: what a
film argues, and what kind of film it is. Taste accounts for a fifth of the
leading axis, so a film can sit high on "redemptive" partly because redemptive
films are the sort of film people rate well.

The adjustment is the residual from predicting the moral position out of the
taste dimensions — CROSS-VALIDATED, so what gets removed is the part that
genuinely generalises rather than whatever a fit could absorb in sample. Fitting
in sample would let the model soak up noise and call it taste, and the residual
would then be an understatement of the moral signal rather than a cleaner one.

`taste_explained` is stored beside each position so the interface can say how
much was taken out of each axis, which differs by a lot between them.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

import numpy as np

from .. import db
from ..config import settings
from . import user_scores

# Below this there are more taste predictors than films to fit them against, and
# the "residual" would be mostly the fit chasing noise.
MIN_FILMS = 60


def readings() -> list[tuple[str, str, str]]:
    """Which (scorer, variant, bank) readings get an adjusted copy."""
    s = settings()
    return [(s.product_scorer, s.product_variant, "dolphin-subs"),
            (s.product_scorer, s.product_variant, "pooled-subs")]


def store(progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Residualise every moral axis on the taste dimensions and store it."""
    from sklearn.linear_model import RidgeCV
    from sklearn.model_selection import KFold, cross_val_predict

    with db.connect(read_only=True) as con:
        taste: dict[str, dict[int, float]] = defaultdict(dict)
        for row in con.execute("SELECT film_id, dim_id, position FROM film_taste"):
            taste[row["film_id"]][row["dim_id"]] = row["position"]
    dim_ids = sorted({d for v in taste.values() for d in v})
    if not dim_ids:
        raise RuntimeError("no taste positions — run the taste step first")
    if progress:
        progress(f"  taste positions for {len(taste)} films on "
                 f"{len(dim_ids)} dimensions")

    folds = KFold(5, shuffle=True, random_state=0)
    rows: list[tuple] = []
    explained: dict[str, float] = {}
    for scorer, variant, bank in readings():
        axes = user_scores.factor_axes(scorer, variant, bank, limit=None)
        stances = user_scores.factor_stances(scorer, variant, bank)
        # Only films with a COMPLETE taste row: a film missing one dimension
        # would otherwise be silently dropped by numpy or, worse, aligned to the
        # wrong column.
        films = [f for f in stances if f in taste and len(taste[f]) == len(dim_ids)]
        if len(films) < MIN_FILMS or not axes:
            if progress:
                progress(f"  {bank}: too little overlap ({len(films)} films), skipped")
            continue

        matrix = np.array([[taste[f][d] for d in dim_ids] for f in films], dtype=float)
        matrix = (matrix - matrix.mean(0)) / matrix.std(0)
        position = {f: i for i, f in enumerate(films)}
        if progress:
            progress(f"  {scorer}/{variant}/{bank}: {len(films)} films, "
                     f"{len(axes)} axes")

        for axis in axes:
            dim = axis["dim_id"]
            pairs = [(f, stances[f][dim]) for f in films if stances[f].get(dim)]
            if len(pairs) < MIN_FILMS:
                continue
            keep = [f for f, _ in pairs]
            y = np.array([sum(v) / len(v) for _, v in pairs], dtype=float)
            sub = matrix[[position[f] for f in keep]]
            predicted = cross_val_predict(
                RidgeCV(alphas=np.logspace(-2, 3, 20)), sub, y, cv=folds)
            r2 = 1 - ((y - predicted) ** 2).sum() / ((y - y.mean()) ** 2).sum()
            share = float(max(r2, 0.0))
            label = (axis.get("label") or axis.get("name") or str(dim))[:38]
            explained[f"{bank}:{label}"] = share
            if progress:
                progress(f"    {label:40} taste explains {share:5.1%}")
            for film, residual in zip(keep, y - predicted):
                rows.append((scorer, variant, bank, film, dim, float(residual), share))

    db.init_db()
    with db.connect() as con:
        con.execute("DELETE FROM film_moral_adjusted")
        con.executemany(
            "INSERT INTO film_moral_adjusted (scorer, variant, bank_version, "
            "film_id, dim_id, score, taste_explained) VALUES (?,?,?,?,?,?,?)", rows)
    if progress:
        progress(f"  stored {len(rows):,} taste-adjusted positions")
    return {"positions": len(rows), "films": len({r[3] for r in rows}),
            "taste_explained": explained}
