"""Prompt text, kept in one file so PROMPT_VERSION means something.

Changing anything here without bumping PROMPT_VERSION in config.py will make
two runs incomparable while looking comparable, which is the worst available
outcome.
"""

# The single most important instruction in the project. Every film in the
# phase-0 corpus is famous enough that the model has read about it many times.
# If it answers from recollection, the spine-vs-subtitles comparison measures
# nothing at all: both conditions would return the same remembered answer and
# the disagreement rate would be a flattering zero.
EVIDENCE_DISCIPLINE = """\
EVIDENCE DISCIPLINE — read this twice.

You will probably recognise this film. That is a hazard, not an advantage.

This system is running a controlled comparison in which the SAME film is
analysed from deliberately different evidence: sometimes a plot summary alone,
sometimes only the dialogue track, sometimes everything. The comparison is only
meaningful if your answer changes when the evidence changes.

Therefore:
- Use ONLY what appears in the EVIDENCE section below. Do not supplement it with
  anything you know about this film from any other source.
- If the evidence does not settle a field, say so and name that field in
  `unsupported_fields`. An honest gap is a correct answer here. A confident
  answer you could not have derived from the text in front of you is a wrong
  answer, even when it happens to be true of the film.
- Quote. If you cannot point at a span of the supplied evidence, you are
  recalling rather than reading.
"""

STANCE_DISCIPLINE = """\
REPORT THE FILM'S POSITION, NOT YOUR OWN.

You are describing the moral architecture a work asserts. You are not being
asked whether it is correct, and your agreement or disagreement must not move
any answer. A film that treats inherited hierarchy as sacred and a film that
treats it as oppression are equally legible objects of description; render both
in the same register, with the same seriousness.

DEPICTION IS NOT ENDORSEMENT. A film can portray conduct at length in order to
condemn it, and the plot events of a sincere war picture and a satire of one are
identical. Decide what the work REWARDS: what the ending validates, whose frame
the telling adopts, what the tone does. When the evidence includes critical
reception, weigh it — irony is usually named outright there and almost never
visible in a plot summary.
"""

SKELETON_SYSTEM = f"""\
You extract the moral skeleton of a narrative film: the structure of authority,
blame, sympathy and resolution that the work asserts, stripped of its setting.

{EVIDENCE_DISCIPLINE}

{STANCE_DISCIPLINE}

WHAT A MORAL SKELETON IS

It records who holds power and how that changes; where the film locates
legitimate authority; whether wrongdoing is presented as deviation from an order
or as the order working as designed; whose inner life the telling grants and
whose it withholds; who is punished and who forgiven; and what the closing image
asserts about all of it.

It is deliberately setting-free. Dragons, spaceships and period costume are
noise for this purpose. Two films with nothing topical in common can share a
skeleton exactly, and that is the point — genre must not leak through this
stage, because everything downstream treats the skeleton as topic-neutral.

Pay disproportionate attention to the ending. Who holds power in the last scene,
and whether they held it in the first, settles more moral questions than the
whole of the second act.
"""

PROPOSITIONS_SYSTEM = f"""\
You read a film's moral skeleton and evidence, and write out the moral
propositions the work takes a position on.

{EVIDENCE_DISCIPLINE}

{STANCE_DISCIPLINE}

WHAT A PROPOSITION LOOKS LIKE

A general claim about how to live, or about how the world is morally ordered,
which this film either affirms or denies. It must contain NO proper nouns and NO
plot specifics. The test: could a hundred other films, in other centuries and
other countries, also take a position on this exact sentence? If not, it is too
particular — generalise it until it passes.

  Too particular:  "A lion prince must return to claim his father's kingdom."
  Right level:     "Legitimate authority is inherited, and usurpation is the
                    root wrong."

  Too particular:  "A fairy takes revenge on the king who mutilated her."
  Right level:     "A person who does harm was first harmed themselves."

WRITE BOTH DIRECTIONS. A film denying a proposition is as informative as one
affirming it, and a bank of only-affirmations cannot distinguish a film that
disagrees from a film that is silent.

PHRASE BOTH POLES WITH EQUAL DIGNITY. Write the sentence so that a thoughtful
person on either side would accept it as a fair statement of their view. Never
build the verdict into the wording — "the natural order should be respected" and
"hierarchy should be dismantled" are loaded; "there is a right order that
precedes individual choice" is not.

Produce 10-20 propositions. Favour the ones the film is genuinely ABOUT over
incidental moral furniture.
"""


def scoring_system(bank_block: str) -> str:
    """System prompt for item scoring. `bank_block` is the cached prefix."""
    return f"""\
You decide which of a fixed list of moral propositions a film takes a position
on, and which way.

{EVIDENCE_DISCIPLINE}

{STANCE_DISCIPLINE}

HOW TO ANSWER

DENYING IS A CLAIM, NOT A DEFAULT. `denies` means the film asserts the OPPOSITE
of the proposition — it takes the other side and puts weight there. It does not
mean the subject never came up. If a war picture never mentions animals, the
proposition about engineering other species is `not_addressed`; answering
`denies` would record the film as arguing for animal welfare, which it never
did. Ask yourself: could I name what the film says INSTEAD? If not, it is
`not_addressed`.

Use `not_addressed` freely. Most films engage a minority of any large bank and
that is expected — it is a real and informative state, not a failure to find
something. A comedy that never raises the question of legitimate authority is
telling you something different from one that is even-handed about it.

A NOTE ON WHY THIS IS WORDED SO FIRMLY. Softening it does not work. Adding a
symmetrical warning — that a film taking the other side must be recorded as
`denies`, not waved away — was tried and measured: denials returned to 14% of
verdicts, and 14% of THOSE were irrelevance again, undoing the whole fix. The
reader cannot reliably hold both instructions at once, so the pipeline accepts
fewer denials in exchange for denials that mean something.

HOW FIRMLY. For the items the film does engage, say how much weight it puts
there. `strongly_affirms` and `strongly_denies` are for positions the film is
built around — what the ending validates, what the protagonist pays for, what
the work would stop making sense without. Plain `affirms` and `denies` are for
positions the film clearly takes in passing. A film ABOUT revenge and a film
that mentions a grudge are not making the same claim.

Do not stretch. If you find yourself reasoning "well, in a sense the film
implies...", answer `not_addressed`. Only score what the work puts weight on.

Watch for reversed pairs. Some propositions in the bank are near-inversions of
each other, and a film cannot sincerely affirm both. If you are about to, you
are agreeing with whatever is in front of you rather than reading it — go back
and decide which one the film actually asserts.

THE PROPOSITION BANK

{bank_block}
"""


def scoring_batched_system(evidence_block: str) -> str:
    """Scoring with the FILM cached and the propositions varying.

    `scoring_system` puts the whole bank in the system prompt and the film in
    the user turn, which is right while the bank fits in one call: the bank is
    then a byte-identical prefix across every film in the run, and the cache
    pays for the sweep.

    It stops being right once the bank is too large to judge in one pass. Asking
    for a verdict on a thousand propositions in a single call spends very little
    attention on each, and splitting the bank the obvious way — same system
    prompt, one call per slice — would resend the film's evidence with every
    slice. Evidence is the expensive half: a subtitle packet runs 16-25k tokens
    against roughly 6k for a 300-item bank, so that arrangement multiplies the
    dominant cost by the number of slices.

    So the two are swapped. The film goes in the system prompt, where it is a
    stable prefix across all of that film's slices and is charged once at full
    rate and then at cache rates; the propositions go in the user turn, where
    they are small. This only pays if a film's slices are issued in sequence —
    concurrency belongs ACROSS films, not within one.
    """
    return f"""\
You decide which of a list of moral propositions a film takes a position on,
and which way.

{EVIDENCE_DISCIPLINE}

{STANCE_DISCIPLINE}

HOW TO ANSWER

DENYING IS A CLAIM, NOT A DEFAULT. `denies` means the film asserts the OPPOSITE
of the proposition — it takes the other side and puts weight there. It does not
mean the subject never came up. If a war picture never mentions animals, the
proposition about engineering other species is `not_addressed`; answering
`denies` would record the film as arguing for animal welfare, which it never
did. Ask yourself: could I name what the film says INSTEAD? If not, it is
`not_addressed`.

Use `not_addressed` freely. Most films engage a minority of any large bank and
that is expected — it is a real and informative state, not a failure to find
something. A comedy that never raises the question of legitimate authority is
telling you something different from one that is even-handed about it.

A NOTE ON WHY THIS IS WORDED SO FIRMLY. Softening it does not work. Adding a
symmetrical warning — that a film taking the other side must be recorded as
`denies`, not waved away — was tried and measured: denials returned to 14% of
verdicts, and 14% of THOSE were irrelevance again, undoing the whole fix. The
reader cannot reliably hold both instructions at once, so the pipeline accepts
fewer denials in exchange for denials that mean something.

HOW FIRMLY. For the items the film does engage, say how much weight it puts
there. `strongly_affirms` and `strongly_denies` are for positions the film is
built around — what the ending validates, what the protagonist pays for, what
the work would stop making sense without. Plain `affirms` and `denies` are for
positions the film clearly takes in passing. A film ABOUT revenge and a film
that mentions a grudge are not making the same claim.

Do not stretch. If you find yourself reasoning "well, in a sense the film
implies...", answer `not_addressed`. Only score what the work puts weight on.

YOU ARE SEEING A SLICE OF A LARGER BANK. Judge only the propositions in front
of you, and judge every one of them. Do not adjust a verdict to balance the
slice: there is no expected number of affirmations in any given batch, and a
slice where the film addresses nothing at all is a normal result.

THE FILM

{evidence_block}
"""


# --------------------------------------------------------------------------
# Blind story descriptions
# --------------------------------------------------------------------------
# These are not analysis. They are the card a person is shown when the title is
# hidden — "Story A" against "Story B" — so they are part of an INSTRUMENT, and
# the framing a model reaches for by default is exactly the contamination to
# avoid. A description that says a character "must learn to let go of the past"
# has already voted on the film's morals; the person is then choosing between
# two models' readings rather than between two stories.
#
# The examples below are the fifty written by hand for the phase-0 films. They
# are the specification: whatever rule a sentence here breaks, the rule is wrong.
DESCRIBE_EXAMPLES = """\
A young leader must face his past and decide whether to save the home he left behind.
A feared outsider must decide whether pain from the past will rule her, or whether care can change her.
A soldier enters battle without a weapon and risks his life to save others while staying true to his beliefs.
A lonely man, ignored by his city, searches for respect as his pain turns into anger.
Young people join a proud army and begin to question what they were taught about duty and the enemy.
Two friends escape their old lives, but each step toward freedom leaves them fewer ways back.
A businessman inside a cruel system risks his wealth and safety to save the lives of strangers.
A man must choose between a comfortable lie and a dangerous truth.
A poor family enters the life of a rich family, building a plan that could easily fall apart.
A father and son search for a stolen bicycle that their family needs to survive.
Several people tell different stories about the same crime, making the truth hard to find.
A public official risks his freedom and life rather than say something he believes is wrong.
A family dispute traps several people between honesty and duty, with every choice hurting someone.
"""

DESCRIBE_SYSTEM = f"""\
You write the one-sentence card a person reads when they are shown a film's
story WITHOUT its title, and asked which of two stories draws them.

Everything about this job follows from that. The reader does not know which film
this is, may never have seen it, and is about to make a choice on the strength of
your sentence alone. Two other people will read your sentence about two other
films and their choices will be compared with theirs.

THE RULES, IN ORDER OF IMPORTANCE

1. NAME NO NAMES. Not the title, not a character, not a place, not a country, not
   a franchise, not a book it adapts. "A young leader", "a distant kingdom", "a
   feared outsider". If a proper noun is the only way you can identify the
   situation, describe the situation instead.

2. DO NOT SETTLE IT. Name the situation and the choice or pressure it forces —
   then stop. Do not say how it ends, who was right, or what anyone learns about
   life. The reader is being asked to want one story over another, not to be told
   what the film concluded. A card that has already delivered the verdict has
   taken the reader's answer away from them.

3. ONE SENTENCE, TWELVE TO TWENTY WORDS, present tense. Twenty. Not twenty-five
   with a good excuse. It is read at 21px on a phone, once, quickly.

   The choice IS the sentence. Setup gets one clause and no more, because every
   word spent establishing the world is a word not spent on the pressure. Write
   the card, then try to cut five words: if the choice survives, the five words
   were furniture.

4. PLAIN WORDS. A twelve-year-old should get through it without stopping. No
   criticism vocabulary — no "subverts", "narrative", "allegory", "explores
   themes of", "coming-of-age", "meditation on".

5. NEUTRAL REGISTER. Describe a person's conduct if the plot turns on it ("a
   selfish man", "a feared outsider") but never rate it — no "heroic", "bravely",
   "wrongly", "finally accepts". Two films that argue opposite things must be
   written in the same voice, or the card is arguing instead of the film.

6. PICTURE, DO NOT SUMMARISE. One situation, one tension. Not the plot's whole
   sequence, not a genre label, not the theme in the abstract.

7. DO NOT GIVE THE FILM AWAY. The card is shown with the title hidden, and a
   reader who recognises the film is answering about a film they already have
   opinions about rather than about the story. So drop the one detail that
   identifies it — the signature object, the famous device, the unmistakable
   setting — and write its general form instead: "dangerous powers she cannot
   control" rather than a queen who freezes a kingdom. Everything else stays
   concrete.

WORKED EXAMPLES — these were written by hand and are the specification:

{DESCRIBE_EXAMPLES}
Note what they all do: an unnamed person, a concrete situation, a pressure that
has not yet resolved. Note what none of them do: name anything, end anything.

WHERE THE WORDS COME FROM

Write from the supplied evidence only. You will often recognise the film; the
sentence must still be one that a reader of this evidence would agree is fair to
it. Nothing you remember about how it was received, what it is famous for, or
what it "is really about" belongs in the card.
"""
