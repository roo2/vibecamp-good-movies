from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ... import db
from ..deps import current_session
from ..shortlist_service import ranked_shortlist, session_member_ids
from ..store import Session, save_shortlist_reaction

router = APIRouter(prefix="/api/shortlist", tags=["shortlist"])
DECK_SIZE = 6


class Reaction(BaseModel):
    film_id: str
    reaction: str


@router.get("/films")
def films(
    session: Annotated[Session, Depends(current_session)],
    share_token: str | None = None,
) -> dict[str, list[dict[str, object]]]:
    """Tonight's deck, ranked by how well each film fits everyone watching.

    Without a share token this still works, ranked for the caller alone — a
    person looking at their own list before anyone else has joined should see
    something, not an error.
    """
    members = session_member_ids(share_token, session.user.id) if share_token else None
    if share_token and members is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shared session not found.",
        )
    return {"films": ranked_shortlist(members or [session.user.id], DECK_SIZE)}


@router.post("/reactions")
def react(
    request: Reaction,
    session: Annotated[Session, Depends(current_session)],
) -> dict[str, str]:
    if request.reaction not in {"yes", "no"} or db.get_film(request.film_id) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unknown shortlist reaction.",
        )
    save_shortlist_reaction(session.user.id, request.film_id, request.reaction)
    return {"status": "saved"}
