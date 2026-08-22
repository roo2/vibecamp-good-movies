"""Cut the raw proposition pool down to an item bank.

Two passes. First a cheap textual clustering that collapses near-duplicates —
forty films will produce "the wicked must be punished" a dozen times over in
slightly different words. Then an optional LLM pass that writes one canonical,
non-loaded sentence per cluster and flags reversed pairs.

Reversed pairs earn their keep: no film can sincerely affirm both "becoming
yourself means accepting a role you did not choose" and "becoming yourself means
refusing a role that was chosen for you". Any scorer that affirms both is
agreeing with whatever it is shown, and that is measurable rather than
suspected.
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


class ReversalPair(BaseModel):
    item_a: str
    item_b: str
    note: str


class ReversalSet(BaseModel):
    pairs: list[ReversalPair]


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


def build_bank(
    bank_version: str, clusters: list[dict[str, Any]],
    client=None, min_support: int = 1, batch_size: int = 40, progress=None,
) -> dict[str, Any]:
    """Write an item bank. With a client, canonicalise and detect reversals."""
    kept = [c for c in clusters if c["support"] >= min_support]
    canonical: dict[int, str] = {c["cluster_id"]: c["representative"] for c in kept}
    dropped: dict[int, str] = {}

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
            "reversed_of": None,
            "active": True,
            "note": "",
        })

    # Write the bank BEFORE the reversal pass. Canonicalisation is the expensive
    # part — dozens of LLM calls — and reversal detection is a cheap nice-to-have
    # on top. Doing the risky thing first and persisting afterwards meant one
    # failed call discarded everything that had already been paid for.
    _write_items(bank_version, items)

    reversals: list[ReversalPair] = []
    reversal_error: str | None = None
    if client is not None and len(items) > 1:
        try:
            reversals = detect_reversals(items, client, batch_size=120,
                                         progress=progress)
            index = {it["item_id"]: it for it in items}
            for pair in reversals:
                if pair.item_a in index and pair.item_b in index:
                    index[pair.item_b]["reversed_of"] = pair.item_a
                    index[pair.item_b]["note"] = pair.note
            _write_items(bank_version, items)
        except Exception as e:  # noqa: BLE001
            # The bank is already saved and usable; reversed pairs are an
            # acquiescence check, not a prerequisite for scoring.
            reversal_error = str(e)
            if progress:
                progress(f"[yellow]reversal detection failed, bank kept:[/] {e}")

    return {
        "reversal_error": reversal_error,
        "bank_version": bank_version,
        "prompt_version": PROMPT_VERSION,
        "n_clusters": len(clusters),
        "n_items": len(items),
        "n_dropped": len(dropped),
        "n_reversed_pairs": len(reversals),
        "dropped": dropped,
    }


def _write_items(bank_version: str, items: list[dict[str, Any]]) -> None:
    with db.connect() as con:
        con.execute("DELETE FROM item_bank WHERE bank_version=?", [bank_version])
        for it in items:
            con.execute(
                "INSERT INTO item_bank (item_id, bank_version, text, cluster_id, "
                "support, reversed_of, active, note) VALUES (?,?,?,?,?,?,?,?)",
                [it["item_id"], bank_version, it["text"], it["cluster_id"],
                 it["support"], it["reversed_of"], it["active"], it["note"]],
            )


def detect_reversals(
    items: list[dict[str, Any]], client, batch_size: int = 120, progress=None,
) -> list[ReversalPair]:
    """Find near-inverted pairs in the bank.

    The whole bank goes in the system block on every call so cross-batch pairs
    are still visible, while the user turn names only the slice to report on.
    That keeps the OUTPUT bounded — which is what actually ran out last time —
    without giving up the global view an inversion check needs.
    """
    listing = "\n".join(f"{it['item_id']}. {it['text']}" for it in items)
    system = (
        "You are auditing a bank of moral propositions for REVERSED PAIRS: two "
        "items that are near-inversions of each other, such that no single work "
        "could sincerely affirm both.\n\n"
        "These pairs are valuable — they are kept deliberately, as a check on "
        "whether a scorer is reading the work or simply agreeing with whatever it "
        "is shown. Report nothing that is merely related or adjacent; only true "
        "inversions.\n\n"
        f"THE COMPLETE BANK\n\n{listing}"
    )

    found: list[ReversalPair] = []
    seen: set[tuple[str, str]] = set()
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        ids = ", ".join(it["item_id"] for it in batch)
        res = client.parse(
            system=system,
            user=(f"Report reversed pairs where at least one member is in this "
                  f"slice: {ids}\n\nThe other member may be anywhere in the bank."),
            output_model=ReversalSet,
            max_tokens=16000,
        )
        for pair in res.pairs:
            key = tuple(sorted((pair.item_a, pair.item_b)))
            if key not in seen:
                seen.add(key)
                found.append(pair)
        if progress:
            progress(f"reversals     items {i}-{i + len(batch) - 1}: "
                     f"{len(found)} pairs so far")
    return found


def export_bank(bank_version: str, path: str) -> int:
    """Write the bank to a reviewable text file.

    This is the ~90 minutes of manual work the plan asks for: read the sentences,
    delete the incoherent, merge the redundant. Set active=false in the file and
    re-import to apply.
    """
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT item_id, text, support, reversed_of, active, note FROM item_bank "
            "WHERE bank_version=? ORDER BY support DESC, item_id",
            [bank_version],
        ).fetchall()

    lines = [
        f"# Item bank {bank_version} — {len(rows)} propositions",
        "# Set active: false to retire an item, then: atlas bank-import <file>",
        "",
    ]
    for item_id, text, support, rev, active, note in rows:
        lines.append(json.dumps({
            "item_id": item_id, "text": text, "support": support,
            "reversed_of": rev, "active": bool(active), "note": note,
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
