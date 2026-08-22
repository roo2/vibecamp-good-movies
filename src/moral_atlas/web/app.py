"""HTTP routes for the mock frontend integration."""
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from .mock_data import COMPASS_PROFILE, ONBOARDING_FILMS, QUESTIONS
from .mock_store import MockStore, Session
from .schemas import (
    AccessRequest,
    AccessResponse,
    MovieRating,
    MovieRatingRequest,
    TestResult,
    TestResultRequest,
)

app = FastAPI(title="Moral Atlas API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
store = MockStore()

VALID_ANSWERS = {
    question["id"]: {choice["id"] for choice in question["choices"]} | {"neither"}
    for question in QUESTIONS
}
VALID_MOVIE_REACTIONS = {"not_for_me", "havent_seen", "loved_it"}


def current_session(x_session_token: Annotated[str | None, Header()] = None) -> Session:
    session = store.get_session(x_session_token or "")
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="A valid session is required.")
    return session


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/access", response_model=AccessResponse, status_code=status.HTTP_201_CREATED)
def create_access(request: AccessRequest) -> AccessResponse:
    session = store.create_session(request.name)
    return AccessResponse(token=session.token, user=session.user)


@app.get("/api/test/questions")
def get_test_questions() -> dict[str, list[dict[str, object]]]:
    return {"questions": QUESTIONS}


@app.get("/api/onboarding/films")
def get_onboarding_films() -> dict[str, list[dict[str, object]]]:
    return {"films": ONBOARDING_FILMS}


@app.post("/api/onboarding/ratings", response_model=MovieRating, status_code=status.HTTP_201_CREATED)
def save_movie_rating(
    request: MovieRatingRequest,
    session: Annotated[Session, Depends(current_session)],
) -> MovieRating:
    if request.reaction not in VALID_MOVIE_REACTIONS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown movie reaction.")
    if request.film_id not in {film["id"] for film in ONBOARDING_FILMS}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown film.")
    return store.save_movie_rating(session.user.id, request.film_id, request.reaction)


@app.post("/api/test/results", response_model=TestResult, status_code=status.HTTP_201_CREATED)
def save_test_result(
    request: TestResultRequest,
    session: Annotated[Session, Depends(current_session)],
) -> TestResult:
    for question_id, choice_id in request.answers.items():
        if choice_id not in VALID_ANSWERS.get(question_id, set()):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown question or answer.")
    return store.save_result(session.user.id, request.answers)


@app.get("/api/test/results", response_model=list[TestResult])
def get_test_results(session: Annotated[Session, Depends(current_session)]) -> list[TestResult]:
    return store.list_results(session.user.id)


@app.get("/api/profile/compass")
def get_compass_profile() -> dict[str, object]:
    return COMPASS_PROFILE
