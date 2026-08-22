"""In-memory development store.

This is deliberately the only persistence seam the web routes use. Replacing
it with a real user/session store should not require changing the API contract
or frontend services.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from secrets import token_urlsafe
from threading import Lock
from uuid import uuid4

from .schemas import MovieRating, TestResult, User


@dataclass(frozen=True)
class Session:
    token: str
    user: User


class MockStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._sessions: dict[str, Session] = {}
        self._results: list[TestResult] = []
        self._movie_ratings: list[MovieRating] = []

    def create_session(self, name: str) -> Session:
        user = User(id=f"usr_{uuid4().hex[:12]}", name=name.strip())
        session = Session(token=token_urlsafe(32), user=user)
        with self._lock:
            self._sessions[session.token] = session
        return session

    def get_session(self, token: str) -> Session | None:
        with self._lock:
            return self._sessions.get(token)

    def save_result(self, user_id: str, answers: dict[str, str]) -> TestResult:
        result = TestResult(
            id=f"result_{uuid4().hex[:12]}",
            user_id=user_id,
            answers=answers,
            answered_count=len(answers),
            submitted_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._results.append(result)
        return result

    def list_results(self, user_id: str) -> list[TestResult]:
        with self._lock:
            return [result for result in self._results if result.user_id == user_id]

    def save_movie_rating(self, user_id: str, film_id: str, reaction: str) -> MovieRating:
        rating = MovieRating(
            id=f"rating_{uuid4().hex[:12]}",
            user_id=user_id,
            film_id=film_id,
            reaction=reaction,
            submitted_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._movie_ratings.append(rating)
        return rating
