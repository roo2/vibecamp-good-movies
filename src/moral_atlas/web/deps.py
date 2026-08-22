"""Shared API dependencies."""
from typing import Annotated

from fastapi import Header, HTTPException, status

from .mock_store import Session, store


def current_session(x_session_token: Annotated[str | None, Header()] = None) -> Session:
    session = store.get_session(x_session_token or "")
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="A valid session is required.")
    return session
