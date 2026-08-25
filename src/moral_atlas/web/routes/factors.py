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
from ...analysis import factor_detail, factor_names, latent
from ...config import settings

router = APIRouter(prefix="/api/factors", tags=["factors"])

# Scorers whose run is not worth putting in front of a reader, and why.
#
# Withdrawn from the interface, not from the database: the runs stay, because
# "this model was tried and could not do it" is a finding about the model and
# deleting it would leave the impression nobody had asked.
WITHDRAWN = {
    # 8B parameters, and it shows. 30 films scored out of 570 before it stopped
    # producing usable structured output, and the axes it did yield came from
    # too little to mean anything.
    "dolphin": "too small a model to complete the corpus",
    # Scored more films than any other model and engaged fewer propositions than
    # any other model: 564 films against 71 usable items, 8% of the grid. Two
    # propositions can only be compared over the films that answered both, and
    # its median pair shares one film — so nothing it produced can clear a
    # significance test, however many films are added.
    "grok": "answers too few propositions per film for any axis to reach significance",
}

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

    # One row per model. A scorer can have verdicts against more than one bank —
    # an abandoned run, or an earlier experiment against a shared bank — and
    # every one of those became its own button, so the same model appeared
    # several times and more than one could read as selected at once. The run
    # with the most verdicts is the one that model is actually being judged on.
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row["scorer"] in WITHDRAWN:
            continue
        current = best.get(row["scorer"])
        if current is None or row["verdicts"] > current["verdicts"]:
            best[row["scorer"]] = dict(row)
    return {"models": sorted(best.values(), key=lambda row: -row["verdicts"]),
            # Named rather than silently absent, so the page can say a model was
            # tried and withdrawn instead of implying it was never run.
            "withdrawn": [{"scorer": s, "reason": r} for s, r in sorted(WITHDRAWN.items())]}


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
        estimator = factor_names.estimator_for(scorer, variant, bank)
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

    # Where every film sits on every factor, and what put it there. Sent with
    # the index rather than fetched per factor: it is the evidence for the axis,
    # and an axis whose evidence costs an extra round trip is one most readers
    # will take on trust.
    detail = factor_detail.detail(scorer, bank, variant, report["groups"], texts,
                                  distance=report.get("distance"),
                                  loadings=report.get("loading"))

    payload = {
        "scorer": scorer,
        "variant": variant,
        "bank_version": bank,
        # Which reading produced these, so the page can describe the method it
        # actually used rather than the one it used to use.
        "estimator": estimator,
        # What the null test itself required, so the page can state the bar it
        # actually applied rather than one layered on top of it.
        "margin_floor": report["margin_floor"],
        "shown": len(factors),
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
            {**factor,
             "examples": members.get(factor["factor_id"], [])[:6],
             **detail.get(factor["factor_id"], {})}
            for factor in factors
        ],
    }
    _cache[key] = {"fingerprint": fingerprint, "payload": payload}
    return payload


@router.get("/product/films/{film_id}")
def product_film_axes(film_id: str) -> dict[str, Any]:
    """One film on the axes the PRODUCT reads, without naming the model.

    The app shows a person where a recommendation stands morally, and which
    model produced those axes is a deployment decision — `ATLAS_PRODUCT_SCORER`
    — not something a phone screen should hard-code. Declared above the
    `/{scorer}/...` route on purpose: otherwise "product" is read as the name of
    a model and 404s.
    """
    return film_on_factors(settings().product_scorer, film_id,
                           variant=settings().product_variant)


@router.get("/{scorer}/films/{film_id}")
def film_on_factors(
    scorer: str, film_id: str, variant: str = "subs", bank: str = "",
) -> dict[str, Any]:
    """One film against every factor, with the verdicts behind each position.

    The reverse of the factor view, and the one a reader reaches for first:
    they know the film, and want to see what the instrument made of it.
    """
    db.init_db()
    bank = bank or f"{scorer}-{variant}"
    texts = factor_names.bank_texts(bank)
    factors = factor_names.load(scorer, variant, bank)
    if not factors:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"{scorer!r} has no named factors.")

    with db.connect(read_only=True) as con:
        groups = {r["item_id"]: r["factor_id"] for r in con.execute(
            "SELECT item_id, factor_id FROM latent_factor_items WHERE scorer=? "
            "AND variant=? AND bank_version=?", [scorer, variant, bank])}
        loadings = {r["item_id"]: r["loading"] for r in con.execute(
            "SELECT item_id, loading FROM latent_factor_items WHERE scorer=? "
            "AND variant=? AND bank_version=?", [scorer, variant, bank])}
        rows = con.execute(
            "SELECT item_id, value FROM model_verdicts WHERE scorer=? AND variant=? "
            "AND bank_version=? AND film_id=?", [scorer, variant, bank, film_id],
        ).fetchall()
        title = con.execute("SELECT title FROM films WHERE film_id=?",
                            [film_id]).fetchone()

    # Each verdict counted in the direction its proposition points. A factor can
    # hold a proposition and its opposite — films answer them together — so a
    # denial of one is an affirmation of the other, and averaging the raw values
    # would put a film that took a clear side at zero and call it undecided.
    by_factor: dict[int, list[float]] = {}
    for row in rows:
        factor = groups.get(row["item_id"])
        if factor is None:
            continue
        loading = loadings.get(row["item_id"])
        direction = -1.0 if (loading is not None and loading < 0) else 1.0
        by_factor.setdefault(factor, []).append(row["value"] * direction)

    scored = []
    for factor in factors:
        values = by_factor.get(factor["factor_id"], [])
        scored.append({
            "factor_id": factor["factor_id"],
            "name": factor["name"],
            "question": factor["question"],
            "pole_high": factor["pole_high"],
            "pole_low": factor["pole_low"],
            "pole_high_label": factor.get("pole_high_label"),
            "pole_low_label": factor.get("pole_low_label"),
            # None rather than 0 when the film engaged nothing: silence on an
            # axis is not a middling position on it, and a zero would draw as
            # though the film had weighed the question and declined to choose.
            "score": round(sum(values) / len(values), 3) if values else None,
            "items": len(values),
            "verdicts": factor_detail.film_justification(
                scorer, bank, variant, groups, texts, film_id, factor["factor_id"],
                loadings=loadings),
        })
    return {"film_id": film_id, "title": title["title"] if title else film_id,
            "scorer": scorer, "factors": scored}
