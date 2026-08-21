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
| Ingestion (TMDB / Wikipedia / subtitles) | working, verified on 40 films |
| Evidence packets and A/B variants | working |
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

### Subtitles without an OpenSubtitles account

Set `SUBTITLES_DIR` to a folder of `.srt` files named `<film_id>.srt` (e.g.
`the-lion-king-1994.srt`). Local files always win over the API, so 40
hand-supplied tracks run the whole pipeline with no subtitle credential at all.

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

## Layout

```
src/moral_atlas/
  config.py            settings, PROMPT_VERSION, cost estimation
  db.py                DuckDB schema and helpers
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
