# Web API

This API shares the SQLite file with the atlas, but keeps its product-facing
tables and route modules separate from the research pipeline.

Run it from the repository root:

```powershell
python -m uvicorn moral_atlas.api:app --reload
```

The React app proxies `/api` calls to `http://127.0.0.1:8000` during `npm run
dev`.

Endpoints:

- `GET /` — the landing page: two doors (the React app and Datasette over the
  store) plus a live read of what the pipeline has produced so far. It renders
  on an empty store too, so a fresh clone gets told what to run rather than a
  500. Point the doors somewhere else with `ATLAS_FRONTEND_URL`,
  `ATLAS_DATASETTE_URL` and `ATLAS_SQLITEWEB_URL`.
- `POST /api/access` — creates a SQLite-backed name-only user and session.
- `GET /api/access/me` — returns the current persisted user.
- `GET /api/test/questions` — serves mock test questions.
- `POST /api/test/results` — captures answers using `X-Session-Token`.
- `GET /api/test/results` — returns the active user's captured results.
- `GET /api/profile/moral` — the caller's score on each derived moral axis, read
  from the films they reacted to and the story pairs they chose between.
- `GET /api/atlas` — the whole dataset the explorer at `#/atlas` draws: corpus
  totals, the derived axes, every film's skeleton and its position on each axis.
  Rebuilt when the store's mtime changes, so a pipeline run shows up on reload.
  The published demo does not use this endpoint — that site is static and reads
  `/api/atlas.json`, which `atlas dataset` writes into `src/frontend/public/`.
- `GET /api/atlas/films/{film_id}` — one film's source text in full: plot,
  themes, reception and dialogue. Separate from the index because it is ~80KB
  per film and only wanted for the film someone opened. The static site serves
  the same documents from `/api/atlas/<film_id>.json`.

Users, sessions, movie reactions, and test results are stored in SQLite. The
user record is intentionally limited to `id` and `name`; an SSO identity can be
added later without altering the existing response tables.

Movie cards are read from the existing SQLite `films` table. Seed the curated
40-film deck without any external calls before using the onboarding API:

```powershell
atlas seed-films
```

The explorer at `#/atlas` is outside the sign-in guard: it reads a published
file, holds nothing about anyone, and is the thing to show someone before they
have a reason to sign in.
