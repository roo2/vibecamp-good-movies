from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import current_session
from ..film_service import film_exists, random_onboarding_films
from ..mock_store import Session, store
from ..schemas import MovieRating, MovieRatingRequest

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])
VALID_MOVIE_REACTIONS = {"not_for_me", "havent_seen", "loved_it"}


@router.get("/films")
def get_onboarding_films() -> dict[str, list[dict[str, object]]]:
    films = random_onboarding_films(limit=10)
    if not films:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No films are seeded. Run `atlas seed-films` first.",
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
    return store.save_movie_rating(session.user.id, request.film_id, request.reaction)
