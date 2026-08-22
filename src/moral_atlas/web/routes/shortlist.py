from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ... import db
from ..deps import current_session
from ..store import Session, save_shortlist_reaction

router = APIRouter(prefix="/api/shortlist", tags=["shortlist"])
FILM_IDS = ["casablanca-1942", "spirited-away-2001", "arrival-2016", "do-the-right-thing-1989"]

class Reaction(BaseModel):
    film_id: str
    reaction: str

@router.get("/films")
def films(_: Annotated[Session, Depends(current_session)]) -> dict[str, list[dict[str, object]]]:
    rows = [db.get_film(film_id) for film_id in FILM_IDS]
    return {"films": [{"id": f["film_id"], "title": f["title"], "year": f.get("year"), "description": f.get("description"), "artwork_url": f.get("artwork_url")} for f in rows if f]}

@router.post("/reactions")
def react(request: Reaction, session: Annotated[Session, Depends(current_session)]) -> dict[str, str]:
    if request.film_id not in FILM_IDS or request.reaction not in {"yes", "no"}:
        raise HTTPException(status_code=422, detail="Unknown shortlist reaction.")
    save_shortlist_reaction(session.user.id, request.film_id, request.reaction)
    return {"status": "saved"}
