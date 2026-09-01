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

import json

from typing import Any

from fastapi import APIRouter, HTTPException, status

from ... import db
from ...analysis import factor_detail, factor_names, latent
from ...config import settings
from ...llm.schemas import MAX_STRENGTH

router = APIRouter(prefix="/api/factors", tags=["factors"])

# Scorers whose run is not worth putting in front of a reader, and why.
#
# Withdrawn from the interface, not from the database: the runs stay, because
# "this model was tried and could not do it" is a finding about the model and
# deleting it would leave the impression nobody had asked.
WITHDRAWN = {
    # Dolphin is BACK, and the entry it used to have was wrong. It read "8B
    # parameters, and it shows": the configured model is 24B and the failure was
    # never capacity. Asked for 298 verdicts in one reply it broke; asked for 40
    # at a time it scores a film with no failed slices at all.
    #
    # It is shown because the atlas is an audit page and a weak reader is a
    # result. What it is weak at is worth being precise about, because it is not
    # what anyone expected: it SCORES about as well as deepseek — engaging 223
    # of 298 propositions on The Return of the King against deepseek's 193, and
    # affirming 87% of what it engages against deepseek's 93%, so it is the less
    # acquiescent of the two. What it cannot do is WRITE the propositions. 38%
    # of its harvest are cross-film duplicates against deepseek's 0.3%, its
    # three highest-support items are paraphrases of the prompt's own examples,
    # and 188 of its 213 items are claims no film disagrees with. That leaves 25
    # usable propositions and one axis, and the count does not move as films are
    # added: 20 survivors at 43 films, 22 at 145.
    #
    # The picker prints its film and factor counts beside deepseek's, which is
    # the honest way to show a reader the difference.
    # Scored more films than any other model and engaged fewer propositions than
    # any other model: 564 films against 71 usable items, 8% of the grid. Two
    # propositions can only be compared over the films that answered both, and
    # its median pair shares one film — so nothing it produced can clear a
    # significance test, however many films are added.
    "grok": "answers too few propositions per film for any axis to reach significance",
}

# Banks whose propositions were written by more than one model. The writer is
# otherwise read off the bank name, which works only while a bank has one
# author; a pooled bank would report itself as written by "pooled".
POOLED_WRITERS = {"pooled": "dolphin + deepseek"}

_cache: dict[str, Any] = {}


def _adjusted_null_test(scorer: str, variant: str, bank: str) -> dict[str, Any] | None:
    """The permutation test with taste subtracted out, if it is still current.

    `taste_null.load` returns nothing when the corpus has moved since the answer
    was computed, so a stale chart is never drawn. Regenerate with
    `atlas taste-null`.
    """
    from ...analysis import taste_null

    return taste_null.load(scorer, variant, bank)


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

    # One row per READING, not per model — because who wrote the propositions
    # turns out to matter as much as who answered them, and collapsing to one
    # row per scorer hid that entirely.
    #
    # The two roles fail in different ways and the picker should let a reader
    # see it. Measured across all four combinations of these two models: as a
    # WRITER, dolphin produces 98 contested propositions out of 218 where
    # deepseek produces 72 out of 297. As a READER, deepseek recovers six axes
    # replicating at 0.49-0.65 from either bank, while dolphin recovers one
    # from its own bank and fourteen from deepseek's — eleven of those built on
    # four propositions or fewer — replicating at 0.20-0.32. Same reader,
    # opposite failures, depending on whose questions it was given.
    #
    # A run is only offered once its axes have been named, since an unnamed one
    # has nothing to show; a scorer with no named run keeps its largest, so a
    # model that has been scored but not analysed does not vanish silently.
    readings: list[dict[str, Any]] = []
    unnamed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row["scorer"] in WITHDRAWN:
            continue
        entry = dict(row)
        # The bank is named after whoever wrote it, which is the one place that
        # authorship is recorded at all.
        wrote = (row["bank_version"] or "").split("-")[0] or "unknown"
        # A pooled bank has no single author: its propositions are two banks
        # concatenated. The picker reads "who wrote → who answered", and
        # "pooled" would name a bank rather than answer the question.
        entry["wrote"] = POOLED_WRITERS.get(wrote, wrote)
        entry["reading_id"] = f"{row['scorer']}|{row['bank_version']}|{row['variant']}"
        # The reading the PRODUCT itself reads. The atlas used to open on
        # whichever reading had the most verdicts, which is a fact about how
        # much scoring has been done rather than about which answer is in use —
        # and it meant the page's default disagreed with the recommender.
        entry["product"] = (
            row["scorer"] == settings().product_scorer
            and row["variant"] == settings().product_variant
            and row["bank_version"] == settings().factor_bank
        )
        if row["factors"]:
            readings.append(entry)
        else:
            current = unnamed.get(row["scorer"])
            if current is None or row["verdicts"] > current["verdicts"]:
                unnamed[row["scorer"]] = entry
    for scorer, entry in unnamed.items():
        if not any(r["scorer"] == scorer for r in readings):
            readings.append(entry)
    best = {r["reading_id"]: r for r in readings}
    return {"models": sorted(best.values(), key=lambda row: -row["verdicts"]),
            # Named rather than silently absent, so the page can say a model was
            # tried and withdrawn instead of implying it was never run.
            "withdrawn": [{"scorer": s, "reason": r} for s, r in sorted(WITHDRAWN.items())]}


# Declared BEFORE /{scorer}, or the path parameter swallows "sets" and the
# atlas asks for a model of that name.
@router.get("/sets")
def get_film_sets() -> dict[str, Any]:
    """The named groups of films the atlas can highlight, with their sources.

    Sent whole rather than per-set: six lists of film ids is a few KB, and the
    picker has to know what exists before a reader picks anything.
    """
    from ...analysis import film_sets

    return {"sets": film_sets.all_sets()}


# Also before /{scorer}, for the same reason.
@router.get("/taste")
def get_taste_dimensions() -> dict[str, Any]:
    """The dimensions of taste, and where each film sits on them.

    Served beside the moral axes rather than merged into them: they answer a
    different question — who enjoys this, rather than what it argues — and the
    relationship between the two is itself a result worth showing.

    `status` travels with every dimension because three of them have no name.
    1,128 human tags could not characterise them, and a reader has to be able to
    tell "we know what this is" from "this is real and we do not know what it
    is". Three more are franchise artefacts of a 546-film corpus and say so.
    """
    import json

    with db.connect(read_only=True) as con:
        try:
            rows = con.execute(
                "SELECT dim_id, pole_high, pole_low, variance, replication, evidence, "
                "tags_high, tags_low, status, source FROM taste_dimensions "
                "ORDER BY variance DESC").fetchall()
            places = con.execute(
                "SELECT t.film_id, t.dim_id, t.position, f.title, f.year "
                "FROM film_taste t JOIN films f USING (film_id)").fetchall()
            # The measured figures the page quotes. They used to be typed into
            # the components, where a number that changed could go on being
            # asserted with nothing to show it had.
            measured = con.execute(
                "SELECT key, value, display, note, source, measured_at "
                "FROM findings").fetchall()
        except Exception:
            # Nothing derived yet: the atlas hides the section rather than erroring.
            return {"dimensions": [], "films": [], "findings": {}}

    films: dict[str, dict[str, Any]] = {}
    for row in places:
        entry = films.setdefault(
            row["film_id"], {"film_id": row["film_id"], "title": row["title"],
                             "year": row["year"], "position": {}})
        entry["position"][str(row["dim_id"])] = round(row["position"], 4)

    return {
        "dimensions": [
            {"dim_id": r["dim_id"], "pole_high": r["pole_high"],
             "pole_low": r["pole_low"], "variance": r["variance"],
             "replication": r["replication"], "evidence": r["evidence"],
             "tags_high": json.loads(r["tags_high"] or "[]"),
             "tags_low": json.loads(r["tags_low"] or "[]"),
             "status": r["status"], "source": r["source"]}
            for r in rows
        ],
        "films": list(films.values()),
        "findings": {
            r["key"]: {"value": r["value"], "display": r["display"],
                       "note": r["note"], "source": r["source"],
                       "measured_at": r["measured_at"]}
            for r in measured
        },
    }


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
    # STRONGEST FIRST. Only six of these are shown, so which six is the whole
    # question, and this appended them in `groups` iteration order — which is
    # bank insertion order, an arbitrary corner of the factor. The same defect
    # was found and fixed in the naming prompt and in the proposition list
    # below; this was the third copy of it, and the one on the page whose job
    # is to let a reader judge a name against its evidence.
    loading = report.get("loading") or {}
    members: dict[int, list[str]] = {}
    for item_id, factor in sorted(report["groups"].items(),
                                  key=lambda kv: -abs(loading.get(kv[0], 0.0))):
        members.setdefault(factor, []).append(texts.get(item_id, item_id))

    # Where every film sits on every factor, and what put it there. Sent with
    # the index rather than fetched per factor: it is the evidence for the axis,
    # and an axis whose evidence costs an extra round trip is one most readers
    # will take on trust.
    detail = factor_detail.detail(scorer, bank, variant, report["groups"], texts,
                                  distance=report.get("distance"),
                                  loadings=report.get("loading"),
                                  vectors=report.get("loadings"))

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
        "unanimous_items": report.get("unanimous_items", 0),
        "replication": report.get("replication", []),
        "max_recoverable": report["max_recoverable"],
        "n_factors": report["n_factors"],
        "n_clear_factors": report["n_clear_factors"],
        "eigenvalues": report["eigenvalues"],
        "null_threshold": report["null_threshold"],
        # The same test run again on verdicts with the taste-predictable part
        # removed. Precomputed: two hundred permutations over a residualised
        # matrix does not belong inside a page load. Carries its own control,
        # because the adjusted run can only use films that have a taste
        # position and a chart comparing 565 against 543 would show a drop that
        # is partly just the smaller corpus.
        "adjusted_null_test": _adjusted_null_test(scorer, variant, bank),
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
    from ...analysis.user_scores import PRODUCT_AXES

    payload = film_on_factors(settings().product_scorer, film_id,
                              variant=settings().product_variant,
                              bank=settings().factor_bank)
    # The atlas route this delegates to returns every named axis, because
    # auditing the corpus is what that page is for. A person meeting a film in
    # the app is not auditing anything, and the third axis is one the product
    # does not read: its propositions barely cohere, no ideological list
    # separates along it, and a person cannot be placed on it above noise.
    # Showing it here would put a number beside a film that nothing else uses.
    return {**payload, "factors": (payload.get("factors") or [])[:PRODUCT_AXES]}


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
        # Every factor's loading, so a film's position here is computed the same
        # way the product computes it — by every proposition that speaks to an
        # axis, weighted by how much it does. Reading only the propositions
        # filed under an axis gave this page a different number from the compass
        # for the same film.
        every = {r["item_id"]: json.loads(r["loadings"]) for r in con.execute(
            "SELECT item_id, loadings FROM latent_factor_items WHERE scorer=? "
            "AND variant=? AND bank_version=? AND loadings IS NOT NULL",
            [scorer, variant, bank])}
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
    known = sorted({f["factor_id"] for f in factors})
    for factor in known:
        weighted: list[tuple[float, float]] = []
        for row in rows:
            item = row["item_id"]
            vector = every.get(item)
            if vector is not None and factor < len(vector):
                strength = vector[factor]
            elif groups.get(item) == factor:
                strength = loadings.get(item) or 1.0
            else:
                continue                    # older rows carry only their own axis
            if not strength:
                continue
            direction = -1.0 if strength < 0 else 1.0
            weighted.append((row["value"] * direction / MAX_STRENGTH, abs(strength)))
        if not weighted:
            continue
        mean_weight = sum(w for _v, w in weighted) / len(weighted)
        if not mean_weight:
            continue
        by_factor[factor] = [v * (w / mean_weight) for v, w in weighted]

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
                loadings=loadings, vectors=every),
        })
    return {"film_id": film_id, "title": title["title"] if title else film_id,
            "scorer": scorer, "factors": scored}
