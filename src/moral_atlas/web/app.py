"""Application assembly only; feature endpoints live in `web.routes`."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import access, atlas, landing, onboarding, profile, sessions, shortlist, test

app = FastAPI(title="Moral Atlas API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(landing.router)
app.include_router(access.router)
app.include_router(onboarding.router)
app.include_router(test.router)
app.include_router(profile.router)
app.include_router(sessions.router)
app.include_router(shortlist.router)
app.include_router(atlas.router)
