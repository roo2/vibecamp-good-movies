"""What the explorer reads now: each model's own discovered axes.

The old `/api/atlas` document is built around a single dimension set that one
model was asked to produce — `dimensions`, the per-axis film rankings, the
reliability battery attacking those eight. None of that survives the shift to
axes discovered from film responses, because there is no longer one answer:
every scorer writes its own bank, scores films against it, and gets its own
factors out. So the shape of this endpoint is a list of models, and everything
else hangs off which one you picked.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from ... import db
from ...analysis import factor_names, latent

router = APIRouter(prefix="/api/factors", tags=["factors"])

_cache: dict[str, Any] = {}


def _fingerprint(scorer: str, variant: str, bank: str) -> tuple:
    """Counts, not file stats — the store is in WAL mode and its mtime lies."""
    with db.connect(read_only=True) as con:
        return (
            con.execute("SELECT COUNT(*) n FROM model_verdicts WHERE scorer=? AND "
                        "bank_version=? AND variant=?", [scorer, bank, variant]).fetchone()["n"],
            con.execute("SELECT COUNT(*) n FROM latent_factors WHERE scorer=? AND "
                        "variant=? AND bank_version=?", [scorer, variant, bank]).fetchone()["n"],
        )


@router.get("")
def list_models() -> dict[str, Any]:
    """Every scorer with verdicts, and whether its axes have been named yet.

    The toggle is built from this rather than from a hardcoded list, so a model
    appears in the interface exactly when it has something to show.
    """
    db.init_db()
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT v.scorer, v.bank_version, v.variant, COUNT(*) verdicts, "
            "COUNT(DISTINCT v.film_id) films, COUNT(DISTINCT v.item_id) items, "
            "(SELECT COUNT(*) FROM latent_factors f WHERE f.scorer=v.scorer "
            " AND f.variant=v.variant AND f.bank_version=v.bank_version) factors "
            "FROM model_verdicts v GROUP BY v.scorer, v.bank_version, v.variant "
            "ORDER BY verdicts DESC"
        ).fetchall()
    return {"models": [dict(row) for row in rows]}


@router.get("/{scorer}")
def get_factors(
    scorer: str, variant: str = "subs", bank: str = "", n_iter: int = 200,
) -> dict[str, Any]:
    """One model's axes, with the evidence that there are that many of them."""
    db.init_db()
    bank = bank or f"{scorer}-{variant}"
    key = (scorer, variant, bank)
    fingerprint = _fingerprint(scorer, variant, bank)
    cached = _cache.get(key)
    if cached and cached["fingerprint"] == fingerprint:
        return cached["payload"]

    factors = factor_names.load(scorer, variant, bank)
    try:
        report = latent.analyse(scorer, bank, n_iter=n_iter, variant=variant)
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nothing scored for {scorer!r} on {bank!r}/{variant!r}: {error}",
        ) from error

    texts = factor_names.bank_texts(bank)
    members: dict[int, list[str]] = {}
    for item_id, factor in report["groups"].items():
        members.setdefault(factor, []).append(texts.get(item_id, item_id))

    payload = {
        "scorer": scorer,
        "variant": variant,
        "bank_version": bank,
        "films": report["films"],
        "items": report["items"],
        "density": report["density"],
        "dropped_items": report["dropped_items"],
        "max_recoverable": report["max_recoverable"],
        "n_factors": report["n_factors"],
        "n_clear_factors": report["n_clear_factors"],
        "eigenvalues": report["eigenvalues"],
        "null_threshold": report["null_threshold"],
        "margins": report["margins"],
        "group_sizes": report["group_sizes"],
        "factors": [
            # A sample of each factor's propositions, so a reader can judge the
            # name against the items rather than taking it on trust.
            {**factor, "examples": members.get(factor["factor_id"], [])[:6]}
            for factor in factors
        ],
    }
    _cache[key] = {"fingerprint": fingerprint, "payload": payload}
    return payload
