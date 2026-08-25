from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import current_session
from ..film_service import film_exists
from ..store import (Session, direct_session_films, extend_session_deck,
                     film_is_in_direct_session_deck, list_movie_ratings,
                     save_movie_rating as persist_movie_rating)
from ..schemas import MovieRating, MovieRatingRequest

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])
VALID_MOVIE_REACTIONS = {"not_for_me", "neutral", "havent_seen", "loved_it"}


@router.get("/films")
def get_onboarding_films(
    share_token: str,
    session: Annotated[Session, Depends(current_session)],
) -> dict[str, list[dict[str, object]]]:
    films = direct_session_films(share_token, session.user.id)
    if not films:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shared session deck not found.",
        )
    return {"films": films}


@router.post("/ratings", response_model=MovieRating, status_code=status.HTTP_201_CREATED)
def save_movie_rating(
    request: MovieRatingRequest,
    session: Annotated[Session, Depends(current_session)],
) -> MovieRating:
    if request.reaction not in VALID_MOVIE_REACTIONS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown movie reaction.")
    if not film_exists(request.film_id):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown film.")
    if not request.session_share_token or not film_is_in_direct_session_deck(request.session_share_token, session.user.id, request.film_id):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Film is not in this session's direct deck.")
    return persist_movie_rating(session.user.id, request.film_id, request.reaction)


@router.get("/ratings", response_model=list[MovieRating])
def get_movie_ratings(session: Annotated[Session, Depends(current_session)]) -> list[MovieRating]:
    return list_movie_ratings(session.user.id)


@router.post("/films/more")
def deal_more_films(
    share_token: str,
    session: Annotated[Session, Depends(current_session)],
) -> dict[str, list[dict[str, object]]]:
    """Deal more films to somebody who answered everything and said nothing.

    "Haven't seen it" is an honest answer that carries no moral information.
    Give it twenty times and the deck is exhausted while the person is still
    unread — so rather than hand them an empty compass, deal ten more.
    """
    films = extend_session_deck(share_token, session.user.id)
    if not films:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No more films are available for this session.")
    return {"films": films}
