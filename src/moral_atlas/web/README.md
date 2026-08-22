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

- `POST /api/access` — creates a SQLite-backed name-only user and session.
- `GET /api/access/me` — returns the current persisted user.
- `GET /api/test/questions` — serves mock test questions.
- `POST /api/test/results` — captures answers using `X-Session-Token`.
- `GET /api/test/results` — returns the active user's captured results.
- `GET /api/profile/compass` — serves a mock compass profile.

Users, sessions, movie reactions, and test results are stored in SQLite. The
user record is intentionally limited to `id` and `name`; an SSO identity can be
added later without altering the existing response tables.

Movie cards are read from the existing SQLite `films` table. Seed the curated
40-film deck without any external calls before using the onboarding API:

```powershell
atlas seed-films
```
