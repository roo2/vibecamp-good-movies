# Moral Atlas

Discover the moral structure of narrative film from text, then project it onto a
single axis that reflects your own judgements.

The design document — method, axes, confounds, validation — is the companion
artifact. This README covers the machine.

## The idea in one paragraph

Films are treated as **respondents** and moral propositions as **items**, the
way the Big Five personality factors were discovered: harvest a large pool of
statements from the corpus itself, cut it to a fixed bank, score every film
against every item, and factor analyse the result. Nothing is imposed — the
factors are whatever survives rotation. Your own verdicts on ~80 films you have
actually seen then supply a discriminant direction through that space, which is
the personal moral axis everything is finally ranked along.

## Status

| Stage | State |
|---|---|
| Store (Postgres) | DuckDB → SQLite → Postgres; 358,123 rows carried across |
| Ingestion (Wikipedia / Wikidata / OPUS subtitles) | working — 40/40 plot, 40/40 reception, 39/40 subtitles, no API keys |
| Evidence packets and A/B variants | working — all four conditions runnable on 39/40 films |
| Moral skeleton extraction | built, needs `ANTHROPIC_API_KEY` |
| Proposition harvesting | built, needs key |
| Item bank construction | built, needs key (or `--no-llm` to cluster only) |
| Item scoring | built, needs key |
| Source A/B analysis | built |
| Factor analysis, verdict UI, atlas views | not yet |

## Setup

```bash
python3 -m venv .venv && ./.venv/bin/pip install -e .
cp .env.example .env        # then fill in what you have
./.venv/bin/atlas init      # creates the DB, reports which keys are present
```

Only `ANTHROPIC_API_KEY` truly gates things. Wikipedia needs no credential, so
ingestion works immediately; TMDB and subtitles degrade to "layer absent" rather
than failing.

## Phase 0 — the $10 experiment

The question phase 0 answers is whether a Wikipedia plot summary is good enough,
or whether the film's own dialogue is required. It is settled with a measurement
rather than an argument.

```bash
atlas ingest                       # 40 seed films, all evidence layers
atlas status                       # completeness per film, runnable variants
atlas skeleton                     # stage 1, under every evidence condition
atlas propose                      # stage 2, harvest the raw statement pool
atlas bank --version b1            # cluster and canonicalise into an item bank
atlas bank-export                  # -> data/bank.jsonl, for your ~90 min prune
atlas bank-import                  # read the pruned bank back
atlas score --version b1           # stage 3, score every film in every condition
atlas ab --version b1              # the verdict
```

## Moral dimensions

The item bank is an instrument, not an answer: hundreds of propositions is a
fine thing to score against and a useless thing to hand a person. These commands
reduce it to a handful of named axes and then try to knock them down.

```bash
atlas dimensions --version d1 --n-dims 8 \
    --cross-model claude-sonnet-5  # derive the axes, place every item on one
atlas dimensions-validate          # the evidence that they are real
atlas dimensions-split-half        # derive twice from disjoint halves of the corpus
atlas profile                      # where each film sits
```

## Taste, and the recommender

The steps above read what a film ARGUES, from its own dialogue. A second half of
the pipeline reads something different — who likes these films TOGETHER — from
an outside ratings corpus, and it is what actually drives recommendations: over
162,000 outside raters, co-preference orders a film someone liked above one they
disliked 83% of the time, against the moral axes' 57%.

```bash
atlas taste-build                  # neighbours, taste dimensions, adjusted morals
atlas taste-null                   # the permutation test with taste removed
atlas dataset                      # publish it
```

It needs the MovieLens ml-25m extract in `data/movielens/ml-25m` (or
`MOVIELENS_DIR`). That data is licensed for non-commercial research and may not
be redistributed, so it is not vendored here; download it from
[GroupLens](https://grouplens.org/datasets/movielens/25m/). Nothing derived from
it that reaches the database or the corpus export contains ratings — only
aggregates over our own films.

**Run `atlas taste-build` after ingesting films.** `atlas model-scan` gives a new
film a moral position and nothing else: no taste position and no neighbours, so
it can be looked up but never recommended, and it drops out of every
taste-adjusted figure. Nothing errors when this is skipped.

One hazard is worth knowing about, because it has been shipped twice. The taste
dimensions come out of an SVD, and an SVD component's sign is arbitrary — so
re-deriving the axes over a larger corpus flips about half of them, and the pole
labels, which are fixed text in `seeds/taste-dimensions.yaml`, then describe the
wrong ends with nothing failing. Every named dimension therefore carries an
`anchor`: a tag from the MovieLens genome that belongs at its `pole_high` end.
`taste-build` checks each component against its anchor and turns it the right way
up, reporting any it had to flip.

## Showing it to someone

It is at **https://moviecompass.net**, and the dataset explorer is a page inside
it at `#/atlas`. Both are served by the same dyno that serves the API, so the
explorer reads the store live through `/api/atlas` — a pipeline run shows up on
reload rather than on rebuild.

That endpoint is a permutation test as much as a page, so its answer is kept in
`documents` and rebuilt only when the corpus counts move. See
[`infra/README.md`](infra/README.md).

`atlas dataset` still writes the same document to a file, which is what to reach
for when somebody wants the numbers without the site:

```bash
atlas dataset                      # -> src/frontend/public/data/atlas.json
atlas dataset --check              # non-zero if that file is behind the store
```

The page is built around the reduction the project claims — 696 harvested
propositions down to 8 axes — and around the evidence that the reduction is
real rather than imposed. `atlas dataset` runs the same battery
`atlas dimensions-validate` prints (blind re-assignment, and two permutation
tests against verdicts recorded before the axes existed) and publishes the
numbers with the seed that produced them, so a figure on the page can be
reproduced from the command line. It is a few seconds of arithmetic with no API
call. Each film is then presented axis by axis, and every position expands into
the propositions it was scored on, the verdict, and the grounding the scorer
gave — so a number can be read back to the sentences behind it.

Re-run `atlas dataset` after any pipeline stage; the page shows whatever the
store holds at that moment, and says which evidence condition every film was
read under. It is public by design — outside the sign-in guard, carrying no
user data.

The source text travels with it, so every claim is checkable against what it was
read from: plot, themes, reception and the dialogue track. That is 3MB against a
240KB index, so it is written as one file per film — `data/atlas/<film_id>.json`
— and fetched only when somebody opens that film. `--no-evidence` leaves it out.
Locally the same page also reads a live `GET /api/atlas`, so a pipeline run shows
up on reload without a rebuild.

Note that the axes are derived semantically, by an LLM reading the bank, and not
by the TF-IDF clustering that cuts the bank. That clustering compares vocabulary
rather than meaning, and on canonicalised propositions it barely merges anything
— the typical nearest-neighbour cosine similarity is ~0.12 against a merge
threshold that demands 0.55. Forcing small *k* does not help either: LSA plus
k-means scores a silhouette around 0.03, which is a numerical way of saying the
lexical structure is not there.

That invites a fair objection — an LLM asked for eight moral dimensions will
always produce eight moral dimensions — so `dimensions-validate` reports evidence
rather than a verdict, and four of its five tests can fail:

| Test | What it would mean if it failed |
|---|---|
| Split-half | Axes derived from disjoint film sets disagree → they came from the prompt, not the corpus |
| Blind replicate | Items shuffled and axes renumbered, and agreement collapses → items have no determinate home |
| Cross-model | A second model disagrees → one model's taste, not a real distinction |
| Co-engagement | Films do not engage same-axis items together → the axis is not in how the corpus behaves |
| Stance coherence | Films scatter across a pole instead of landing on one → not an axis |

The last two are permutation-tested against a null that shuffles which item sits
on which axis while holding the axis sizes fixed, so lopsided groups cannot
manufacture significance. Both discard each film's verdicts on items harvested
from that same film by default, since almost every item traces back to one film
and letting it vote for its own propositions would inflate the result for free.
Every number is seeded, so anything quoted can be re-run.

### Evidence conditions

The A/B works by withholding layers. The same film, the same propositions,
different evidence:

| Variant | Layers | Question it answers |
|---|---|---|
| `spine` | plot only | Is a human-written summary enough? |
| `spine_themes` | plot + themes + reception | Does adding critical reading fix it? |
| `subs` | subtitle track only | The reference — no summariser in the loop |
| `full` | everything | Ceiling |

`atlas ab` reports two kinds of disagreement separately, because they mean
different things. A **flip** is both conditions taking opposite positions — the
cheap source is *wrong*, and flips poison a factor analysis silently. A
**silence** is one condition not engaging at all — the cheap source is *thin*,
which the salience mask already models honestly. A 20% disagreement made of
silence is a very different verdict from 20% made of flips.

## Where subtitles come from

The obvious route, the OpenSubtitles REST API, does not scale here: 5 downloads
per day anonymously, 20 with a free account, ~1,000 on a paid VIP subscription.
A 40-film pilot is two days of waiting; a 2,000-film sweep is three months.

So the default source is the **OPUS OpenSubtitles corpus** (Helsinki NLP), which
republishes the whole collection as a citable research corpus. It ships as one
very large zip — 13.7 GB for v2018, 35.8 GB for v2024 — but the host supports
HTTP range requests, so the archive is never downloaded. `atlas opus-index`
fetches only the Zip64 central directory (~70-180 MB, once) and builds a local
index of IMDb id to byte offset; each film then costs two ranged requests and
about 80 KB.

```bash
atlas opus-index --version v2024     # 444,595 titles, one-off
atlas ingest                         # subtitles now arrive with everything else
```

Sources are tried in order:

1. **`SUBTITLES_DIR`** — a hand-supplied `.srt` named `<film_id>.srt`. Always
   wins. The only route that carries SDH speaker labels.
2. **OPUS** — v2024 then v2018. No account, no daily limit.
3. **OpenSubtitles API** — for films newer than the archive release.

Three things worth knowing:

- **OPUS strips SDH speaker labels.** Dash-prefixed two-speaker cues survive, so
  turn-taking is visible, but `[MUFASA]`-style attribution is gone in v2018
  (v2024 retains more). Where it matters, hand-supply the track.
- **Track selection is by plausibility, not size.** OPUS holds dozens of tracks
  per film, and the largest is often a concatenated dual-language file — the
  biggest Lion King track runs 3,132 cues to 165 minutes for an 88-minute
  picture. Candidates are ordered by closeness to the median size and validated
  against the film's runtime (from Wikidata P2047) before being accepted. A
  wrong timeline silently puts the "closing 15%" in the wrong place, which would
  corrupt every ending-derived proposition.
- **IMDb ids come from Wikidata** (P345), not TMDB, so the subtitle layer needs
  no TMDB account either.

Cite the corpus if any of this is published: Lison & Tiedemann (2016),
*OpenSubtitles2016: Extracting Large Parallel Corpora from Movie and TV
Subtitles*, LREC.

## The one-line story cards

Every film carries a `description`: one sentence, twelve to twenty words, no
proper nouns, present tense, ending withheld. It is the line under the title on
a swipe card, and it is the whole of what a person sees in the blind story pair,
where the title and poster are hidden and two films are judged as stories alone.

Fifty were written by hand. They are the specification — `DESCRIPTIONS` in
`sources/seed.py` — and nothing overwrites them. The rest are condensed from the
film's Wikipedia plot section by `atlas describe`, and stamped in
`films.description_source` so a generated card can always be told from a written
one, found, and replaced.

```bash
atlas resolve-articles      # IMDb id -> Wikipedia article, via Wikidata
atlas backfill-plots        # the plot/themes/reception layers for films missing them
atlas describe              # ~640 words of plot -> one sentence
```

**Why Wikipedia and not a film API.** TMDB's terms bar using its content in
connection with an AI or ML application, and IMDb's non-commercial licence is
narrower still; a one-line overview from either cannot legally be fed to a model
or stored as a derived corpus. Wikipedia plot sections are CC BY-SA, run about
640 words, and are written to an editorial policy that keeps interpretation out
— which is the same reason the `spine` evidence condition reads them. The corpus
already held the identifiers to reach them.

**Resolution is by identifier, never by title.** `search_article` returns a
confident answer whether or not it is the right film, and on this corpus it was
wrong twice: Carlos (2010) resolved to Marmaduke, Jeanne Dielman to Gerry. Both
films had also been ingested under the wrong IMDb id, so their subtitle tracks
belong to those films too — a card that did not sound like the film it was filed
under is what surfaced it. `resolve-articles` checks each stored id against the
labels, aliases and release years Wikidata holds for it and reports the ones
that point at another film rather than following them.

Both were then taken out of the corpus with `atlas remove-film`, which is why it
holds 674 films rather than 676. Everything either film contributed — verdicts,
taste positions, similarity edges in *other* films' neighbour lists, set
memberships — was derived from another film's dialogue, so repairing the row
would have meant re-scoring it from scratch, and neither is load-bearing for
anything the project claims. Removal sweeps every table that names a film,
found from the schema rather than from a list somebody has to remember to
update. Run it against the deployed store as well: a corpus push replaces corpus
tables, and a film somebody there has rated is kept rather than deleted — the
push names the ones it kept.

**The house style is checked, not requested.** `describe_problems` rejects a
card that runs long, names anything, uses more than one sentence, rates the
story or reaches for criticism vocabulary; a rejected card is rewritten once
with the specific failure quoted back. The rules are held to the fifty
hand-written cards — a test asserts all fifty pass the check that gates the
generated ones, so a rule that rejects the specification is a broken rule. Cards
that survive neither attempt are left unwritten, and re-running `atlas describe`
picks them up.

## Looking at the data

The store is Postgres, so anything that speaks Postgres reads it — `psql`,
pgAdmin, DBeaver, TablePlus, pandas.

```bash
psql moral_atlas                           # CLI
python -c "import psycopg,pandas as pd; \
  print(pd.read_sql('SELECT * FROM runs', psycopg.connect('dbname=moral_atlas')))"
```

`DATABASE_URL` (or `ATLAS_DB`, which is the same setting) points every `atlas`
command at another store, so reading production for an afternoon never means
editing a config file.

### Getting the corpus without running a sweep

A sweep costs money and an API key. If someone else has already run one, take
theirs — the deployed store holds it, and Heroku will hand you a copy:

```bash
heroku pg:backups:capture -a moral-atlas
heroku pg:backups:download -a moral-atlas -o /tmp/atlas.dump
createdb moral_atlas && pg_restore --no-owner --no-privileges -d moral_atlas /tmp/atlas.dump
```

Films, skeletons, propositions, the item bank, the dimensions and every score —
and, unlike the corpus export it replaces, the user tables as well — a backup is
a backup. Treat it accordingly: it is people's ratings.

Sending work the other way is `atlas corpus-push`, which replaces the corpus
tables in a deployed store and refuses to touch the user ones. The laptop is
authoritative for the corpus, the app for the people, and neither overwrites
the other. See [`infra/README.md`](infra/README.md).

In `psql`, `\x auto` and `\pset null '∅'` make output readable.

```sql
\dt
SELECT stage, model, n_calls, cost_usd FROM runs ORDER BY started_at;
SELECT variant, count(*) FROM skeletons GROUP BY 1;
SELECT film_id, data::json->>'legitimacy_source'
FROM skeletons WHERE variant = 'full' LIMIT 10;
```

## Design notes

**Evidence discipline.** Every phase-0 film is famous enough that the model has
read about it many times. If it answers from recollection the A/B measures
nothing — both conditions return the same remembered answer and the disagreement
rate is a flattering zero. `llm/prompts.py` therefore instructs hard against
supplementing the packet, requires verbatim quotes, and asks the model to name
its own ungrounded fields in `unsupported_fields`. **Watch that field.** If it is
consistently empty on `spine`, the discipline is not holding and the A/B is
measuring the model's memory rather than the evidence.

**Nothing is overwritten.** Every skeleton, proposition and score is stamped with
`run_id`, `model` and `prompt_version`. Changing a prompt without bumping
`PROMPT_VERSION` in `config.py` makes two runs incomparable while looking
comparable — the worst available outcome.

**Genre is withheld from the scorer** and kept only as a confound covariate.
Feeding it in would let topic leak back into propositions the whole design is
trying to keep topic-free.

**Caching.** The item bank is a byte-identical prefix across every scoring call,
so it goes in the system block behind a cache breakpoint with the film's evidence
after it. That is most of the reason a full sweep costs tens rather than
hundreds.

## Keeping the atlas page current

The explorer reads from two places, and the order is the whole of whether the
page can be trusted.

`/api/atlas` re-reads the store on every request and caches against its mtime,
so it is **fresh by construction** — a pipeline run shows up on reload. It is
tried first. `/data/atlas.json` is a snapshot `atlas dataset` writes into
`public/`, and is what the published demo serves, because a bucket has no store
behind it. The footer says which one answered.

That order used to be the other way round, and the failure was not theoretical:
a new section was added to the page, the store had the data, and the page
rendered nothing — because a committed snapshot from an earlier state answered
first and won.

So:

- **Running the app locally or on the runner** — nothing to do. The API is
  authoritative and the page follows the store.
- **Publishing the static demo** — the snapshot is only as current as the last
  rebuild, so check before committing:

```bash
atlas dataset            # rebuild the snapshot from the store
atlas dataset --check    # exit non-zero if it is behind; for a pre-commit hook
```

`--check` compares **counts, not timestamps**. There is no file to stat any
more, and there never was a good answer in one: under SQLite the writes landed
in a WAL and the store's own mtime could sit still through an entire sweep, so
the check reported "current" while the corpus was being rewritten underneath it
— the one moment it must not. CI cannot run this at all: the store is not in the
repository, so the machine that builds the site has nothing to compare against.

## Which model produced this?

Every derived row records the model and prompt version that made it, so the
question can be asked of any layer:

```bash
atlas provenance                 # model per layer, and a warning if a layer is mixed
atlas backfill-provenance --model claude-opus-5   # for rows written before this existed
```

```
layer         table             model          prompt  rows
skeleton      skeletons         claude-opus-5   p1       284
propositions  propositions_raw  claude-opus-5   p1       696
bank          item_bank         claude-opus-5   -        694
scoring       scores            claude-opus-5   p1     3,629
```

The bank line is the one that changed. `build_bank` never opened a run, so the
step that **rewrote the majority of the harvested propositions** — the wording
every film is scored against — was the only step you could not attribute. It now
opens a run like any other stage.

Rows carrying a `run_id` are backfilled losslessly from `runs`. The bank cannot
be: its model was never recorded anywhere, so it has to be asserted by whoever
remembers the run, which is what `--model` is for. `atlas provenance` flags a
layer built by more than one model — fine deliberately, misleading by accident,
since a layer built by two models is not one instrument.

## Whose morals are in the scores?

Every number in the atlas came from one model reading a film and voting on 694
moral propositions. That model has moral opinions of its own, so an equally good
explanation of the whole corpus is that we have measured `claude-opus-5`
carefully, forty times. Nothing in the pipeline so far can tell those two
explanations apart.

The design that separates them is a substitution: hold the bank, the evidence
packet, the rubric and the film byte-identical, and change only the scorer. What
survives is the film; what moves is the scorer.

```bash
atlas models                                  # who is available, and which keys are set
atlas model-scan --scorers grok,deepseek,hermes --limit 10
atlas model-bias                              # engagement, refusals, agreement, lean
```

Four things get measured. **Engagement** is how many items a scorer thinks a
film takes a position on at all — a model that engages half as much is measuring
something narrower, not being more careful. **Refusal** is the guardrail
question put directly: a model that will not say what a film argues about
obedience has returned a missing answer rather than a neutral one, and
missingness is not evenly spread across the axes. **Agreement** is Cohen's kappa
on the cells two scorers both voted on, chance-corrected because the verdicts run
about two affirms per denial. **Lean** is the payoff: average each scorer's
polarity-adjusted verdicts within an axis, and a gap between two scorers reading
the *same forty films* cannot be a property of the films.

`model-scan` writes to `model_verdicts`, never to `scores`. The product's film
positions — and through them every user's profile — must not move because an
audit ran.

### Choosing a scorer without guardrails

Refusal training is only the visible half. A safety-trained model also learns
which conclusions are comfortable, and on a corpus about vengeance, complicity
and obedience that is exactly the variable under test — so a scorer with no such
training is a control, not a stunt. Three options, commercially available by API:

| alias | model | what it buys |
|---|---|---|
| `hermes` | Nous Hermes 3 405B (OpenRouter) | **Recommended.** Trained to follow the operator rather than an internal policy, with refusal behaviour deliberately minimised. Frontier-scale, so divergence from Claude is a difference of judgement rather than of competence — and it still returns clean JSON. |
| `dolphin` | Dolphin Mixtral 8x22B (OpenRouter) | Alignment data stripped from the fine-tune outright. Weaker, so read a gap as a floor: it may be incapacity rather than candour. |
| `llama-base` | Llama 3.1 405B base (OpenRouter) | The purest control — never had preferences trained into it at all. Hardest to hold to a schema, which is the price of asking what the pretraining distribution alone believes. |

`hermes` is the one to start with. The other two are worth running precisely
because they fail differently: if all three diverge from Claude in the same
direction, that is a finding; if only the weakest does, that is a bug in the
weakest.

## Layout

```
src/moral_atlas/
  config.py            settings, PROMPT_VERSION, cost estimation
  db.py                Postgres schema and helpers
  cli.py               the atlas command
  sources/
    _http.py           cached HTTP with rate-limit backoff
    tmdb.py            metadata + confound covariates
    wikipedia.py       path-aware section splitting
    subtitles.py       SDH-preferred acquisition, SRT parsing, act slicing
    packet.py          evidence packets and the A/B variants
    ingest.py          orchestration
  llm/
    prompts.py         all prompt text, versioned together
    schemas.py         structured output shapes
    client.py          caching, concurrency, retry, cost accounting
    stages.py          skeleton / propositions / scoring
  analysis/
    bank.py            clustering, canonicalisation, reversed pairs
    ab.py              the source comparison
tests/                 run with ./.venv/bin/python -m pytest tests/
seeds/phase0.yaml      the 40-film seed corpus
```
