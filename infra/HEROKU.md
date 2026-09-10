# Heroku

Where this runs now. One app, one dyno, one Postgres database.

The AWS stack described in [`README.md`](README.md) is still up and still
serving; it is frozen at the last SQLite commit and nothing deploys to it any
more. Read that file for what exists there and how to take it down when the time
comes — not for how anything works today.

## The shape

| | What it is | Where it runs |
|---|---|---|
| **The atlas** | a batch pipeline that spends money on LLM calls | your laptop |
| **The interface and its API** | React build plus FastAPI | one Heroku dyno |
| **The store** | Postgres | a Heroku Postgres add-on |

The pipeline stays local on purpose. It needs API keys, a 60GB subtitle archive
and hours of wall time, none of which belong on a web dyno. What crosses is the
result: `atlas corpus-push` sends the derived tables straight into the app's
database. Code deploys itself on a push to `main`; data is a decision somebody
makes.

## Standing it up

The app is `movie-compass`, at **https://moviecompass.net**. This is how it was
made, and how a second one — a staging copy, a fresh start — would be:

```bash
heroku create movie-compass --region us
heroku buildpacks:add heroku/nodejs -a movie-compass    # order matters:
heroku buildpacks:add heroku/python -a movie-compass    # node builds the SPA first
heroku addons:create heroku-postgresql:essential-0 -a movie-compass
heroku ps:type basic -a movie-compass                   # after the first deploy:
                                                      # there are no dynos to
                                                      # resize before one exists
heroku config:set ATLAS_SERVE_FRONTEND=1 ATLAS_WARM_CACHE=1 -a movie-compass
heroku config:set ATLAS_FRONTEND_URL=https://moviecompass.net -a movie-compass
git push heroku main
```

`DATABASE_URL` is set by the add-on. Nothing else is required: the dyno serves
pages and reads the store, and it calls no model, so it needs no API key.

Then the data, once:

```bash
atlas corpus-push movie-compass
```

## The domain

`moviecompass.net`, registered at Cloudflare, which is also its DNS. Two records
point it here — the apex needs ALIAS/ANAME rather than A, because Heroku has no
static IPs, and Cloudflare's CNAME flattening is what makes that possible at all:

| Type | Name | Target |
|---|---|---|
| CNAME | `@` | `cryptic-dinosaur-zukyeayxamzpgmzrqk17iqti.herokudns.com` |
| CNAME | `www` | `safe-marigold-juxba63c3k8hwpxiy9gfnhur.herokudns.com` |

Read the current targets with `heroku domains -a movie-compass`; they are
per-app and per-domain, not guessable, and they change if a domain is removed
and re-added.

**Leave both records DNS-only — the grey cloud, not the orange one.** Proxied,
Cloudflare answers the ACME challenge with its own certificate and Heroku's
Automatic Certificate Management can never validate, which presents as a
domain that resolves and then fails its TLS handshake. Once
`heroku certs:auto` reports the cert as issued, proxying can be turned on with
Cloudflare's SSL mode set to Full (strict) — but it buys little here and is one
more thing between a visitor and the dyno.

```bash
heroku certs:auto -a movie-compass      # issued? failing? what on
heroku domains -a movie-compass         # the targets, and whether DNS matches
```

## Deploying

A push to `main` runs the tests and pushes to Heroku — see
[`.github/workflows/heroku.yml`](../.github/workflows/heroku.yml). It needs two
things set on the repository, once:

```bash
gh variable set HEROKU_APP --body movie-compass
gh secret set HEROKU_API_KEY --body "$(heroku authorizations:create --short)"
```

`heroku authorizations:create` rather than `heroku auth:token`: the second is
your own session token and expires, which turns into a deploy that stops working
a month later for no visible reason.

Every release runs `atlas init` before the new dyno takes traffic (see
[`Procfile`](../Procfile)). A migration that fails aborts the release and the
old dyno keeps serving.

## Sending up a new corpus

Ingest and sweep locally, then:

```bash
atlas corpus-push movie-compass
```

It reads the app's `DATABASE_URL` through `heroku config:get`, so no credential
is typed or pasted. Everything that is not a user table is replaced, inside one
transaction — the site is never serving half an atlas, and a push that dies
half-way leaves it as it was.

User rows are counted before and after and the push is refused if any of them
moved. One thing it will not do is delete a film somebody has rated or
shortlisted: those are named in the output and kept. To remove one for real,
including the ratings that point at it:

```bash
heroku run atlas remove-film some-film-2019 --yes -a movie-compass
```

## Looking at it

```bash
heroku logs --tail -a movie-compass
heroku pg:psql -a movie-compass
heroku pg:info -a movie-compass
heroku releases -a movie-compass
heroku rollback -a movie-compass          # back one release, dyno and all
```

`/internal` is the pipeline page — corpus counts, dimension coverage, what has
been scored. It is the same page that used to be at `/` on the runner; the
product lives at `/` now.

## Pulling production down to your machine

```bash
heroku pg:backups:capture -a movie-compass
heroku pg:backups:download -a movie-compass -o /tmp/atlas.dump
dropdb --if-exists moral_atlas_prod && createdb moral_atlas_prod
pg_restore --no-owner --no-privileges -d moral_atlas_prod /tmp/atlas.dump
ATLAS_DB=postgresql:///moral_atlas_prod atlas status
```

`ATLAS_DB` and `DATABASE_URL` are the same setting; every `atlas` command
honours either, so a one-off read of production never means editing a config
file.

## What it costs

The smallest useful pair. `essential-0` Postgres and one `basic` dyno is about
US$12/month between them; both scale up in place without a migration.

The database limits worth knowing: 20 connections and 1GB. The corpus is around
50MB with 674 films, so the size is not the constraint — the connection count
is, which is why `ATLAS_DB_POOL_SIZE` exists and defaults to 5. A second dyno
type, a `heroku run` session and a `corpus-push` all draw from the same twenty.

## Things worth knowing before you rely on them

**The dyno's filesystem is temporary.** Nothing may be written to disk and
expected to survive a restart, and dynos restart daily. Everything durable is in
Postgres. The one exception is the front-end build, which is baked into the slug
at deploy time and is read-only.

**Migrations run in the release phase, not on request.** `init_db` runs once per
process and looks before it alters — an `ALTER TABLE ... ADD COLUMN IF NOT
EXISTS` takes an exclusive lock even when the column is already there, and
running thirty of them per request queues the whole site behind whichever client
last died mid-transaction. That is not hypothetical; it is what the first real
request against Postgres did.

**The atlas document is built once, not per process.** `/api/atlas` runs a
thousand-permutation null test — 3 seconds of arithmetic on a laptop, forty on a
dyno, against a router that hangs up at 30. It is kept in `atlas_documents`,
keyed on the store's own counts, so a restart reads it rather than making it
again; a sweep changes the counts and the next request rebuilds. On top of that
it is built in a background thread at startup (`ATLAS_WARM_CACHE=1`), which
covers the one case the table cannot: the first boot after a corpus push. Look
for `atlas document built and cached` in the log.

**A killed client can hold a lock.** If the site stops answering and nothing
looks wrong, this is the first thing to check:

```sql
SELECT pid, state, wait_event_type, left(query, 60), xact_start
FROM pg_stat_activity WHERE datname = current_database() ORDER BY xact_start;
```

An `idle in transaction` row with an old `xact_start` is the culprit;
`SELECT pg_terminate_backend(pid)` clears it.
