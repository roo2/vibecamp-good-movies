"""Let the films decide how many dimensions there are.

Every earlier attempt at the axes asked a model to name them, which means the
count was never discovered — `derive_system` takes `n_dims`, and a model asked
for eight axes returns eight. This module never asks. It reads how the films
actually responded to the items and recovers the structure from the responses,
the way the personality factors were found: items that the same films answer the
same way are being driven by the same underlying thing.

WHAT COUNTS AS A RESPONSE. The scoring is sparse — a film's verdict is recorded
only for the items it takes a position on, because "does not address this" is a
real state and not a neutral midpoint. Silence is therefore excluded from the
arithmetic rather than treated as a third value: two items are correlated over
the films that took a position on BOTH of them.

    That reading was impossible when this was written. At 40 films, 82% of item
    pairs shared no film at all and the mean overlap was 0.21, so there was
    nothing to correlate and silence had to be kept as a value to make the
    matrix dense. The cost was severe and measurable: the largest factor in the
    corpus was not a moral position but how talkative a film is — 87% of its
    item loadings shared one sign, and a film's place on it correlated +0.87
    with how many propositions it engaged.

    At 465 films every pair shares at least one film, the mean overlap is 96 and
    the median 86. Normalising the dense reading does not substitute for this:
    centring and scaling each film moves that correlation from +0.87 to -0.86,
    flipping the sign and keeping the coupling, because silence is 63% of the
    matrix and normalising values cannot touch a pattern of zeros.

ACQUIESCENCE. Each film is also judged against its own rate of agreement. The
scorers say "affirms" between 75% and 93% of the time and a film affirms 89% of
what it engages, so "how readily was this film agreed with" is a large signal
that is partly the film and partly the model's habit. Excluding silence without
removing this still over-counted — 5 factors where 3 were planted.

WHERE THIS IS WEAKEST, STATED PLAINLY. The count is trustworthy to the extent
that missingness is a property of FILMS rather than of cells. On planted data
whose silences follow how much each film engages, k is recovered exactly. Spray
the same number of silences uniformly across cells instead and the count
inflates badly — 13 to 15 where 3 were planted — because item pairs then
correlate over unrelated subsets of films, which manufactures eigenvalues. It is
stable rather than noisy: more null sampling does not move it. On this corpus
missingness is a film property, and the count is stable across null seeds. It is
still the assumption the number rests on. `test_the_count_depends_on_how_
engagement_is_distributed` pins it.

There is one more cost, paid knowingly: judging each film against its own rate
spends a degree of freedom, so on complete data with no acquiescence the count
comes back one short.

HOW MANY FACTORS. Horn's parallel analysis. Compute the eigenvalues of the real
item correlation matrix, then do the same for many random matrices of exactly
the same shape, built by permuting each item's column independently. That null
destroys any association BETWEEN items while preserving each item's own
engagement rate and affirm/deny balance, so a factor only counts if it explains
more than the amount of structure those margins produce for free. Keep the
factors whose observed eigenvalue clears the 95th percentile of the null.

This is what makes the count a finding rather than a setting.

A REAL LIMIT, STATED ONCE. Factor analysis conventionally wants several times
more respondents than variables. With 465 films and 298 items that is no longer
inverted, but the correlation matrix still has rank at most the number of films,
so the recoverable ceiling is reported alongside the count. What would carry
most weight is agreement between models: if scorers that harvested different
propositions keep landing on the same k, that is evidence the corpus has that
many joints. They do not currently — one finds eleven and another finds none —
and that disagreement is itself the finding.
"""
from __future__ import annotations

import statistics as st
from typing import Any, Iterable

from .. import db

# An item scored on one film contributes a spike rather than a covariance, and
# 224 of them would dominate the eigenvalues with noise.
MIN_FILMS_PER_ITEM = 3


def response_matrix(
    scorer: str | None = None, bank_version: str = "b1",
    min_films: int = MIN_FILMS_PER_ITEM, variant: str | None = None,
) -> dict[str, Any]:
    """Films x items, dense, in {+1, 0, -1}.

    `scorer=None` reads the atlas's own `scores`; anything else reads that
    model's `model_verdicts`, so the same analysis can be run per model.

    `variant` scopes the whole thing to one evidence condition, and on a mixed
    corpus it should be set. Films read from a plot summary and films read from
    their own dialogue are not answering the same instrument: a Wikipedia plot
    section is an editor's account of which events mattered, and a reception
    section is critics' moral opinions outright, so pooling them with subtitles
    would put "what the encyclopaedia says about this film" and "what the film
    says" into the same correlation matrix and call the result a dimension.
    """
    import numpy as np

    db.init_db()
    with db.connect(read_only=True) as con:
        table = "scores" if scorer is None else "model_verdicts"
        where, args = ["bank_version=?"], [bank_version]
        if scorer is not None:
            where.append("scorer=?")
            args.append(scorer)
        if variant:
            where.append("variant=?")
            args.append(variant)
        rows = con.execute(
            f"SELECT film_id, item_id, value FROM {table} WHERE {' AND '.join(where)}",
            args,
        ).fetchall()
    if not rows:
        raise RuntimeError(
            f"no verdicts for scorer={scorer!r} bank={bank_version!r}"
            + (f" variant={variant!r}" if variant else ""))

    # A film may be scored under several evidence variants; average first so a
    # film counts once however many conditions it was run under.
    cells: dict[tuple[str, str], list[int]] = {}
    for row in rows:
        cells.setdefault((row["film_id"], row["item_id"]), []).append(row["value"])

    films = sorted({f for f, _ in cells})
    engaged: dict[str, set[str]] = {}
    for (film, item) in cells:
        engaged.setdefault(item, set()).add(film)
    items = sorted(i for i, fs in engaged.items() if len(fs) >= min_films)
    dropped = len(engaged) - len(items)
    if len(items) < 2 or len(films) < 3:
        raise RuntimeError(
            f"too little to factor: {len(items)} items on {len(films)} films "
            f"(items need >= {min_films} films each)")

    index = {item: j for j, item in enumerate(items)}
    matrix = np.zeros((len(films), len(items)))
    for row_index, film in enumerate(films):
        for item in items:
            values = cells.get((film, item))
            if values:
                matrix[row_index, index[item]] = sum(values) / len(values)

    return {"films": films, "items": items, "matrix": matrix, "variant": variant,
            "dropped_items": dropped, "density": float((matrix != 0).mean())}


# Below this a pair's correlation is computed from too few films to mean
# anything, and one wild value would enter the matrix as a strong association.
MIN_PAIR_OVERLAP = 8


def _pairwise_correlation(matrix) -> Any:
    """Correlate items over the films that took a position on BOTH of them.

    The strict reading of the question, and the one the module docstring records
    as unanswerable — at 40 films, 82% of item pairs shared no film at all and
    the mean overlap was 0.21. That is no longer true: at 465 films every pair
    shares at least one, the mean overlap is 96 and the median 86, so the
    estimator this corpus could not support is now the estimator it can.

    It matters because the dense reading cannot be rescued by normalising.
    Silence is 63% of the matrix, so an estimator that treats silence as a value
    finds "which films are silent where" as its largest structure, and centring
    or scaling the values does not touch the pattern of zeros — measured, the
    first factor's correlation with a film's engagement count only moves from
    +0.87 to -0.86. Excluding silence from the arithmetic is the one change that
    alters what is being measured: agreement, not co-engagement.

    The cost is a matrix that is no longer guaranteed positive semi-definite,
    because each cell is computed on a different subset of films. Its
    eigenvalues can go slightly negative, which is fine here: the null is built
    with the same estimator, so both sides carry the same artefact.
    """
    import numpy as np

    engaged = (matrix != 0).astype(float)
    n = engaged.T @ engaged
    sx = matrix.T @ engaged                  # sum of i over films engaging i and j
    sxx = (matrix * matrix).T @ engaged
    sxy = matrix.T @ matrix
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_i = sx / n
        cov = sxy / n - mean_i * mean_i.T
        var = sxx / n - mean_i ** 2
        r = cov / np.sqrt(var * var.T)
    r = np.nan_to_num(r, nan=0.0, posinf=0.0, neginf=0.0)
    r[n < MIN_PAIR_OVERLAP] = 0.0
    np.fill_diagonal(r, 1.0)
    return np.clip(r, -1.0, 1.0)


def _film_centred(matrix) -> Any:
    """Each film against its own affirm rate, over the cells it engaged.

    The scorers say "affirms" between 75% and 93% of the time, and a film
    affirms 89% of what it engages, so "how readily was this film agreed with"
    is a large signal that is partly the film and partly the model's habit.
    Subtracting each film's own rate leaves what it affirms RELATIVE to itself,
    which is the part that can distinguish it from another film.

    On planted data with both pathologies present, excluding silence alone still
    over-counted — 5 factors where 3 were planted. With this it recovers 3.
    """
    import numpy as np

    out = matrix.astype(float).copy()
    engaged = out != 0
    counts = engaged.sum(axis=1)
    totals = out.sum(axis=1)
    means = np.divide(totals, np.where(counts == 0, 1, counts))
    out[engaged] -= np.repeat(means, counts)
    out[~engaged] = 0.0
    return out


def _agreement_eigenvalues(matrix) -> Any:
    """Silence excluded, acquiescence removed — and both INSIDE the estimator.

    Doing the centring outside, on the observed matrix only, leaves the null
    uncentred and the comparison meaningless. That mistake is what produced a
    reading of 120 factors on this corpus.
    """
    import numpy as np

    return np.sort(np.linalg.eigvalsh(_pairwise_correlation(_film_centred(matrix))))[::-1]


def parallel_analysis(
    matrix, n_iter: int = 200, percentile: float = 95.0, seed: int = 11,
    margin_floor: float = 0.05,
) -> dict[str, Any]:
    """Horn's test: how many factors beat the structure the margins give free?

    The null permutes each item's column independently. Shuffling the whole
    matrix instead would also destroy each item's engagement rate, and then a
    factor could clear the bar simply by some items being scored more often than
    others — which is not a moral dimension, it is a salience artefact.
    """
    import numpy as np

    observed = _agreement_eigenvalues(matrix)
    rng = np.random.default_rng(seed)
    null = np.empty((n_iter, len(observed)))
    for i in range(n_iter):
        shuffled = matrix.copy()
        for column in range(shuffled.shape[1]):
            rng.shuffle(shuffled[:, column])
        null[i] = _agreement_eigenvalues(shuffled)

    threshold = np.percentile(null, percentile, axis=0)
    above = observed > threshold
    # Factors are retained up to the first failure: a lone later eigenvalue
    # poking above the line is noise, not a ninth dimension.
    retained = int(np.argmin(above)) if not above.all() else int(len(above))

    # How far each factor clears the null, relative to it. A count alone hides
    # the difference between a factor that beats chance by half and one that
    # beats it in the third decimal, and on this corpus the last retained
    # factors do the latter — so `n_factors` on its own would overstate the
    # result every time it was quoted.
    margins = [float((o - t) / t) if t else 0.0
               for o, t in zip(observed[:retained], threshold[:retained])]
    clear = sum(1 for m in margins if m >= margin_floor)

    return {
        "n_factors": retained,
        "n_clear_factors": clear,
        "margin_floor": margin_floor,
        "margins": [round(m, 4) for m in margins],
        "observed": [round(float(v), 4) for v in observed[:20]],
        "null_threshold": [round(float(v), 4) for v in threshold[:20]],
        "max_recoverable": int(min(matrix.shape) - 1),
        "n_iter": n_iter,
        "percentile": percentile,
    }


def item_groups(matrix, items: list[str], k: int,
                seed: int = 11) -> tuple[dict[str, int], dict[str, float]]:
    """Sort items into k groups by how films responded to them.

    Clustering the loadings rather than the raw columns: two items answered the
    same way by the same films have similar loadings on the retained factors,
    which is the operational form of "driven by the same underlying thing".

    Returns the grouping AND how far each item sits from its group's centre.
    Membership alone says an item belongs somewhere; the distance says how much
    it belongs, and every group has a periphery. Anyone showing a reader "what
    this factor is made of" needs the near items, not an arbitrary slice.
    """
    import numpy as np
    from sklearn.cluster import KMeans

    # Nothing beat chance. There is no grouping to return, and returning one
    # group would hand the namer every proposition in the bank and get an axis
    # back — a named, plausible, entirely invented axis with no margin behind it.
    if k < 1:
        return {}, {}
    if k < 2:
        return {item: 0 for item in items}, {item: 0.0 for item in items}
    # Cluster the eigenvectors of the agreement matrix, so membership is decided
    # by the same reading of the data that decided the count.
    correlation = _pairwise_correlation(_film_centred(matrix))
    values, vectors = np.linalg.eigh(correlation)
    loadings = vectors[:, np.argsort(values)[::-1][:k]]
    model = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(loadings)
    labels = model.labels_
    distances = np.linalg.norm(loadings - model.cluster_centers_[labels], axis=1)
    return ({item: int(label) for item, label in zip(items, labels)},
            {item: float(distance) for item, distance in zip(items, distances)})


def analyse(
    scorer: str | None = None, bank_version: str = "b1",
    n_iter: int = 200, min_films: int = MIN_FILMS_PER_ITEM, seed: int = 11,
    variant: str | None = None,
) -> dict[str, Any]:
    """The whole thing for one scorer: how many dimensions, and which items."""
    data = response_matrix(scorer, bank_version, min_films, variant)
    horn = parallel_analysis(data["matrix"], n_iter=n_iter, seed=seed)
    groups, distance = item_groups(data["matrix"], data["items"],
                                   horn["n_clear_factors"], seed=seed)
    sizes: dict[int, int] = {}
    for label in groups.values():
        sizes[label] = sizes.get(label, 0) + 1
    return {
        "scorer": scorer or "opus",
        "variant": variant,
        "films": len(data["films"]),
        "items": len(data["items"]),
        "dropped_items": data["dropped_items"],
        "density": round(data["density"], 4),
        "n_factors": horn["n_factors"],
        "n_clear_factors": horn["n_clear_factors"],
        # The only bar there is, carried out so a reader can be told what it was.
        "margin_floor": horn["margin_floor"],
        "margins": horn["margins"],
        "max_recoverable": horn["max_recoverable"],
        "eigenvalues": horn["observed"],
        "null_threshold": horn["null_threshold"],
        "group_sizes": dict(sorted(sizes.items())),
        "groups": groups,
        # How far each item sits from the centre of its group. Small means the
        # item is what the factor is about; large means it landed there because
        # it had to land somewhere.
        "distance": distance,
    }


def convergence(reports: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Do independent scorers agree on the NUMBER, and on the grouping?

    Two questions rather than one, because they can disagree: models can land on
    the same count while cutting the material completely differently, and that
    would be a coincidence of arithmetic rather than a shared structure.
    """
    from .structure_stats import agreement

    reports = list(reports)
    counts = {r["scorer"]: r["n_factors"] for r in reports}
    pairs = {}
    for i, a in enumerate(reports):
        for b in reports[i + 1:]:
            shared = set(a["groups"]) & set(b["groups"])
            if len(shared) < 2:
                continue
            pairs[f"{a['scorer']} vs {b['scorer']}"] = agreement(
                {k: a["groups"][k] for k in shared}, {k: b["groups"][k] for k in shared})
    return {
        "counts": counts,
        "same_count": len(set(counts.values())) == 1 if counts else None,
        "spread": (max(counts.values()) - min(counts.values())) if counts else None,
        "median": st.median(counts.values()) if counts else None,
        "grouping_agreement": pairs,
    }
