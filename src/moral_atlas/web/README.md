# Web API (mock integration)

This API is deliberately separate from the atlas data store. It provides a
stable frontend boundary while the research database and scoring model change.

Run it from the repository root:

```powershell
python -m uvicorn moral_atlas.api:app --reload
```

The React app proxies `/api` calls to `http://127.0.0.1:8000` during `npm run
dev`.

Endpoints:

- `POST /api/access` — creates a name-only temporary session.
- `GET /api/test/questions` — serves mock test questions.
- `POST /api/test/results` — captures answers using `X-Session-Token`.
- `GET /api/test/results` — returns the active user's captured results.
- `GET /api/profile/compass` — serves a mock compass profile.

The session and answers are stored in memory, so restarting the API clears
them. Replace `mock_store.py` with a persistent user/session store later;
routes and the frontend contract do not need to change.

Movie cards are read from the existing SQLite `films` table. Seed the curated
40-film deck without any external calls before using the onboarding API:

```powershell
atlas seed-films
```
