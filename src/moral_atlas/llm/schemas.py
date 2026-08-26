"""Structured output shapes.

Kept to plain types — str, bool, float, Literal, list[str] — because these are
enforced by the API's structured-output layer, and exotic schema features are
where silent validation failures come from.

Every stage demands verbatim evidence. That is not decoration: an assertion the
model cannot quote from the packet is one it recalled from training rather than
read, and for the source A/B a recalled answer is a contaminated answer.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AntagonistFate = Literal[
    "destroyed", "punished_but_alive", "reconciled", "escapes",
    "becomes_protagonist", "no_clear_antagonist", "unknown",
]
TonalRegister = Literal[
    "sincere", "ironic", "satirical", "ambivalent", "comic", "tragic", "unknown",
]


class MoralSkeleton(BaseModel):
    """The topic-stripped substrate every later stage reads.

    Deliberately says nothing about dragons, spaceships or period setting — the
    point is to carry moral structure forward while leaving genre behind, so
    that topic cannot leak into the factor analysis downstream.
    """

    legitimacy_source: str = Field(
        description="What the film treats as the source of legitimate authority "
                    "— inheritance, law, divine order, consent, competence, force, "
                    "self-determination. State what the FILM treats as legitimate, "
                    "not what you believe is legitimate."
    )
    opening_power: str = Field(description="Who holds power when the film opens.")
    closing_power: str = Field(description="Who holds power when the film closes.")
    what_is_restored: str = Field(
        description="What the ending puts back the way it was. '' if nothing."
    )
    what_is_overturned: str = Field(
        description="What the ending permanently changes or dismantles. '' if nothing."
    )

    antagonist: str = Field(description="Principal antagonist, or '' if none.")
    antagonist_origin_given: bool = Field(
        description="Does the film supply a backstory that explains, and partly "
                    "mitigates, the antagonist's conduct?"
    )
    antagonist_origin: str = Field(description="That backstory in one sentence, or ''.")
    antagonist_fate: AntagonistFate

    protagonist_flaw: str = Field(description="What the protagonist must overcome in themselves.")
    protagonist_change: str = Field(
        description="What replaces that flaw. Note specifically whether the "
                    "protagonist ends by TAKING UP something handed to them or "
                    "PUTTING DOWN something imposed on them."
    )

    interiority_granted: list[str] = Field(
        description="Characters whose inner life the film shows from inside."
    )
    interiority_withheld: list[str] = Field(
        description="Significant characters kept external — seen, never inhabited."
    )

    punished: list[str] = Field(description="Who the narrative punishes.")
    forgiven: list[str] = Field(description="Who the narrative forgives or redeems.")

    final_image: str = Field(description="What the last scene shows and asserts.")
    final_spoken_line: str = Field(
        description="The last significant line of dialogue, verbatim, if the "
                    "evidence contains it. '' otherwise. Do not reconstruct from memory."
    )

    tonal_register: TonalRegister
    depicts_but_does_not_endorse: bool = Field(
        description="True when the film presents conduct or an order it is "
                    "actually critiquing — satire, irony, an unreliable narrator. "
                    "A sincere war picture and a satire of one describe the same "
                    "events; this flag is the difference."
    )
    endorsement_evidence: str = Field(
        description="What in the evidence settles the previous field either way."
    )

    source_text: str = Field(description="Work this adapts or retells, or ''.")
    inverts_source_how: str = Field(
        description="If it retells an earlier story with the moral valence "
                    "changed, what specifically is inverted. '' otherwise."
    )

    evidence_quotes: list[str] = Field(
        description="3-8 short verbatim spans from the supplied evidence that "
                    "support the fields above. Quote only what is present."
    )
    unsupported_fields: list[str] = Field(
        description="Field names you could not ground in the supplied evidence. "
                    "Be honest and complete here — this list is the measurement "
                    "the source comparison depends on."
    )
    confidence: float = Field(ge=0.0, le=1.0)


class Proposition(BaseModel):
    text: str = Field(
        description="A moral proposition, stated as a general claim about how to "
                    "live or how the world is morally ordered. No proper nouns, "
                    "no plot specifics — it must be a statement a hundred other "
                    "films could also affirm or deny."
    )
    stance: Literal["affirms", "denies"]
    evidence: str = Field(description="What in this film settles it. Quote where possible.")


class PropositionSet(BaseModel):
    propositions: list[Proposition]


class ItemScore(BaseModel):
    item_id: str
    verdict: Literal[
        "strongly_affirms", "affirms", "denies", "strongly_denies", "not_addressed",
    ] = Field(
        description="How firmly the film takes this position. Use not_addressed "
                    "when the film never raises the subject — that is NOT a denial.")
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="How sure YOU are of the reading. Separate from how firmly "
                    "the FILM holds it, which is the verdict.")
    # Optional, because it is routinely omitted for `not_addressed` — there is
    # nothing to quote when the film never raised the subject. Requiring it cost
    # 58 of 150 films in one batched run: pydantic rejected the whole slice over
    # a missing string on items the model had correctly called silent.
    evidence: str = Field(
        default="", description="Brief grounding from the supplied evidence. "
                                "May be empty when the verdict is not_addressed.")


class ScoreSet(BaseModel):
    """Sparse by design: only items the film actually engages.

    Most films engage a minority of any large bank, and 'does not address' is a
    real, informative state rather than a neutral midpoint — a comedy that never
    raises the question of legitimate authority is not the same as one that is
    balanced about it. Omission here becomes the salience mask downstream.
    """
    scores: list[ItemScore]


# A film can hold a position centrally or glancingly, and flattening those to
# one value threw away the difference between a film ABOUT revenge and one that
# mentions it. Stored at this scale; every reader normalises to -1..1.
VERDICT_TO_INT = {
    "strongly_affirms": 2, "affirms": 1,
    "denies": -1, "strongly_denies": -2,
    "not_addressed": 0,
}
MAX_STRENGTH = 2
