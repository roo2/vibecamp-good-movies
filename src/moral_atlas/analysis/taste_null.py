"""The permutation test, run again on verdicts with taste subtracted out.

The atlas draws observed eigenvalues against the 95th percentile of a null that
shuffles each proposition's own answers: is this more structure than the margins
hand out free? This asks the harder version — is it more structure than the
margins hand out free ONCE what a film's taste position can predict is removed.

Two hundred permutations over a residualised matrix is far too slow for a page
load, so the answer is stored. Anything stored can go stale, and a stale chart
that still draws is worse than no chart: it asserts a result nothing produced
any more, with nothing on screen to say so. So every row carries a fingerprint
of the inputs that made it, and `load` refuses to return a row whose inputs have
moved. Re-run `atlas taste-null` after any reanalysis and it comes back.

THE CONTROL IS NOT OPTIONAL. Residualising can only use films that have a taste
position — 543 of 565 on this corpus — so an adjusted chart read against the
unadjusted one would show a drop that is partly just the smaller corpus. Each
row therefore stores the same films run with taste left in, which is what the
adjusted numbers should be read against.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from .. import db


def fingerprint(scorer: str, variant: str, bank_version: str) -> str:
    """What the stored answer was computed from.

    Counts rather than hashes: the three inputs that can move are how many
    verdicts the bank holds, how many films have a taste position, and how many
    taste dimensions there are. Any of those changing means the residuals — and
    therefore the test — are different.
    """
    with db.connect(read_only=True) as con:
        verdicts = con.execute(
            "SELECT COUNT(*) n FROM model_verdicts WHERE scorer=? AND variant=? "
            "AND bank_version=?", [scorer, variant, bank_version]).fetchone()["n"]
        try:
            placed = con.execute("SELECT COUNT(*) n FROM film_taste").fetchone()["n"]
            dims = con.execute(
                "SELECT COUNT(*) n FROM taste_dimensions").fetchone()["n"]
        except Exception:
            placed = dims = 0
    return f"v{verdicts}:p{placed}:d{dims}"


def compute(scorer: str, variant: str, bank_version: str,
            n_iter: int = 200) -> dict[str, Any] | None:
    """Residualise every proposition on the taste dimensions, then re-run Horn."""
    import numpy as np
    from sklearn.linear_model import Ridge

    from . import latent

    with db.connect(read_only=True) as con:
        taste: dict[str, dict[int, float]] = defaultdict(dict)
        for row in con.execute("SELECT film_id, dim_id, position FROM film_taste"):
            taste[row["film_id"]][row["dim_id"]] = row["position"]
    dims = sorted({d for v in taste.values() for d in v})
    if not dims:
        return None

    data = latent.response_matrix(scorer=scorer, bank_version=bank_version,
                                  variant=variant)
    films = list(data["films"])
    matrix = np.asarray(data["matrix"], dtype=float)
    have = [i for i, f in enumerate(films) if len(taste.get(f, {})) == len(dims)]
    if len(have) < 100:
        return None

    control = matrix[have]
    positions = np.array([[taste[films[i]][d] for d in dims] for i in have], float)
    positions = (positions - positions.mean(0)) / positions.std(0)

    residual = control.copy()
    for column in range(control.shape[1]):
        engaged = control[:, column] != 0
        # Too few films to fit fourteen predictors against; left as it is rather
        # than fitted to noise.
        if engaged.sum() < 20:
            continue
        y = control[engaged, column]
        fit = Ridge(alpha=1.0).fit(positions[engaged], y)
        residual[engaged, column] = y - fit.predict(positions[engaged])

    adjusted = latent.parallel_analysis(residual, n_iter=n_iter)
    baseline = latent.parallel_analysis(control, n_iter=n_iter)
    return {
        "films": len(have),
        "eigenvalues": [float(x) for x in adjusted["observed"]],
        "null_threshold": [float(x) for x in adjusted["null_threshold"]],
        "control_eigenvalues": [float(x) for x in baseline["observed"]],
        "control_null_threshold": [float(x) for x in baseline["null_threshold"]],
        "n_factors": adjusted["n_factors"],
        "control_n_factors": baseline["n_factors"],
    }


def store(scorer: str, variant: str, bank_version: str, result: dict[str, Any]) -> None:
    db.init_db()
    with db.connect() as con:
        con.execute(
            "INSERT OR REPLACE INTO null_test_adjusted "
            "(scorer, variant, bank_version, films, eigenvalues, thresholds, "
            " control_eigen, control_thresh, source_fingerprint, computed_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            [scorer, variant, bank_version, result["films"],
             json.dumps(result["eigenvalues"]), json.dumps(result["null_threshold"]),
             json.dumps(result["control_eigenvalues"]),
             json.dumps(result["control_null_threshold"]),
             fingerprint(scorer, variant, bank_version),
             datetime.now(timezone.utc).isoformat()])


def load(scorer: str, variant: str, bank_version: str) -> dict[str, Any] | None:
    """The stored answer, or nothing if its inputs have moved since.

    Returning nothing is the point. A chart drawn from a row whose corpus has
    changed asserts a result nothing produced any more, and there is no way to
    tell by looking at it.
    """
    try:
        with db.connect(read_only=True) as con:
            row = con.execute(
                "SELECT films, eigenvalues, thresholds, control_eigen, control_thresh, "
                "source_fingerprint, computed_at FROM null_test_adjusted "
                "WHERE scorer=? AND variant=? AND bank_version=?",
                [scorer, variant, bank_version]).fetchone()
    except Exception:
        return None
    if not row:
        return None
    if row["source_fingerprint"] != fingerprint(scorer, variant, bank_version):
        return None
    return {
        "films": row["films"],
        "eigenvalues": json.loads(row["eigenvalues"] or "[]"),
        "null_threshold": json.loads(row["thresholds"] or "[]"),
        "control_eigenvalues": json.loads(row["control_eigen"] or "[]"),
        "control_null_threshold": json.loads(row["control_thresh"] or "[]"),
        "computed_at": row["computed_at"],
    }
