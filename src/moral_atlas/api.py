"""Development web API, intentionally independent of the atlas data store."""
from .web.app import app

__all__ = ["app"]
