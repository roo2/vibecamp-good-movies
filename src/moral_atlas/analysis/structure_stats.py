"""Statistics on whether different models carve the same moral space.

Once every model has sorted the identical 694 items into its own axes, the
comparison stops being a matter of reading two lists of names and deciding they
feel similar. Four questions, each with a number:

DO THEY GROUP THE SAME ITEMS TOGETHER?
    Adjusted Rand Index and Normalised Mutual Information, both label-free: they
    ask only whether two items placed together by one model are placed together
    by the other, never what either called the group. ARI is adjusted so that
    two random partitions of the same shape score ~0 rather than the substantial
    overlap they get for free — with 8 groups over 694 items, raw agreement is
    around 12% before anyone has read anything.

WHICH AXIS IS WHICH?
    `match_axes` pairs A's axes to B's by item overlap using the Hungarian
    algorithm, then reports the Jaccard of each matched pair. An axis both models
    found is a candidate for being a real feature of the corpus; an axis that
    matches nothing is one model's idea. This is the only honest way to say
    "both models found the mercy/vengeance axis", because it is decided by which
    propositions landed there, not by the names being synonyms.

IS EIGHT THE RIGHT NUMBER?
    This is the question nobody can put to an LLM directly: `derive_system` takes
    n_dims, and a model asked for eight axes will always return eight. The
    k-sweep asks it indirectly — derive at k = 4, 6, 8, 10, 12 and measure how
    much independent models agree at each k. If the material really has eight
    joints, agreement should peak near eight; if agreement is flat, then eight
    was a number we supplied and the models were being agreeable.

IS ANY OF IT BETTER THAN CHANCE?
    Every agreement figure is reported beside a permutation null that shuffles
    one model's labels while holding its group sizes fixed. Lopsided partitions
    can manufacture agreement, and holding the sizes fixed prices that in.
"""
from __future__ import annotations

import random
import statistics as st
from collections import defaultdict
from typing import Any, Iterable

# Two partitions of the same items agree this much by construction with 8 groups;
# quoting raw agreement without saying so would flatter every pair of models.
PERMUTATIONS = 500


def _labels(a: dict[str, int], b: dict[str, int]) -> tuple[list[int], list[int], list[str]]:
    shared = sorted(set(a) & set(b))
    return [a[i] for i in shared], [b[i] for i in shared], shared


def agreement(a: dict[str, int], b: dict[str, int], seed: int = 5) -> dict[str, Any]:
    """Label-free agreement between two partitions of the same items."""
    from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

    left, right, shared = _labels(a, b)
    if len(shared) < 2:
        return {"n_items": len(shared), "ari": None, "nmi": None, "raw": None}

    raw = sum(1 for x, y in zip(left, right) if x == y) / len(shared)
    ari = adjusted_rand_score(left, right)
    nmi = normalized_mutual_info_score(left, right)

    rng = random.Random(seed)
    pool = list(right)
    null = []
    for _ in range(PERMUTATIONS):
        rng.shuffle(pool)
        null.append(adjusted_rand_score(left, pool))
    mean, sd = st.mean(null), st.pstdev(null)

    return {
        "n_items": len(shared),
        "raw": round(raw, 3),
        "ari": round(ari, 3),
        "nmi": round(nmi, 3),
        "null_ari_mean": round(mean, 4),
        "z": round((ari - mean) / sd, 1) if sd else None,
        "n_groups": (len(set(left)), len(set(right))),
    }


def match_axes(
    a: dict[str, int], b: dict[str, int],
    names_a: dict[int, str] | None = None, names_b: dict[int, str] | None = None,
) -> list[dict[str, Any]]:
    """Pair A's axes to B's by item overlap, not by name.

    The Hungarian assignment maximises total overlap, so each axis is matched at
    most once — which is what stops a large, vague axis in one model from being
    declared the counterpart of three different axes in the other.
    """
    import numpy as np
    from scipy.optimize import linear_sum_assignment

    shared = set(a) & set(b)
    groups_a: dict[int, set[str]] = defaultdict(set)
    groups_b: dict[int, set[str]] = defaultdict(set)
    for item in shared:
        groups_a[a[item]].add(item)
        groups_b[b[item]].add(item)
    if not groups_a or not groups_b:
        return []

    ids_a, ids_b = sorted(groups_a), sorted(groups_b)
    overlap = np.zeros((len(ids_a), len(ids_b)))
    for i, x in enumerate(ids_a):
        for j, y in enumerate(ids_b):
            overlap[i, j] = len(groups_a[x] & groups_b[y])

    rows, cols = linear_sum_assignment(-overlap)
    out = []
    for i, j in zip(rows, cols):
        x, y = ids_a[i], ids_b[j]
        union = len(groups_a[x] | groups_b[y])
        out.append({
            "a_dim": x, "b_dim": y,
            "a_name": (names_a or {}).get(x, str(x)),
            "b_name": (names_b or {}).get(y, str(y)),
            "shared_items": int(overlap[i, j]),
            "jaccard": round(overlap[i, j] / union, 3) if union else 0.0,
            "a_size": len(groups_a[x]), "b_size": len(groups_b[y]),
        })
    out.sort(key=lambda row: -row["jaccard"])
    return out


def pairwise(parts: dict[str, dict[str, int]]) -> dict[str, dict[str, Any]]:
    aliases = sorted(parts)
    return {
        f"{x} vs {y}": agreement(parts[x], parts[y])
        for i, x in enumerate(aliases) for y in aliases[i + 1:]
    }


def item_stability(parts: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
    """Per item: do the models agree about which OTHER items belong with it?

    Labels cannot be compared across models, but neighbourhoods can. For each
    item and each pair of models, take the Jaccard of the two sets of items
    sharing its axis; average over pairs. An item every model keeps in the same
    company is structure the corpus supplies. An item whose neighbours change
    with the model is the taxonomy straining, and it is worth reading the ones
    at the bottom of this list before trusting any axis they sit on.
    """
    aliases = sorted(parts)
    if len(aliases) < 2:
        return []
    shared = sorted(set.intersection(*(set(parts[a]) for a in aliases)))

    members: dict[str, dict[int, set[str]]] = {}
    for alias in aliases:
        by_dim: dict[int, set[str]] = defaultdict(set)
        for item in shared:
            by_dim[parts[alias][item]].add(item)
        members[alias] = by_dim

    out = []
    for item in shared:
        scores = []
        for i, x in enumerate(aliases):
            for y in aliases[i + 1:]:
                nx = members[x][parts[x][item]]
                ny = members[y][parts[y][item]]
                union = len(nx | ny)
                scores.append(len(nx & ny) / union if union else 0.0)
        out.append({"item_id": item, "stability": round(st.mean(scores), 3),
                    "pairs": len(scores)})
    out.sort(key=lambda row: -row["stability"])
    return out


def k_sweep(
    by_k: dict[int, dict[str, dict[str, int]]],
) -> list[dict[str, Any]]:
    """Mean pairwise cross-model ARI at each k.

    The number this is really after is the shape of the curve, not any single
    value: a peak says the models keep rediscovering the same joints at that
    granularity, and a flat line says the count came from the prompt.
    """
    out = []
    for k, parts in sorted(by_k.items()):
        scores = [row["ari"] for row in pairwise(parts).values() if row["ari"] is not None]
        nulls = [row["null_ari_mean"] for row in pairwise(parts).values()
                 if row.get("null_ari_mean") is not None]
        if not scores:
            continue
        out.append({
            "k": k,
            "models": len(parts),
            "pairs": len(scores),
            "mean_ari": round(st.mean(scores), 3),
            "min_ari": round(min(scores), 3),
            "max_ari": round(max(scores), 3),
            "null": round(st.mean(nulls), 4) if nulls else None,
        })
    return out


def best_k(sweep: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The k where independent models agree most, and whether it stands out.

    `margin` is the gap to the runner-up. A peak that beats its neighbours by a
    hair is not a finding, so the margin is reported rather than hidden behind
    an argmax.
    """
    if not sweep:
        return None
    ranked = sorted(sweep, key=lambda row: -row["mean_ari"])
    top = ranked[0]
    margin = top["mean_ari"] - ranked[1]["mean_ari"] if len(ranked) > 1 else None
    return {"k": top["k"], "mean_ari": top["mean_ari"], "margin": round(margin, 3)
            if margin is not None else None,
            "flat": bool(margin is not None and margin < 0.05)}
