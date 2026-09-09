# Heroku process types.
#
# release runs on every deploy, before the new web dyno takes traffic, and a
# non-zero exit aborts the release — which is exactly what you want from a
# migration: a schema change that fails leaves the old release serving.
#
# `atlas init` is idempotent. It creates missing tables, adds missing columns,
# and re-applies the curated seed descriptions; on a release that changed
# neither it does nothing and says so.
release: atlas init
web: uvicorn moral_atlas.web.app:app --host 0.0.0.0 --port ${PORT:-8000}
