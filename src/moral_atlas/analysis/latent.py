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

    At 422 films every pair shares at least one film, the mean overlap is 89 and
    the median 74. Normalising the dense reading does not substitute for this:
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
more respondents than variables. With 422 films and 297 items that is no longer
inverted, but the correlation matrix still has rank at most the number of films,
so the recoverable ceiling is reported alongside the count. What would carry
most weight is agreement between models: if scorers that harvested different
propositions keep landing on the same k, that is evidence the corpus has that
many joints. They do not currently — one finds twenty and another finds none —
and that disagreement is itself the finding.
"""
from __future__ import annotations

import statistics as st
from typing import Any, Iterable

from .. import db
from ..llm.schemas import MAX_STRENGTH

# An item scored on one film contributes a spike rather than a covariance, and
# 224 of them would dominate the eigenvalues with noise.
MIN_FILMS_PER_ITEM = 3

# The smallest share of engaged films that must sit on the MINORITY side of a
# proposition for it to count as a measurement rather than a consensus.
#
# A proposition every film affirms cannot separate films, so it can carry no
# moral dimension. That much is obvious. What is not obvious, and is why this
# has to be enforced rather than left to the arithmetic, is that such an item is
# worse than useless here: film-centring subtracts each film's own affirm rate,
# so a unanimously-affirmed item's centred value becomes `constant - film_mean`
# — a negated copy of how agreeable the film is. Measured on this corpus those
# items correlate -1.00 with the film's affirm rate, and they carried a mean
# absolute loading of 1.00 against 0.34 for everything else. The correction for
# acquiescence was manufacturing an acquiescence factor out of them.
#
# The bank is far more unanimous than it looks: the median proposition has 98%
# of engaged films on one side, and 60 of 296 have no disagreement whatsoever.
#
# 5% chosen by measurement, not taste. Sweeping the threshold, the leading
# factor's correlation with how much a film engages runs -0.62 (no filter),
# -0.63, +0.61, -0.42, and then +0.08 here — and split-half replication IMPROVES
# as items are removed, 0.58 -> 0.64 at k=1 and 0.28 -> 0.32 at k=3. Dropping
# three quarters of the bank makes the remainder both cleaner and more
# reproducible, which is the sign the discarded items were never carrying signal.
MIN_DISAGREEMENT = 0.05


def response_matrix(
    scorer: str | None = None, bank_version: str = "b1",
    min_films: int = MIN_FILMS_PER_ITEM, variant: str | None = None,
    min_disagreement: float = MIN_DISAGREEMENT,
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
    def contested(item: str) -> bool:
        """Do enough films take opposite sides of this to make it a measurement?"""
        values = [sum(v) / len(v) for (f, i), v in cells.items() if i == item]
        if len(values) < min_films:
            return False
        positive = sum(1 for v in values if v > 0) / len(values)
        return min(positive, 1 - positive) >= min_disagreement

    seen = sorted(i for i, fs in engaged.items() if len(fs) >= min_films)
    items = [i for i in seen if contested(i)] if min_disagreement > 0 else seen
    dropped = len(engaged) - len(items)
    unanimous = len(seen) - len(items)
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
                # Verdicts are stored graded (-2..2 for strongly denies..strongly
                # affirms) and normalised here, so everything downstream keeps
                # working on the -1..1 it was written for.
                matrix[row_index, index[item]] = sum(values) / len(values) / MAX_STRENGTH

    return {"films": films, "items": items, "matrix": matrix, "variant": variant,
            "dropped_items": dropped, "unanimous_items": unanimous,
            "density": float((matrix != 0).mean())}


# Below this a pair's correlation is computed from too few films to mean
# anything, and one wild value would enter the matrix as a strong association.
MIN_PAIR_OVERLAP = 8


def _pairwise_correlation(matrix) -> Any:
    """Correlate items over the films that took a position on BOTH of them.

    The strict reading of the question, and the one the module docstring records
    as unanswerable — at 40 films, 82% of item pairs shared no film at all and
    the mean overlap was 0.21. That is no longer true: at 422 films every pair
    shares at least one, the mean overlap is 89 and the median 74, and only 5%
    fall under MIN_PAIR_OVERLAP — so the estimator this corpus could not support
    is now the estimator it can.

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


# ---------------------------------------------------------------------------
# COMMON FACTORS, the default. The block above computes principal components:
# the correlation matrix keeps 1.0 on its diagonal, so every proposition's
# unique and error variance is inside the solution. Factor analysis replaces
# that diagonal with communalities and models only what the propositions SHARE,
# which is the literal form of this project's question — that latent moral
# dimensions cause films to answer propositions together.
#
# It was adopted on measurement grounds, and the deciding evidence was that the
# one thing components did better turned out not to be about morality. On 4,000
# held-out MovieLens users components ordered a liked film above a disliked one
# 57.6% of the time against the common factors' 56.4% — five standard errors
# apart. With taste residualised out of both, the gap fell to 0.21 +/- 0.25 and
# both sat within a point of chance. Four fifths of the advantage was taste: the
# marginal variance components keep and factors discard is largely what KIND of
# film something is.
#
# What the factors do better: their own propositions agree far more (0.89 and
# 0.63 on the first two axes, against 0.66 and 0.40), they separate the
# reference lists slightly better on one dimension fewer, and their third axis
# puts the devotional canon and the sigma canon at the same end — both affirming
# an order that precedes individual choice — which the components' extra
# dimension dissolves.


def _communalities(r) -> Any:
    """Starting communalities: squared multiple correlations, or the row's max.

    SMC needs an invertible matrix. This one is estimated pairwise on different
    subsets of films and can be singular, so the fallback is load-bearing rather
    than decorative.
    """
    import numpy as np

    try:
        inverse = np.linalg.pinv(r)
        smc = 1.0 - 1.0 / np.diag(inverse)
        if np.all(np.isfinite(smc)):
            return np.clip(smc, 0.05, 0.95)
    except np.linalg.LinAlgError:
        pass
    off = r - np.diag(np.diag(r))
    return np.clip(np.abs(off).max(axis=1), 0.05, 0.95)


def _common_eigenvalues(matrix) -> Any:
    """The FA analogue of `_agreement_eigenvalues`: the REDUCED matrix.

    Same estimator, same centring, same exclusion of silence. Only the diagonal
    differs, which is the whole difference between the two methods.
    """
    import numpy as np

    r = _pairwise_correlation(_film_centred(matrix))
    reduced = r.copy()
    np.fill_diagonal(reduced, _communalities(r))
    return np.sort(np.linalg.eigvalsh(reduced))[::-1]


def _principal_axis(r, k: int, iters: int = 60, tol: float = 1e-5):
    """Principal axis factoring, iterated to stable communalities.

    Not maximum likelihood: ML requires a positive semi-definite matrix and this
    one is not, by construction — `_pairwise_correlation` records why.
    """
    import numpy as np

    h2 = _communalities(r)
    loadings = None
    for _ in range(iters):
        reduced = r.copy()
        np.fill_diagonal(reduced, h2)
        values, vectors = np.linalg.eigh(reduced)
        order = np.argsort(values)[::-1][:k]
        loadings = vectors[:, order] * np.sqrt(np.clip(values[order], 0, None))
        updated = np.clip((loadings ** 2).sum(axis=1), 0.0, 0.998)
        done = np.max(np.abs(updated - h2)) < tol
        h2 = updated
        if done:
            break
    return loadings, h2


def _varimax(loadings, iters: int = 100, tol: float = 1e-6):
    """Orthogonal rotation.

    Needed here in a way it is not on the component side. That path clusters
    loading MAGNITUDES, and rotation preserves the distances k-means reads, so
    it is inert there. Factor analysis assigns each item to the factor it loads
    highest on, and that reading is not rotation-invariant.
    """
    import numpy as np

    p, k = loadings.shape
    if k < 2:
        return loadings
    rotation = np.eye(k)
    last = 0.0
    for _ in range(iters):
        z = loadings @ rotation
        u, sv, vt = np.linalg.svd(
            loadings.T @ (z ** 3 - z @ np.diag((z ** 2).sum(axis=0)) / p))
        rotation = u @ vt
        if sv.sum() < last * (1 + tol):
            break
        last = sv.sum()
    return loadings @ rotation


def common_factor_groups(matrix, items: list[str], k: int, seed: int = 11):
    """The FA counterpart of `item_groups`, returning the same five things.

    Simpler than the component path in one respect that has caused real bugs
    there: a factor IS a group here, so there is no k-means label to confuse
    with an eigenvector index and `dominant` is the identity.
    """
    import numpy as np

    if k < 1:
        return {}, {}, {}, {}, {}

    r = _pairwise_correlation(_film_centred(matrix))
    loadings, _h2 = _principal_axis(r, k)
    loadings = _varimax(loadings)
    home = np.argmax(np.abs(loadings), axis=1)

    # Orient each factor so the majority of its own items load positive, which
    # is the convention the component path uses and the direction the namer is
    # shown. A factor's sign is arbitrary and this project has shipped three
    # separate screens that were silently inverted by forgetting it.
    for j in range(k):
        mine = np.where(home == j)[0]
        if len(mine) and float(np.sign(loadings[mine, j]).sum()) < 0:
            loadings[:, j] = -loadings[:, j]

    strongest = np.abs(loadings[np.arange(len(items)), home])
    ceiling = strongest.max() or 1.0
    return (
        {items[i]: int(home[i]) for i in range(len(items))},
        # Distance from the factor, in the same sense the component path means
        # it: 0 is the item the axis is about, 1 is an item that had to go
        # somewhere.
        {items[i]: float(1.0 - strongest[i] / ceiling) for i in range(len(items))},
        {items[i]: float(loadings[i, home[i]]) for i in range(len(items))},
        {j: j for j in range(k)},
        {items[i]: [float(x) for x in loadings[i]] for i in range(len(items))},
    )


def parallel_analysis(
    matrix, n_iter: int = 200, percentile: float = 95.0, seed: int = 11,
    margin_floor: float = 0.05, method: str = "fa",
) -> dict[str, Any]:
    """Horn's test: how many factors beat the structure the margins give free?

    The null permutes each item's column independently. Shuffling the whole
    matrix instead would also destroy each item's engagement rate, and then a
    factor could clear the bar simply by some items being scored more often than
    others — which is not a moral dimension, it is a salience artefact.
    """
    import numpy as np

    spectrum = _common_eigenvalues if method == "fa" else _agreement_eigenvalues
    observed = spectrum(matrix)
    rng = np.random.default_rng(seed)
    null = np.empty((n_iter, len(observed)))
    for i in range(n_iter):
        shuffled = matrix.copy()
        for column in range(shuffled.shape[1]):
            rng.shuffle(shuffled[:, column])
        null[i] = spectrum(shuffled)

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


def split_half_overlap(matrix, k: int = 5, reps: int = 12, seed: int = 7) -> dict[str, Any]:
    """Do the same factors come back from two random halves of the FILMS?

    The question the factor count cannot answer. Parallel analysis says how many
    factors beat chance in the data you have; it says nothing about whether the
    same factors would appear in another sample of films. An instrument that
    passes the null and fails this one is measuring this corpus rather than
    measuring films.

    Reported as SUBSPACE overlap, not as agreement factor by factor. Individual
    factors are not separately identified when their eigenvalues are close — the
    solution is free to rotate within the tied block — so matching factor 3 of
    one half against factor 3 of the other punishes a stable structure for an
    arbitrary choice of basis. The mean squared canonical correlation between
    the two k-dimensional spaces has no such problem: it asks whether the halves
    describe the same variation, however each chose to name its axes.

    1.0 is identical, and `chance` (k / number of items) is what two unrelated
    samples score. Read the gap between them, not the raw figure.

    A caution that belongs with every number this returns: each half has half
    the films, and the pairwise estimator degrades as films are removed — at 211
    films 11.4% of item pairs fall under MIN_PAIR_OVERLAP against 4.9% at 422.
    So this is a lower bound on the stability of the full corpus, and it is
    most useful watched over time as films are added rather than read once.
    """
    import numpy as np

    rng = np.random.default_rng(seed)
    n_items = matrix.shape[1]
    k = min(k, n_items)

    def basis(sub):
        corr = _pairwise_correlation(_film_centred(sub))
        values, vectors = np.linalg.eigh(corr)
        return vectors[:, np.argsort(values)[::-1][:k]]

    scores = []
    for _ in range(reps):
        order = rng.permutation(matrix.shape[0])
        half = len(order) // 2
        a, b = basis(matrix[order[:half]]), basis(matrix[order[half:]])
        singular = np.linalg.svd(a.T @ b, compute_uv=False)
        scores.append(float((singular ** 2).sum() / k))

    return {
        "k": k, "reps": reps, "films": int(matrix.shape[0]), "items": int(n_items),
        "overlap": float(np.mean(scores)),
        "spread": float(np.std(scores)),
        "chance": k / n_items,
    }


def item_groups(matrix, items: list[str], k: int,
                seed: int = 11) -> tuple[dict[str, int], dict[str, float],
                                         dict[str, float], dict[int, int],
                                         dict[str, list[float]]]:
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
        return {}, {}, {}, {}, {}
    if k < 2:
        return ({item: 0 for item in items}, {item: 0.0 for item in items},
                {item: 1.0 for item in items}, {0: 0},
                {item: [1.0] for item in items})
    # Cluster the LOADINGS of the agreement matrix — eigenvectors scaled by the
    # square root of their eigenvalues — so membership is decided by the same
    # reading of the data that decided the count.
    #
    # The scaling is the part worth stating. Raw eigenvectors are unit vectors,
    # so clustering them treats a factor explaining 30% of the variance and one
    # explaining 4% as equally important in deciding where an item belongs. The
    # square root of the eigenvalue is the standard weighting and measurably
    # tightens the groups: mean within-group similarity of the proposition text
    # rises from 1.97x the between-group level to 2.05x.
    #
    # NOT rotated, and that is not an oversight. Varimax and its relatives are
    # ORTHOGONAL, so they preserve the distances between item loading profiles,
    # and k-means depends on nothing else — rotating first leaves every group
    # identical to the last item. Measured on this corpus: the largest change in
    # any pairwise distance was 2e-15. Rotation earns its keep in the tradition
    # that assigns each item to its single highest loading, which is a different
    # rule from this one; tried that way here it made the groups markedly worse
    # (1.56x, with one group swelling to 90 of 298 propositions) because so many
    # propositions load diffusely across several factors.
    correlation = _pairwise_correlation(_film_centred(matrix))
    values, vectors = np.linalg.eigh(correlation)
    order = np.argsort(values)[::-1][:k]
    loadings = vectors[:, order] * np.sqrt(np.clip(values[order], 0, None))
    # CLUSTER ON THE MAGNITUDES, NOT THE SIGNS. An axis has two ends, and a
    # proposition at one end loads +0.8 where its opposite loads -0.8. In the
    # space k-means measures, those are as far apart as two points can be — so
    # clustering the signed loadings files the two ends of one axis as two
    # different things. Measured here, it did exactly that: two of the three
    # groups were both drawn from factor 1, each with 100% of its propositions
    # pointing the same way. They were the poles of a single axis, torn apart
    # and presented as separate axes.
    #
    # Which produced every symptom a reader reported at once: an axis whose
    # "other end was not observed" (it was — in the other cluster), names that
    # read as half an axis with the rest invented, and films with opposite
    # moral messages sitting together because a one-ended group measures only
    # how much a film affirms that end.
    #
    # On magnitudes the groups come back 58-68% one-sign, which is what a real
    # bipolar axis looks like, and the SIGN then separates the poles inside the
    # group — which is what the sign is for and what reverse-keying expects.
    #
    # The note above about rotation being inert is still true and was still the
    # wrong thing to conclude from: distance between signed profiles is exactly
    # what destroys the relationship between an axis's two ends.
    magnitudes = np.abs(loadings)
    model = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(magnitudes)
    labels = model.labels_
    distances = np.linalg.norm(magnitudes - model.cluster_centers_[labels], axis=1)

    # Each item's signed loading on the factor it was assigned to.
    #
    # This is the number that says which way a proposition points and how much
    # it counts, and its absence was a real fault. A factor's items do not all
    # run the same way: 85 of 298 here load against their own group's majority,
    # because "selfishness is necessary for survival" and "altruism is superior"
    # belong to one axis while pointing in opposite directions. DENYING the
    # first asserts what AFFIRMING the second asserts.
    #
    # Each factor is oriented so its majority is positive, which keeps the
    # direction the naming step was shown. An item with a negative loading is
    # reverse-keyed: a film that denies it is taking the factor's high position.
    # WHICH COLUMN. A k-means label is an arbitrary integer — the clusterer
    # numbers groups by where its initialisation happened to land, not by any
    # correspondence to an eigenvector. This used to read
    # `loadings[members, factor]`, taking cluster 3's loading on eigenvector 3
    # as though the two were the same object. Measured on this corpus, NONE of
    # the twenty clusters had a label matching the eigenvector its members
    # actually load on, and the column being read carried a median of 20% of
    # the group's signal — for one group, 0.1%.
    #
    # That mattered twice over. The sign decides which propositions are
    # reverse-keyed, and reverse-keying is what `user_scores.factor_stances`
    # uses to flip a verdict before scoring a person. And the eigenvalue
    # attached to each named axis is what the product orders "the strongest
    # six" by. So a group was being described, oriented and ranked by a factor
    # that was not its own.
    #
    # Each group is matched to the factor its members genuinely load on. Two
    # groups may choose the same one; that is a real answer — they are facets
    # of one factor — and better than a unique-but-arbitrary assignment.
    # ONE GROUP, ONE FACTOR. Taking each group's argmax independently lets two
    # groups claim the same factor, and then whatever reads them as axes has to
    # treat one of them as a facet of the other and drop it. That went wrong the
    # first time it mattered: three groups, three real factors, and two of them
    # both pointed at the first — so "utilitarian calculus vs moral absolutes"
    # was discarded as a restatement of "redemption and hope vs cynical
    # realism", which it plainly is not.
    #
    # There are exactly as many groups as factors, so a one-to-one assignment
    # always exists. Claims are settled strongest-first: the group with the most
    # to lose gets its preference, and a group whose first choice is taken falls
    # to the strongest factor still free.
    #
    # HOW STRONGLY A GROUP CLAIMS A FACTOR IS A MAGNITUDE QUESTION, and this
    # measured `abs(mean(signed))` — the size of the group's average loading,
    # which is not the same thing as its average size. On a BIPOLAR group the
    # difference is total: half the members load +0.6 and half -0.6, the mean
    # is ~0, and the group makes almost no claim to the factor it is made of.
    # It then wins some other factor by default, and every group shifts.
    #
    # Which is the same defect the note above describes, surviving the fix for
    # it, because clustering on magnitudes is what MADE the groups bipolar.
    # Measured here: 26 of 90 propositions sat on the factor they actually load
    # most on, mean loading 0.19 against a ceiling of 0.45; the axis named from
    # the strongest 23-item group was really the weakest factor, and the
    # proposition loading 0.83 — the largest in the solution — was filed under
    # a factor where it loads 0.17 and dropped below the threshold to be read
    # at all. `mean(abs(signed))` puts 76 of 90 right, at mean loading 0.43.
    members_of = {factor: [i for i, label in enumerate(labels) if label == factor]
                  for factor in range(k)}
    claims = sorted(
        ((float(np.abs(loadings[m]).mean(axis=0)[f]), g, f)
         for g, m in members_of.items() if m for f in range(k)),
        reverse=True)
    dominant: dict[int, int] = {}
    taken: set[int] = set()
    for _strength, group, factor in claims:
        if group in dominant or factor in taken:
            continue
        dominant[group] = factor
        taken.add(factor)

    # Each factor is oriented so its majority is positive, and that orientation
    # has to reach EVERYTHING that reads a direction off it — not just the
    # column below. Written once and applied twice, because storing the oriented
    # value in one place and the raw value in another put 65 of 87 propositions
    # on this reading at opposite signs depending on which was read, and every
    # film's position on two of the three axes came out inverted.
    #
    # `group` and `factor` are different things and this loop reads both. A
    # k-means label indexes `members_of` and `orientation`; the eigenvector it
    # loads on indexes `loadings`. Naming the loop variable `factor` while it
    # iterated GROUPS is how the two were confused in the first place, twice,
    # so they are named apart here and everywhere below.
    signed: dict[str, float] = {}
    orientation: dict[int, float] = {}
    for group in range(k):
        members = members_of.get(group) or []
        if not members:
            continue
        column = loadings[members, dominant[group]]
        flip = -1.0 if float(np.sign(column).sum()) < 0 else 1.0
        orientation[group] = flip
        for position, value in zip(members, column * flip):
            signed[items[position]] = float(value)

    # Every factor's loading per item, ordered to match `dominant`'s factor
    # indices. Scoring a film on an axis by averaging only the propositions
    # filed under it throws away the rest, and the rest is 22% of the loading
    # mass here — a proposition that speaks to two axes should count on both,
    # in proportion to how much it speaks to each.
    # Permuted into GROUP order, so index g is the loading on the axis whose
    # factor_id is g. The raw columns are eigen-factors and the labels are
    # k-means groups, and `dominant` is the mapping between them — indexing one
    # by the other reads a real number off the wrong axis, which is the same
    # class of mistake as the label-as-factor-index bug this replaced.
    all_loadings = {
        items[i]: [float(loadings[i, dominant[g]] * orientation.get(g, 1.0))
                   if g in dominant else 0.0
                   for g in range(k)]
        for i in range(len(items))
    }

    return ({item: int(label) for item, label in zip(items, labels)},
            {item: float(distance) for item, distance in zip(items, distances)},
            signed, dominant, all_loadings)


def analyse(
    scorer: str | None = None, bank_version: str = "b1",
    n_iter: int = 200, min_films: int = MIN_FILMS_PER_ITEM, seed: int = 11,
    variant: str | None = None, method: str | None = None,
) -> dict[str, Any]:
    """The whole thing for one scorer: how many dimensions, and which items.

    `method` is "fa" (common factors, the default) or "pca" (components, what
    this project shipped until 2026-09). ONE solution is ever stored: the
    alternative exists so the comparison can be re-run, not so two readings can
    be served side by side. Three separate screens have already been silently
    wrong from two places computing the same quantity from different solves.
    """
    from ..config import settings

    method = method or settings().extraction
    data = response_matrix(scorer, bank_version, min_films, variant)
    horn = parallel_analysis(data["matrix"], n_iter=n_iter, seed=seed, method=method)
    cut = common_factor_groups if method == "fa" else item_groups
    groups, distance, loading, dominant, all_loadings = cut(
        data["matrix"], data["items"], horn["n_clear_factors"], seed=seed)
    sizes: dict[int, int] = {}
    for label in groups.values():
        sizes[label] = sizes.get(label, 0) + 1
    return {
        "scorer": scorer or "opus",
        "variant": variant,
        "method": method,
        "films": len(data["films"]),
        "items": len(data["items"]),
        "dropped_items": data["dropped_items"],
        # Of those, the ones removed for having no disagreement rather than too
        # few films. A different fact about the bank and worth saying separately.
        "unanimous_items": data.get("unanimous_items", 0),
        # Whether the structure survives a change of sample, which the null test
        # cannot ask. Reported for the first three factors because that is where
        # it stops being informative: below that the answer is always "no".
        "replication": [split_half_overlap(data["matrix"], k=k, reps=12)
                        for k in (1, 2, 3)],
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
        # Signed loading: direction and weight. Negative means reverse-keyed —
        # denying it is what the factor's high pole asserts.
        "loading": loading,
        # Which eigenvector each k-means group actually loads on. Not the
        # group's own label — see the note in `item_groups`.
        "dominant": dominant,
        # {item: [loading on every factor]}, so a film can be scored on an axis
        # using every proposition that speaks to it rather than only those filed
        # under it.
        "loadings": all_loadings,
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
