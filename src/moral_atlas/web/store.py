"""SQLite-backed persistence for the name-only web experience."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from secrets import token_urlsafe
from uuid import uuid4

from .. import db
from .film_service import build_session_deck, film_card
from .schemas import GroupSession, GroupSessionStatus, MovieRating, SessionMember, TestResult, User

WAIT_TO_CONTINUE_SECONDS = 10 * 60


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


def save_test_result(user_id: str, answers: dict[str, str], session_share_token: str | None = None) -> TestResult:
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
        if session_share_token:
            con.execute(
                "UPDATE session_members SET completed_at=? WHERE user_id=? AND completed_at IS NULL "
                "AND session_id=(SELECT session_id FROM group_sessions WHERE share_token=? AND status='in_progress')",
                [result.submitted_at.isoformat(), user_id, session_share_token],
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


def create_group_session(host_user_id: str) -> GroupSession:
    _ensure_db()
    deck = build_session_deck()
    if not deck["direct"]:
        raise ValueError("At least 15 seeded films are required to start a shared session.")
    group_session = GroupSession(
        id=f"group_{uuid4().hex[:12]}", share_token=token_urlsafe(12), host_user_id=host_user_id,
        status="lobby", created_at=db.now(),
    )
    with db.connect() as con:
        con.execute(
            "INSERT INTO group_sessions (session_id, share_token, host_user_id, status, created_at, deck_json) VALUES (?,?,?,?,?,?)",
            [group_session.id, group_session.share_token, host_user_id, group_session.status, group_session.created_at.isoformat(), json.dumps(deck)],
        )
        con.execute(
            "INSERT INTO session_members (session_id, user_id, joined_at) VALUES (?,?,?)",
            [group_session.id, host_user_id, group_session.created_at.isoformat()],
        )
    return group_session


def join_group_session(share_token: str, user_id: str) -> GroupSession | None:
    _ensure_db()
    with db.connect() as con:
        row = con.execute("SELECT * FROM group_sessions WHERE share_token=?", [share_token]).fetchone()
        if row is None or row["status"] != "lobby":
            return None
        con.execute(
            "INSERT OR IGNORE INTO session_members (session_id, user_id, joined_at) VALUES (?,?,?)",
            [row["session_id"], user_id, db.now()],
        )
    return _group_session_from_row(row)


def get_group_session_status(share_token: str, user_id: str) -> GroupSessionStatus | None:
    _ensure_db()
    with db.connect(read_only=True) as con:
        row = con.execute(
            "SELECT s.* FROM group_sessions s JOIN session_members m ON m.session_id=s.session_id "
            "WHERE s.share_token=? AND m.user_id=?", [share_token, user_id],
        ).fetchone()
        if row is None:
            return None
        member_rows = con.execute(
            "SELECT u.user_id, u.name, m.joined_at, m.completed_at FROM session_members m "
            "JOIN users u ON u.user_id=m.user_id WHERE m.session_id=? ORDER BY m.joined_at", [row["session_id"]],
        ).fetchall()
    session = _group_session_from_row(row)
    can_continue = bool(session.waiting_started_at and not session.continued_at and
                        (datetime.now(timezone.utc) - session.waiting_started_at).total_seconds() >= WAIT_TO_CONTINUE_SECONDS)
    return GroupSessionStatus(**session.model_dump(), members=[
        SessionMember(user=User(id=member["user_id"], name=member["name"]), joined_at=member["joined_at"], completed_at=member["completed_at"])
        for member in member_rows
    ], can_continue_without_members=can_continue)


def start_group_session(share_token: str, host_user_id: str) -> GroupSession | None:
    return _update_group_session(share_token, host_user_id, "status='in_progress', started_at=?", [db.now()])


def begin_waiting_for_results(share_token: str, host_user_id: str) -> GroupSession | None:
    return _update_group_session(share_token, host_user_id, "waiting_started_at=COALESCE(waiting_started_at, ?)", [db.now()])


def continue_group_session(share_token: str, host_user_id: str) -> GroupSession | None:
    status = get_group_session_status(share_token, host_user_id)
    everyone_completed = bool(status and status.members and all(member.completed_at for member in status.members))
    if status is None or not (status.can_continue_without_members or everyone_completed):
        return None
    return _update_group_session(share_token, host_user_id, "status='results_started', continued_at=?", [db.now()])


def _update_group_session(share_token: str, host_user_id: str, update: str, values: list[str]) -> GroupSession | None:
    _ensure_db()
    with db.connect() as con:
        con.execute(f"UPDATE group_sessions SET {update} WHERE share_token=? AND host_user_id=?", [*values, share_token, host_user_id])
        row = con.execute("SELECT * FROM group_sessions WHERE share_token=? AND host_user_id=?", [share_token, host_user_id]).fetchone()
    return _group_session_from_row(row) if row else None


def _group_session_from_row(row) -> GroupSession:
    return GroupSession(
        id=row["session_id"], share_token=row["share_token"], host_user_id=row["host_user_id"], status=row["status"],
        created_at=row["created_at"], started_at=row["started_at"], waiting_started_at=row["waiting_started_at"], continued_at=row["continued_at"],
    )


def group_session_deck(share_token: str, user_id: str) -> dict[str, list[Any]] | None:
    _ensure_db()
    with db.connect(read_only=True) as con:
        row = con.execute(
            "SELECT s.deck_json FROM group_sessions s JOIN session_members m ON m.session_id=s.session_id "
            "WHERE s.share_token=? AND m.user_id=?", [share_token, user_id],
        ).fetchone()
    if row is None or not row["deck_json"]:
        return None
    return json.loads(row["deck_json"])


def direct_session_films(share_token: str, user_id: str) -> list[dict[str, Any]] | None:
    deck = group_session_deck(share_token, user_id)
    if deck is None:
        return None
    return [card for film_id in deck["direct"] if (card := film_card(film_id))]


def blind_session_pairs(share_token: str, user_id: str) -> list[dict[str, Any]] | None:
    deck = group_session_deck(share_token, user_id)
    if deck is None:
        return None
    pairs = []
    for index, film_ids in enumerate(deck["pairs"], start=1):
        cards = [film_card(film_id, include_title=False) for film_id in film_ids]
        if all(cards):
            pairs.append({"id": f"pair-{index}", "choices": [
                {"id": "a", "label": "Story A", "copy": cards[0]["description"]},
                {"id": "b", "label": "Story B", "copy": cards[1]["description"]},
            ]})
    return pairs


def film_is_in_direct_session_deck(share_token: str, user_id: str, film_id: str) -> bool:
    deck = group_session_deck(share_token, user_id)
    return bool(deck and film_id in deck["direct"])
