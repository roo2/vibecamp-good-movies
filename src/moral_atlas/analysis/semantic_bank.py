"""Cut the harvest into an item bank by meaning rather than by wording.

WHAT WAS WRONG WITH THE LEXICAL CUT. `bank.cluster_propositions` scores
similarity with TF-IDF over word and character n-grams, which measures shared
vocabulary. Two consequences were measured on the deepseek harvest:

  Over-merge. The largest cluster held 25 propositions including both "the ends
  justify the means when the end is the collective good" and "the ends do not
  justify immoral means" — opposite claims, merged because they share four
  words. `build_bank` then canonicalised the cluster from its REPRESENTATIVE
  alone, never seeing the members, so what reached the bank was a hedge:
  "whether the ends justify the means depends on the justness of the cause."
  It carried the highest support in the bank and almost no power to separate
  films, because nearly every film affirms it.

  Under-merge. "Redemption" survived as seven near-duplicate items, because the
  same claim phrased in different words has little vocabulary in common.

WHY NOT JUST SWAP IN EMBEDDINGS. Because they do not solve the half of the
problem that matters most. Measured on the pairs above, all-MiniLM-L6-v2 scores
the two OPPOSITE claims at 0.59 and puts the same claim reworded at 0.38 — the
wrong way round. Sentence embedders encode what a sentence is ABOUT, not what it
asserts; a static model (potion-base-8M) was worse still at 0.70 versus 0.39.
There is no threshold that fixes this, so nothing here asks an embedder to
decide whether two claims are the same.

THE ARRANGEMENT THAT DOES WORK. Each stage is given the job it is good at:

  1. Embeddings propose TOPICAL neighbourhoods — what these models are reliable
     at, and it is only a recall step, so a generous threshold is correct.
  2. `bank.polarity_class` blocks the neighbourhoods, so a negation and an
     assertion can never land in the same group whatever the geometry says.
  3. A model reads the neighbourhood's MEMBER SENTENCES and returns the distinct
     claims it actually contains — one, or several. This is the step the old
     pipeline had no equivalent of: deciding sameness is a judgement about
     meaning, and it is made by the only component that can read.

So a neighbourhood is a question put to the model, not a decision already taken.
Merging and splitting are the same operation here, which is why an over-merged
cluster and an under-merged pair are both repaired by one pass.

Support is recorded but not used to drop anything: how many films happened to
PHRASE a claim similarly is not evidence about the claim. Whether an item can
separate films is decided after scoring, by `latent.MIN_FILMS_PER_ITEM`, on the
verdicts themselves.
"""
from __future__ import annotations

from typing import Any, Iterable

from pydantic import BaseModel, Field

from .. import db
from . import bank as lexical

# Small, CPU-only, and used solely to propose neighbourhoods — nothing about the
# result depends on it being a strong model, because it never decides sameness.
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Cosine DISTANCE for agglomerative linkage. Deliberately generous: a
# neighbourhood that is too broad costs a few tokens when the model splits it,
# while one that is too narrow hides a duplicate the model never gets to see.
NEIGHBOUR_DISTANCE = 0.45

# How many member sentences the model is shown. Long enough to see the spread of
# a real cluster, short enough that the judgement stays sharp.
MAX_MEMBERS_SHOWN = 18


class Claim(BaseModel):
    text: str = Field(
        description="One canonical moral proposition: a general claim about how to "
                    "live or how the world is morally ordered. No proper nouns, no "
                    "plot specifics. Phrased so a thoughtful person on EITHER side "
                    "would accept it as a fair statement of the question.")
    members: list[int] = Field(
        description="Line numbers from the supplied list that assert THIS claim.")


class ClaimSet(BaseModel):
    claims: list[Claim] = Field(
        description="Every distinct claim present in the group. One if they all "
                    "assert the same thing; several if they do not.")
    discard: list[int] = Field(
        default_factory=list,
        description="Line numbers that are not moral propositions at all — plot "
                    "summary, genre observation, a remark about craft.")


SPLIT_SYSTEM = """\
You are building a fixed measuring instrument out of moral propositions
harvested from films, and your job on each group is to decide how many DISTINCT
claims it contains.

These sentences were grouped because software found them similar. That software
matches subject matter, not meaning, so a group routinely contains claims that
argue with each other. Treat the grouping as a question, never as an answer.

TWO SENTENCES ARE THE SAME CLAIM only when a film could not possibly affirm one
and deny the other. Same topic is not the same claim.

  Same claim, different words — return ONE:
    "A person should be judged by what they do, not where they were born."
    "An individual's worth rests on their actions rather than their social rank."

  Same topic, opposing claims — return TWO, one for each side:
    "The ends justify the means when the end is the collective good."
    "The ends do not justify immoral means."

  Same words, different claims — return TWO:
    "Sacrifice for the greater good is noble."
    "Deception is justified when it serves a greater good."

DO NOT HEDGE. When a group holds both sides of a question, the answer is two
opposed propositions — never one compromise sentence that concedes both. A
proposition beginning "whether X depends on..." is a failure: nearly every film
affirms it, so it measures nothing. Write the claim each side actually makes.

STATE EACH CLAIM POSITIVELY, so that a film can affirm or deny it, and never
build the verdict into the wording. Assign every line to exactly one claim, or
to `discard` if it is not a moral proposition at all.
"""


def embed(texts: list[str]):
    """Unit-normalised sentence vectors. Imported lazily: torch is a heavy import."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(EMBED_MODEL)
    return model.encode(list(texts), normalize_embeddings=True,
                        batch_size=128, show_progress_bar=False)


def neighbourhoods(rows: list[Any], distance: float = NEIGHBOUR_DISTANCE,
                   progress=None) -> list[dict[str, Any]]:
    """Topical groups, blocked so polarity can never be crossed.

    Clustering runs INSIDE each polarity class rather than over everything at
    once. Doing it globally and repairing afterwards is what the lexical
    pipeline attempted, and a repair step cannot recover a distinction the
    geometry has already dissolved.
    """
    import numpy as np
    from sklearn.cluster import AgglomerativeClustering

    texts = [r["text"] for r in rows]
    if progress:
        progress(f"embedding {len(texts)} propositions")
    vectors = embed(texts)

    blocks: dict[str, list[int]] = {}
    for i, text in enumerate(texts):
        blocks.setdefault(lexical.polarity_class(text), []).append(i)

    groups: list[dict[str, Any]] = []
    for polarity, index in sorted(blocks.items()):
        if len(index) == 1:
            groups.append({"polarity": polarity, "members": [rows[index[0]]]})
            continue
        sub = np.asarray([vectors[i] for i in index])
        labels = AgglomerativeClustering(
            n_clusters=None, distance_threshold=distance,
            metric="cosine", linkage="average",
        ).fit_predict(sub)
        by_label: dict[int, list[int]] = {}
        for position, label in enumerate(labels):
            by_label.setdefault(int(label), []).append(index[position])
        for label in sorted(by_label):
            groups.append({"polarity": polarity,
                           "members": [rows[i] for i in by_label[label]]})
        if progress:
            progress(f"  {polarity:<8} {len(index):>5} propositions → {len(by_label)} neighbourhoods")
    return groups


def _listing(members: list[Any]) -> str:
    return "\n".join(f"{n}. {m['text']}" for n, m in enumerate(members[:MAX_MEMBERS_SHOWN], 1))


def distinct_claims(group: dict[str, Any], client) -> list[dict[str, Any]]:
    """Ask the model what claims this neighbourhood actually contains."""
    members = group["members"][:MAX_MEMBERS_SHOWN]
    if len(members) == 1:
        return [{"text": members[0]["text"], "support": 1,
                 "films": {members[0]["film_id"]}, "polarity": group["polarity"]}]

    result = client.parse(
        system=SPLIT_SYSTEM,
        user=f"Group of {len(members)} sentences:\n\n{_listing(members)}",
        output_model=ClaimSet,
        max_tokens=4000,
    )
    out: list[dict[str, Any]] = []
    for claim in result.claims:
        picked = [members[n - 1] for n in claim.members if 1 <= n <= len(members)]
        if not claim.text.strip():
            continue
        out.append({
            "text": claim.text.strip(),
            # Support counts distinct FILMS, not sentences: two propositions
            # from one film are one film's opinion however they are worded.
            "films": {m["film_id"] for m in picked},
            "support": len({m["film_id"] for m in picked}),
            "polarity": group["polarity"],
        })
    return out


def build(rows: list[Any], client, distance: float = NEIGHBOUR_DISTANCE,
          progress=None) -> dict[str, Any]:
    """Harvest -> distinct claims. Returns a report; writes nothing."""
    groups = neighbourhoods(rows, distance, progress=progress)
    singles = [g for g in groups if len(g["members"]) == 1]
    plural = [g for g in groups if len(g["members"]) > 1]
    if progress:
        progress(f"{len(groups)} neighbourhoods ({len(plural)} to adjudicate, "
                 f"{len(singles)} single-member)")

    claims: list[dict[str, Any]] = []
    for g in singles:
        claims.extend(distinct_claims(g, client))

    done = 0
    for g in plural:
        try:
            claims.extend(distinct_claims(g, client))
        except Exception as error:            # a bad group must not lose the run
            if progress:
                progress(f"  group of {len(g['members'])} failed: {error}")
            claims.extend({"text": m["text"], "films": {m["film_id"]},
                           "support": 1, "polarity": g["polarity"]}
                          for m in g["members"])
        done += 1
        if progress and done % 25 == 0:
            progress(f"  adjudicated {done}/{len(plural)} — {len(claims)} claims so far")

    return {
        "n_propositions": len(rows),
        "n_neighbourhoods": len(groups),
        "n_adjudicated": len(plural),
        "n_claims": len(claims),
        "claims": claims,
    }


def write_bank(bank_version: str, claims: list[dict[str, Any]],
               model: str | None, run_id: str) -> dict[str, int]:
    """Persist claims as an item bank, in the shape the rest of the pipeline reads."""
    items = [{"item_id": f"I{n:04d}", "text": c["text"], "cluster_id": n,
              "support": c["support"], "active": True, "note": c.get("polarity", "")}
             for n, c in enumerate(sorted(claims, key=lambda c: -c["support"]), 1)]
    return lexical._write_items(bank_version, items, model, run_id)


def harvest(scorer: str, variant: str) -> list[dict[str, Any]]:
    """The model's own propositions, as plain dicts."""
    return [{"prop_id": r["prop_id"], "film_id": r["film_id"], "text": r["text"],
             "stance": r["stance"]}
            for r in lexical.model_propositions(scorer, variant)]
