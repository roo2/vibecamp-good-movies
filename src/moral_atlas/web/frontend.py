"""Serving the built interface from the same process as the API.

These were two things once: a CDN served the SPA out of a bucket, and only
`/api/*` reached the box. That split is why the deploy had a whole job for
publishing the site and another for updating the server, and why the two could
end up on different commits — which happened, and looks from the outside like
the API having a bad day.

One dyno serves both now. The interface is built during the Heroku build (see
the root `package.json`) and read off disk from here, so a release is one
artefact and the front end cannot be a commit behind the back end.

Only switched on when `ATLAS_SERVE_FRONTEND` says so, because a developer
running `uvicorn` wants Vite on 5173 and the pipeline landing page at `/`.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

# Everything the API answers. A request under one of these that reached the
# catch-all is a 404 for a route that does not exist, and must say so — handing
# back index.html would turn every typo'd endpoint into a 200 with a page in it,
# which a browser renders and a client cannot parse.
API_PREFIXES = ("/api", "/health", "/docs", "/redoc", "/openapi.json")

# Vite writes content-hashed filenames into assets/, so those can be cached for
# a year: a changed file has a changed name. index.html must not be cached at
# all — it is the file that names the current hashes, and a stale one points a
# browser at assets that no longer exist.
IMMUTABLE = "public, max-age=31536000, immutable"
NO_STORE = "no-store"

MISSING_BUILD = """<!doctype html><meta charset="utf-8">
<title>Interface not built</title>
<body style="font:16px/1.6 system-ui;max-width:34rem;margin:15vh auto;padding:0 1.5rem">
<h1 style="font-size:1.3rem">The interface is not built</h1>
<p>This process is set to serve the front end
(<code>ATLAS_SERVE_FRONTEND</code>), but there is no build at
<code>{path}</code>.</p>
<p>Run <code>npm --prefix src/frontend ci &amp;&amp; npm --prefix src/frontend run
build</code>, or unset the variable to get the pipeline page here instead.</p>
<p>The API itself is unaffected — <a href="/api/health">/api/health</a>.</p>
</body>"""


class _Cached(StaticFiles):
    """StaticFiles with a Cache-Control header on it.

    Starlette sets ETag and Last-Modified and stops there, which means every
    asset costs a conditional request on every page load — on a phone, over a
    slow link, that is the load time. The names are content-hashed, so there is
    nothing to revalidate.
    """

    def __init__(self, *args, cache: str, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.cache = cache

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = self.cache
        return response


def mount(app: FastAPI, dist: Path) -> bool:
    """Serve `dist` from `app`. Call LAST: the fallback matches every path.

    Returns whether a build was found. A missing one is not fatal — the API
    keeps answering and `/` explains itself — because the alternative is a dyno
    that crashes on boot over a front-end build, taking the API with it.
    """
    index = dist / "index.html"
    if not index.exists():
        @app.get("/", response_class=HTMLResponse, include_in_schema=False)
        def _no_build() -> HTMLResponse:
            return HTMLResponse(MISSING_BUILD.format(path=dist), status_code=503)
        return False

    for folder, cache in (("assets", IMMUTABLE), ("data", NO_STORE)):
        path = dist / folder
        if path.is_dir():
            # data/ is the atlas snapshot, rebuilt by `atlas dataset` and
            # replaced on every deploy under the SAME name — so unlike the
            # hashed assets it must not be cached, or a returning browser draws
            # the last corpus over the new one.
            app.mount(f"/{folder}",
                      _Cached(directory=path, html=False, cache=cache),
                      name=folder)

    def _index() -> FileResponse:
        return FileResponse(index, headers={"Cache-Control": NO_STORE})

    @app.get("/", include_in_schema=False)
    def root() -> FileResponse:
        return _index()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        """Any other path is a route inside the interface — hand it the app.

        Except a file that really is on disk (favicon, manifest, an image), and
        except anything under an API prefix, which is a 404 and has to look
        like one.
        """
        if any(f"/{path}".startswith(prefix) for prefix in API_PREFIXES):
            raise HTTPException(status_code=404, detail="Not Found")

        candidate = (dist / path).resolve()
        if dist.resolve() in candidate.parents and candidate.is_file():
            cache = IMMUTABLE if path.startswith("assets/") else NO_STORE
            return FileResponse(candidate, headers={"Cache-Control": cache})
        return _index()

    return True
