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

Users, sessions, movie reactions, and test results are stored in SQLite. The
user record is intentionally limited to `id` and `name`; an SSO identity can be
added later without altering the existing response tables.

Movie cards are read from the existing SQLite `films` table. Seed the curated
40-film deck without any external calls before using the onboarding API:

```powershell
atlas seed-films
```
