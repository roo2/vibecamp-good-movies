"""The dataset the explorer reads, served live.

The published demo does not use this: that site is static, and the interface
reads a file `atlas dataset` wrote into the bundle. This endpoint is for the
machine that has the store — locally, and on the runner — where re-reading on
each request means a pipeline run shows up on reload rather than on rebuild.

Building the document costs a handful of full-table reads, so the response is
cached against the store's mtime: unchanged file, cached document.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from ...analysis import dataset as dataset_mod
from ...config import settings

router = APIRouter(prefix="/api", tags=["atlas"])

_cache: dict[str, Any] = {"key": None, "payload": None}


@router.get("/atlas")
def get_atlas(dim_version: str = "d1", bank_version: str = "b1") -> dict[str, Any]:
    """Everything the dataset explorer draws, from the current store."""
    db_path = settings().db_path
    if not db_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No store yet — run `atlas init` and ingest before reading the dataset.",
        )

    key = (db_path.stat().st_mtime_ns, db_path.stat().st_size, dim_version, bank_version)
    if _cache["key"] != key:
        _cache["payload"] = dataset_mod.build(dim_version, bank_version)
        _cache["key"] = key
    return _cache["payload"]


@router.get("/atlas/films/{film_id}")
def get_film_evidence(film_id: str) -> dict[str, Any]:
    """One film's source text — what every claim about it was read from.

    Its own endpoint rather than part of the index because it is large and only
    wanted for the film somebody opened. Not cached: it is one indexed read,
    and it is served far less often than the index.
    """
    document = dataset_mod.film_evidence(film_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No film {film_id!r}.")
    return document
