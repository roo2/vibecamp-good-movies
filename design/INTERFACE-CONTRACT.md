# What the interface needs from the atlas

This is the seam between the two halves of the project. The interface is a pure
function of one payload — nothing in `design/*.dc.html` computes anything about
morality, it only renders what the atlas concluded.

Build the UI against `fixtures/session.json` and it will work before the pipeline
produces a single real score. Swap the fixture for a live endpoint later.

## The payload

```jsonc
{
  "factors": [                       // whatever factor analysis returns — 1, 2, 6, 8
    {
      "id": "f1",
      "name": "Given order ↔ Self-authorship",
      "pole_low":  { "label": "The old order was right",   "anchor_film": "the-lion-king-1994" },
      "pole_high": { "label": "The old order was the problem", "anchor_film": "maleficent-2014" },
      "variance_explained": 0.44     // the map prints the sum of the two it plots
    }
  ],
  "people": [
    { "id": "you",  "name": "You", "position": { "f1": 0.66, "f2": 0.34 } },
    { "id": "them", "name": "Sam", "position": { "f1": 0.45, "f2": 0.21 } }
  ],
  "films": [
    {
      "id": "spotlight-2015",
      "title": "Spotlight", "year": 2015, "runtime_min": 129,
      "poster_url": "https://image.tmdb.org/…",   // render-time only, see below
      "coverage": { "read": true, "layers": ["plot", "subs", "themes"] },
      "position": { "f1": 0.68, "f2": 0.15 },
      "premise": "Reporters work out how much of their own city they are willing to burn down in order to print the truth.",
      "tags": [
        { "label": "Everyone counts the same", "matches": ["you", "them"] },
        { "label": "The rot is in the system",  "matches": ["you", "them"] }
      ]
    }
  ],
  "session": {
    "shortlist": ["spotlight-2015", "…"],       // films in the gap between the two positions
    "agreement": [{ "factor": "f2", "gap": 0.05 }],
    "friction":  [{ "factor": "f1", "gap": 0.54,
                    "read": "You want the debt paid. Sam wants it repaired." }]
  }
}
```

All positions are 0–1 with the low pole at zero, matching the atlas's convention
of scoring each axis 0–100 with the Given Order pole at zero.

## Five things design needs that the backend does not yet produce

Listed in the order they block interface work.

1. **`film.premise` — one spoiler-free sentence naming the moral question.**
   This is the single most important string in the product. It is what makes a
   card readable in two seconds and what distinguishes this app from every other
   swipe-a-poster app. *Not currently produced.* The moral skeleton extraction in
   `llm/stages.py` already reads the film closely enough to write it; it needs a
   field and a prompt instruction — must name the dilemma, must not reveal how it
   resolves.

2. **`tag.label` — a value tag of four words or fewer.** Factor analysis yields
   top-loading *propositions*, which are full sentences. A card has room for
   about 28 characters. Something has to compress "The inherited social order is
   shown to be built and maintained at someone's expense" into "The rot is in the
   system". Cheapest place is a one-off pass over the finished item bank, so the
   labels are stable across every film rather than regenerated per card.

3. **`coverage.read`.** Drives the honest unread card state (card 4 of screen 7).
   `atlas status` already computes completeness per film — this is exposure, not
   new work. **A film with `read: false` must never render the confident
   presentation of a read one.** That rule is in the mockup for a reason.

4. **Factor names and pole labels.** The UI writes its own headlines from these
   (`"You agree about where cruelty comes from"`), so they need to be short,
   human, and phrased as claims rather than variable names. Naming them from
   their top-loading propositions is already the plan.

5. **`variance_explained`.** The map prints "these two account for 71% of what
   separates one story from another". If the real number is 40%, the map is the
   wrong screen and the bars win — so this number decides a design question, not
   just a caption.

## Two constraints that came out of the data work

**Posters are render-time only.** TMDB's terms bar using its content as ML input.
So `poster_url` is fetched by the client when a card paints and is never stored,
never fed to a model, and never part of the atlas. The mockups use drawn
placeholders for exactly this reason — they are not unfinished.

**Coverage will be patchy.** Subtitles beat scripts as the substrate (shooting
drafts get rewritten at the ending, which is precisely where moral propositions
are settled), but subtitle coverage is thin. Assume a meaningful fraction of any
popular-films deck is `read: false` and design every list state for it.

## One open question worth settling early

The atlas ranks on a **single personal axis** (a discriminant direction through
factor space, from your verdicts on ~80 films). The map screens plot **two**
factors. These are not in conflict — the 1-D axis is for *ordering* the deck, the
2-D plane is for *explaining* why two people differ — but the interface currently
only shows the second. If the personal axis turns out to be the more legible
idea, there is a third compass design in that: one line, both people on it, every
film placed along it. Worth a sketch before committing.
