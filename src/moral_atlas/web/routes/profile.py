from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import current_session
from ..profile_service import moral_profile
from ..schemas import MoralProfile
from ..store import Session, get_group_session_status

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("/moral", response_model=MoralProfile)
def get_moral_profile(
    session: Annotated[Session, Depends(current_session)],
) -> MoralProfile:
    """The user's score on each derived moral axis, from everything they have told us."""
    try:
        return moral_profile(session.user.id)
    except LookupError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error),
        ) from error


@router.get("/moral/session/{share_token}")
def get_session_moral_profiles(
    share_token: str,
    session: Annotated[Session, Depends(current_session)],
) -> dict[str, list[dict[str, Any]]]:
    """Everyone else in this session, read against the same axes.

    The point of a shared session is the comparison — two people find out where
    they agree by seeing both readings on one axis, not by taking turns looking
    at their own. So the compass needs the other members, and this is the only
    place one person's profile is visible to somebody else.

    Membership is the authorisation, and it is checked rather than assumed:
    `get_group_session_status` returns None unless the caller is in the session,
    so a share token on its own buys nothing.
    """
    status_ = get_group_session_status(share_token, session.user.id)
    if status_ is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Shared session not found.")

    companions = []
    for member in status_.members:
        if member.user.id == session.user.id:
            continue
        try:
            profile = moral_profile(member.user.id)
        except LookupError:
            # Read on nothing yet — they have joined but not answered. Skipped
            # rather than sent as zeroes, which would draw them at the centre of
            # every axis as though they had weighed each one and declined.
            continue
        companions.append({
            "user_id": member.user.id,
            "name": member.user.name,
            "ready": member.completed_at is not None,
            "profile": profile,
        })
    return {"companions": companions}
