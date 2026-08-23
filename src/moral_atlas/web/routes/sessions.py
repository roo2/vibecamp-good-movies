"""Shared group-session endpoints; individual answers remain user-owned."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import current_session
from ..schemas import GroupSession, GroupSessionStatus
from ..store import (Session, begin_waiting_for_results, continue_group_session,
                     create_group_session, get_group_session_status, join_group_session,
                     mark_session_member_unready, start_group_session)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", response_model=GroupSession, status_code=status.HTTP_201_CREATED)
def create(session: Annotated[Session, Depends(current_session)]) -> GroupSession:
    try:
        return create_group_session(session.user.id)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/{share_token}/join", response_model=GroupSession)
def join(share_token: str, session: Annotated[Session, Depends(current_session)]) -> GroupSession:
    group_session = join_group_session(share_token, session.user.id)
    if group_session is None:
        raise HTTPException(status_code=404, detail="This session is unavailable or has already started.")
    return group_session


@router.get("/{share_token}", response_model=GroupSessionStatus)
def get_status(share_token: str, session: Annotated[Session, Depends(current_session)]) -> GroupSessionStatus:
    group_session = get_group_session_status(share_token, session.user.id)
    if group_session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return group_session


@router.post("/{share_token}/start", response_model=GroupSession)
def start(share_token: str, session: Annotated[Session, Depends(current_session)]) -> GroupSession:
    group_session = start_group_session(share_token, session.user.id)
    if group_session is None:
        raise HTTPException(status_code=403, detail="Only the host can start this session.")
    return group_session


@router.post("/{share_token}/wait", response_model=GroupSession)
def wait(share_token: str, session: Annotated[Session, Depends(current_session)]) -> GroupSession:
    group_session = begin_waiting_for_results(share_token, session.user.id)
    if group_session is None:
        raise HTTPException(status_code=403, detail="Only the host can begin the results wait.")
    return group_session


@router.post("/{share_token}/continue", response_model=GroupSession)
def continue_without_members(share_token: str, session: Annotated[Session, Depends(current_session)]) -> GroupSession:
    group_session = continue_group_session(share_token, session.user.id)
    if group_session is None:
        raise HTTPException(status_code=403, detail="The host can continue after the ten-minute wait.")
    return group_session


@router.post("/{share_token}/unready", response_model=GroupSession)
def unready(share_token: str, session: Annotated[Session, Depends(current_session)]) -> GroupSession:
    group_session = mark_session_member_unready(share_token, session.user.id)
    if group_session is None:
        raise HTTPException(status_code=409, detail="This session can no longer be changed.")
    return group_session
