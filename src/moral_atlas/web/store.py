"""SQLite-backed persistence for the name-only web experience."""
from __future__ import annotations

import json
from dataclasses import dataclass
from secrets import token_urlsafe
from uuid import uuid4

from .. import db
from .schemas import MovieRating, TestResult, User


@dataclass(frozen=True)
class Session:
    token: str
    user: User


def _ensure_db() -> None:
    db.init_db()


def create_session(name: str) -> Session:
    _ensure_db()
    user = User(id=f"usr_{uuid4().hex[:12]}", name=name.strip())
    token = token_urlsafe(32)
    created_at = db.now()
    with db.connect() as con:
        con.execute(
            "INSERT INTO users (user_id, name, created_at) VALUES (?,?,?)",
            [user.id, user.name, created_at],
        )
        con.execute(
            "INSERT INTO user_sessions (token, user_id, created_at) VALUES (?,?,?)",
            [token, user.id, created_at],
        )
    return Session(token=token, user=user)


def get_session(token: str) -> Session | None:
    _ensure_db()
    with db.connect(read_only=True) as con:
        row = con.execute(
            "SELECT s.token, u.user_id, u.name FROM user_sessions s "
            "JOIN users u ON u.user_id=s.user_id WHERE s.token=?",
            [token],
        ).fetchone()
    if row is None:
        return None
    return Session(token=row["token"], user=User(id=row["user_id"], name=row["name"]))


def save_test_result(user_id: str, answers: dict[str, str]) -> TestResult:
    _ensure_db()
    result = TestResult(
        id=f"result_{uuid4().hex[:12]}",
        user_id=user_id,
        answers=answers,
        answered_count=len(answers),
        submitted_at=db.now(),
    )
    with db.connect() as con:
        con.execute(
            "INSERT INTO test_results (result_id, user_id, answers, answered_count, submitted_at) "
            "VALUES (?,?,?,?,?)",
            [result.id, result.user_id, json.dumps(result.answers), result.answered_count,
             result.submitted_at.isoformat()],
        )
    return result


def list_test_results(user_id: str) -> list[TestResult]:
    _ensure_db()
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT result_id, user_id, answers, answered_count, submitted_at "
            "FROM test_results WHERE user_id=? ORDER BY submitted_at DESC",
            [user_id],
        ).fetchall()
    return [TestResult(
        id=row["result_id"], user_id=row["user_id"], answers=json.loads(row["answers"]),
        answered_count=row["answered_count"], submitted_at=row["submitted_at"],
    ) for row in rows]


def save_movie_rating(user_id: str, film_id: str, reaction: str) -> MovieRating:
    _ensure_db()
    rating = MovieRating(
        id=f"rating_{uuid4().hex[:12]}", user_id=user_id, film_id=film_id,
        reaction=reaction, submitted_at=db.now(),
    )
    with db.connect() as con:
        con.execute(
            "INSERT INTO movie_ratings (rating_id, user_id, film_id, reaction, submitted_at) "
            "VALUES (?,?,?,?,?)",
            [rating.id, rating.user_id, rating.film_id, rating.reaction,
             rating.submitted_at.isoformat()],
        )
    return rating


def list_movie_ratings(user_id: str) -> list[MovieRating]:
    _ensure_db()
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT rating_id, user_id, film_id, reaction, submitted_at "
            "FROM movie_ratings WHERE user_id=? ORDER BY submitted_at DESC",
            [user_id],
        ).fetchall()
    return [MovieRating(
        id=row["rating_id"], user_id=row["user_id"], film_id=row["film_id"],
        reaction=row["reaction"], submitted_at=row["submitted_at"],
    ) for row in rows]
