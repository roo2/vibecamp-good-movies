"""Shared API dependencies."""
from typing import Annotated

from fastapi import Header, HTTPException, status

from .store import Session, get_session


def current_session(x_session_token: Annotated[str | None, Header()] = None) -> Session:
    session = get_session(x_session_token or "")
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="A valid session is required.")
    return session
