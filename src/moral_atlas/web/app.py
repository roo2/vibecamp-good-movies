"""Application assembly only; feature endpoints live in `web.routes`."""
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..config import settings
from . import frontend
from .routes import access, atlas, factors, landing, onboarding, profile, sessions, shortlist, test

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the expensive documents before anyone asks for them.

    In a thread, and a daemon one: the dyno has sixty seconds to bind its port
    and this once took most of that on the hardware it runs on, so it must not
    be in the way of the bind — and a restart must not wait for it either.

    ONE thread for both, in sequence. Two would race for the single CPU they
    share and each finish later than if they had queued. Since both documents
    are kept in the store now, this only does real work after a corpus push;
    every other boot reads two rows.
    """
    def build() -> None:
        atlas.warm()
        factors.warm()

    if settings().warm_on_start:
        threading.Thread(target=build, name="warm-documents", daemon=True).start()
    yield


app = FastAPI(title="Moral Atlas API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# The same answer under /api. On AWS that was the only prefix that reached this
# application at all — CloudFront sent /api/* to the runner and everything else
# to the bucket, so a request for /health there was answered by S3 with a 404
# and told you nothing about whether the API was up. On Heroku both work; the
# prefixed one stays because every client and every check already calls it.
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
app.include_router(factors.router)

# Last, and it has to be last: the interface answers on every path the API did
# not claim, so anything mounted after it would never be reached.
if settings().serve_frontend:
    frontend.mount(app, settings().frontend_dist)
