from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..deps import current_session
from ..shortlist_service import ranked_shortlist, session_member_ids
from ..store import Session, next_shortlist_film, save_shortlist_reaction, shortlist_selection

router = APIRouter(prefix="/api/shortlist", tags=["shortlist"])
DECK_SIZE = 6

class Reaction(BaseModel):
    share_token: str
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


@router.get("/next")
def next_film(share_token: str, session: Annotated[Session, Depends(current_session)]) -> dict[str, object]:
    result = next_shortlist_film(share_token, session.user.id)
    if result is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return result


@router.get("/selection")
def selection(share_token: str, session: Annotated[Session, Depends(current_session)]) -> dict[str, object]:
    result = shortlist_selection(share_token, session.user.id)
    if result is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return result


@router.post("/reactions")
def react(request: Reaction, session: Annotated[Session, Depends(current_session)]) -> dict[str, object]:
    if request.reaction not in {"yes", "no"}:
        raise HTTPException(status_code=422, detail="Unknown shortlist reaction.")
    result = save_shortlist_reaction(request.share_token, session.user.id, request.film_id, request.reaction)
    if result is None:
        raise HTTPException(status_code=409, detail="This film is no longer available in the deck.")
    return result
