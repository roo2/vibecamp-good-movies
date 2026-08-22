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


# The same answer under /api, which is the only prefix that reaches this
# application in the published environment: CloudFront sends /api/* to the
# runner and everything else to the bucket, so a request for /health there is
# answered by S3 with a 404 and tells you nothing about whether the API is up.
@app.get("/api/health")
def api_health() -> dict[str, str]:
    return {"status": "ok", "version": app.version}


app.include_router(landing.router)
app.include_router(access.router)
app.include_router(onboarding.router)
app.include_router(test.router)
app.include_router(profile.router)
app.include_router(sessions.router)
app.include_router(shortlist.router)
app.include_router(atlas.router)
