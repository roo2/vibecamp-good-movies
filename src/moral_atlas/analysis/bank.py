"""Cut the raw proposition pool down to an item bank.

Two passes. First a cheap textual clustering that collapses near-duplicates —
forty films will produce "the wicked must be punished" a dozen times over in
slightly different words. Then an optional LLM pass that writes one canonical,
non-loaded sentence per cluster.

The canonicalisation pass is the most consequential and least visible step in the
pipeline: it rewrote the majority of the harvested propositions, so the sentences
every film is scored against are its wording rather than the harvest's. It
therefore opens a run like every other LLM stage, and each item records the model
and prompt version that wrote it.

THE INVERSION PROBLEM. Clustering compares vocabulary, and vocabulary is exactly
where a negation does not live. "Violent response to violent injustice is never
justified" and "...is morally required of the wronged" share every content word,
so they sit almost on top of each other in the space the clustering measures and
merge without complaint. `build_bank` then keeps the LONGEST member as the
cluster's representative — a tie-break that is arbitrary with respect to meaning
— and the bank ends up asserting whichever direction happened to be wordier,
with no trace that the opposite was discarded.

That is not hypothetical. It happened once in b1, on the only two clusters that
merged anything at all, which makes the rate 50% of merges rather than 1 in 694:
Do the Right Thing denied both absolutes, the "morally required" phrasing won by
sixteen characters, and item I001 now says the wronged are obliged to answer with
violence. Note where the fault lies — the canonicaliser was faithful to the
representative it was handed. The inversion happened at clustering.

`split_inverted` separates cluster members by polarity class before any of that,
so opposed statements become two items rather than one. The bank wants both
anyway: a proposition and its inverse are two things a film can take opposite
positions on, and holding both is how a scorer that agrees with whatever it is
shown becomes visible. The reason this is worth doing now, when it has bitten
exactly one item, is that the current threshold of 0.45 almost never merges
anything — the bug is rare by accident rather than by design, and anyone who
lowers the threshold to make deduplication work would meet it at scale.
"""
from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from .. import db
from ..config import PROMPT_VERSION


class CanonicalItem(BaseModel):
    cluster_id: int
    text: str = Field(
        description="One canonical proposition for this cluster. General, no "
                    "proper nouns, phrased so that someone on either side would "
                    "accept it as a fair statement of the question."
    )
    drop: bool = Field(description="True if this cluster is not a moral proposition at all.")
    drop_reason: str = Field(description="Why, if dropped. '' otherwise.")


class CanonicalSet(BaseModel):
    items: list[CanonicalItem]




def _normalise(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text)


def cluster_propositions(threshold: float = 0.45) -> list[dict[str, Any]]:
    """Group raw propositions by textual similarity.

    TF-IDF over word and character n-grams rather than embeddings: for
    near-duplicate detection over short, deliberately generic sentences it is
    about as good, costs nothing, and adds no dependency on an external service.
    """
    import numpy as np
    from sklearn.cluster import AgglomerativeClustering
    from sklearn.feature_extraction.text import TfidfVectorizer

    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT prop_id, film_id, text, stance FROM propositions_raw"
        ).fetchall()
    if not rows:
        return []

    texts = [_normalise(r[2]) for r in rows]
    if len(texts) < 2:
        return [{"cluster_id": 0, "members": rows, "representative": rows[0][2], "support": 1}]

    vec = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True,
                          min_df=1, stop_words="english")
    X = vec.fit_transform(texts)
    # Cosine distance on L2-normalised TF-IDF rows.
    dense = np.asarray((X @ X.T).todense())
    dist = 1.0 - np.clip(dense, 0.0, 1.0)
    np.fill_diagonal(dist, 0.0)

    model = AgglomerativeClustering(
        n_clusters=None, distance_threshold=threshold,
        metric="precomputed", linkage="average",
    )
    labels = model.fit_predict(dist)

    clusters: dict[int, list[Any]] = {}
    for label, row in zip(labels, rows):
        clusters.setdefault(int(label), []).append(row)

    out = []
    for cid, members in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
        # Representative = the longest statement, which is usually the most
        # fully specified phrasing of the shared idea.
        rep = max(members, key=lambda m: len(m[2]))[2]
        out.append({
            "cluster_id": cid,
            "members": members,
            "representative": rep,
            "support": len({m[1] for m in members}),  # distinct films
            "n_statements": len(members),
        })
    return out


# Words that decide what a sentence DOES with its subject matter. TF-IDF cannot
# see them: "violence is never justified" and "violence is morally required"
# share every other token, so they sit almost on top of each other in the space
# the clustering measures, and the merge threshold has nothing left to object to.
NEGATION = {
    "never", "not", "no", "cannot", "cant", "nothing", "neither", "nor",
    "without", "none", "nobody", "isnt", "arent", "doesnt", "dont", "wont",
}
OBLIGATION = {
    "must", "required", "requires", "obliged", "obligatory", "obligation",
    "duty", "ought", "should", "demands", "demanded", "mandatory",
}


def polarity_class(text: str) -> str:
    """What the sentence asserts about its subject: forbids, requires, or neither.

    Negation wins over obligation, because "must not" is a prohibition rather
    than a weaker requirement — collapsing those two would recreate the very
    bug this exists to prevent.
    """
    words = set(_normalise(text).split())
    if words & NEGATION:
        return "negated"
    if words & OBLIGATION:
        return "obliged"
    return "plain"


def split_inverted(clusters: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Separate cluster members that assert opposite things.

    The clustering has already decided these sentences are about the same thing;
    that is exactly what makes a polarity disagreement inside a cluster
    dangerous rather than interesting. `build_bank` keeps the LONGEST member as
    the representative, which is arbitrary with respect to meaning — so when
    "violent response is never justified" and "violent response is morally
    required" land together, the longer one wins by two words and the bank ends
    up asserting the opposite of what the shorter one said, with no trace that
    anything was discarded.

    Splitting by polarity class keeps both directions as separate items, which
    is what the bank wants anyway: a proposition and its inverse are two things
    a film can take opposite positions on, and having both is how a scorer that
    simply agrees with whatever it is shown becomes visible.

    Returns (clusters, splits) where `splits` records what was separated, so the
    caller can say so rather than doing it silently.
    """
    out: list[dict[str, Any]] = []
    splits: list[dict[str, Any]] = []
    next_id = max((c["cluster_id"] for c in clusters), default=-1) + 1

    for cluster in clusters:
        members = cluster["members"]
        if len(members) < 2:
            out.append(cluster)
            continue
        by_class: dict[str, list[Any]] = {}
        for member in members:
            by_class.setdefault(polarity_class(member[2]), []).append(member)
        if len(by_class) < 2:
            out.append(cluster)
            continue

        # Largest group keeps the original id so anything already joined to it
        # still resolves; the rest are new clusters.
        ordered = sorted(by_class.items(), key=lambda kv: -len(kv[1]))
        splits.append({
            "cluster_id": cluster["cluster_id"],
            "classes": {name: [m[2] for m in group] for name, group in ordered},
        })
        for index, (name, group) in enumerate(ordered):
            out.append({
                "cluster_id": cluster["cluster_id"] if index == 0 else next_id,
                "members": group,
                "representative": max(group, key=lambda m: len(m[2]))[2],
                "support": len({m[1] for m in group}),
                "n_statements": len(group),
                "note": f"split from cluster {cluster['cluster_id']} ({name})",
            })
            if index:
                next_id += 1
    return out, splits


def build_bank(
    bank_version: str, clusters: list[dict[str, Any]],
    client=None, min_support: int = 1, batch_size: int = 40, progress=None,
) -> dict[str, Any]:
    """Write an item bank, canonicalising the cluster representatives if a client is given.

    A run is opened whenever a model is involved, so the wording of every item
    is traceable to the model and prompt version that produced it. Without a
    client the items are the harvest's own sentences and the run records that
    too — "no model touched this" is a provenance answer, not a missing one.
    """
    clusters, splits = split_inverted(clusters)
    if splits and progress:
        for split in splits:
            progress(f"[yellow]split cluster {split['cluster_id']}[/] — members asserted "
                     f"opposite things: {', '.join(split['classes'])}")
    kept = [c for c in clusters if c["support"] >= min_support]
    canonical: dict[int, str] = {c["cluster_id"]: c["representative"] for c in kept}
    dropped: dict[int, str] = {}
    model = getattr(client, "model", None)
    run_id = db.start_run(
        "bank", model, PROMPT_VERSION,
        {"bank_version": bank_version, "n_clusters": len(clusters),
         "min_support": min_support, "canonicalised": client is not None},
    )

    if client is not None:
        from ..llm import prompts  # noqa: F401  (keeps prompt versioning in one place)

        system = (
            "You are tidying a bank of moral propositions harvested from films, "
            "so that it can be used as a fixed measuring instrument.\n\n"
            "For each numbered cluster you are given one representative sentence. "
            "Rewrite it as a single canonical proposition:\n"
            "  - a general claim about how to live or how the world is morally "
            "ordered, with no proper nouns and no plot specifics;\n"
            "  - phrased so that a thoughtful person on EITHER side would accept "
            "it as a fair statement of the question. Never build the verdict into "
            "the wording;\n"
            "  - stated positively, so that a film can affirm or deny it.\n\n"
            "Set drop=true only when the cluster is not a moral proposition at all "
            "— a plot summary, a genre observation, a statement about craft."
        )
        for i in range(0, len(kept), batch_size):
            batch = kept[i:i + batch_size]
            listing = "\n".join(
                f"{c['cluster_id']}. {c['representative']}  "
                f"(seen in {c['support']} films)" for c in batch
            )
            res = client.parse(
                system=system,
                user=f"Clusters:\n\n{listing}",
                output_model=CanonicalSet,
                max_tokens=8000,
            )
            for item in res.items:
                if item.drop:
                    dropped[item.cluster_id] = item.drop_reason
                else:
                    canonical[item.cluster_id] = item.text.strip()
            if progress:
                progress(f"canonicalise  clusters {i}-{i + len(batch) - 1}")

    items: list[dict[str, Any]] = []
    for c in kept:
        cid = c["cluster_id"]
        if cid in dropped:
            continue
        items.append({
            "item_id": f"I{len(items) + 1:03d}",
            "text": canonical[cid],
            "cluster_id": cid,
            "support": c["support"],
            "active": True,
            "note": c.get("note", ""),
        })

    _write_items(bank_version, items, model, run_id)
    db.finish_run(run_id, getattr(client, "usage", None) and client.usage.as_dict() or {})

    return {
        "bank_version": bank_version,
        "prompt_version": PROMPT_VERSION,
        "model": model,
        "run_id": run_id,
        "n_clusters": len(clusters),
        "n_items": len(items),
        "n_dropped": len(dropped),
        "n_inversions_split": len(splits),
        "inversions": splits,
        "dropped": dropped,
    }


def _write_items(bank_version: str, items: list[dict[str, Any]],
                 model: str | None = None, run_id: str | None = None) -> None:
    with db.connect() as con:
        con.execute("DELETE FROM item_bank WHERE bank_version=?", [bank_version])
        for it in items:
            con.execute(
                "INSERT INTO item_bank (item_id, bank_version, text, cluster_id, "
                "support, active, note, model, prompt_version, run_id, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [it["item_id"], bank_version, it["text"], it["cluster_id"],
                 it["support"], it["active"], it["note"], model, PROMPT_VERSION,
                 run_id, db.now()],
            )



def export_bank(bank_version: str, path: str) -> int:
    """Write the bank to a reviewable text file.

    This is the ~90 minutes of manual work the plan asks for: read the sentences,
    delete the incoherent, merge the redundant. Set active=false in the file and
    re-import to apply.
    """
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT item_id, text, support, active, note, model FROM item_bank "
            "WHERE bank_version=? ORDER BY support DESC, item_id",
            [bank_version],
        ).fetchall()

    lines = [
        f"# Item bank {bank_version} — {len(rows)} propositions",
        "# Set active: false to retire an item, then: atlas bank-import <file>",
        "",
    ]
    for item_id, text, support, active, note, model in rows:
        lines.append(json.dumps({
            "item_id": item_id, "text": text, "support": support,
            "active": bool(active), "note": note, "written_by": model,
        }))
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return len(rows)


def import_bank(bank_version: str, path: str) -> int:
    n = 0
    with open(path) as fh, db.connect() as con:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            rec = json.loads(line)
            con.execute(
                "UPDATE item_bank SET text=?, active=?, note=? "
                "WHERE bank_version=? AND item_id=?",
                [rec["text"], rec.get("active", True), rec.get("note", ""),
                 bank_version, rec["item_id"]],
            )
            n += 1
    return n
