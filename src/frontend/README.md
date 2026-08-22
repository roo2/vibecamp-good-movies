# Moral Atlas frontend

Standalone React SPA for the Moral Atlas interface. It currently renders a small hello-world screen and reads mock data from `../design/fixtures/session.json`; no backend is required.

## Run locally

```bash
cd src/frontend
npm install
npm run dev
```

Vite prints the local URL (normally `http://localhost:5173`).

## Commands

```bash
npm run build    # production build to src/frontend/dist
npm run preview  # serve the production build locally
```

When the API is ready, replace the fixture import in `src/App.jsx` with a client that returns the payload described in `design/INTERFACE-CONTRACT.md`.
