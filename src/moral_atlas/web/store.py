"""SQLite-backed persistence for the name-only web experience."""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from secrets import token_urlsafe
from typing import Any
from uuid import uuid4

from .. import db
from .film_service import MIN_CARDS, build_session_deck, film_card
from .schemas import GroupSession, GroupSessionStatus, MovieRating, SessionMember, TestResult, User

WAIT_TO_CONTINUE_SECONDS = 10 * 60


@dataclass(frozen=True)
class Session:
    token: str
    user: User


def _ensure_db() -> None:
    db.init_db()


def create_session(name: str = "") -> Session:
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
        existing = con.execute(
            "SELECT result_id FROM test_results WHERE user_id=? AND session_share_token=? "
            "ORDER BY submitted_at DESC LIMIT 1", [user_id, session_share_token],
        ).fetchone() if session_share_token else None
        if existing:
            result.id = existing["result_id"]
            con.execute(
                "UPDATE test_results SET answers=?, answered_count=?, submitted_at=? WHERE result_id=?",
                [json.dumps(result.answers), result.answered_count, result.submitted_at.isoformat(), result.id],
            )
        else:
            con.execute(
                "INSERT INTO test_results (result_id, user_id, answers, answered_count, "
                "submitted_at, session_share_token) VALUES (?,?,?,?,?,?)",
                [result.id, result.user_id, json.dumps(result.answers), result.answered_count,
                 result.submitted_at.isoformat(), session_share_token],
            )
        if session_share_token:
            con.execute(
                "UPDATE session_members SET completed_at=? WHERE user_id=? AND completed_at IS NULL "
                "AND session_id=(SELECT session_id FROM group_sessions WHERE share_token=? AND status='in_progress')",
                [result.submitted_at.isoformat(), user_id, session_share_token],
            )
    return result


def current_test_result(user_id: str, session_share_token: str) -> TestResult | None:
    _ensure_db()
    with db.connect(read_only=True) as con:
        row = con.execute(
            "SELECT result_id, user_id, answers, answered_count, submitted_at FROM test_results "
            "WHERE user_id=? AND session_share_token=? ORDER BY submitted_at DESC LIMIT 1",
            [user_id, session_share_token],
        ).fetchone()
    if row is None:
        return None
    return TestResult(
        id=row["result_id"], user_id=row["user_id"], answers=json.loads(row["answers"]),
        answered_count=row["answered_count"], submitted_at=row["submitted_at"],
    )


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


def user_rating_inputs(user_id: str) -> list[tuple[str, str]]:
    """(film_id, reaction), newest first, for scoring the user's moral profile."""
    _ensure_db()
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT film_id, reaction FROM movie_ratings WHERE user_id=? "
            "ORDER BY submitted_at DESC", [user_id],
        ).fetchall()
    return [(row["film_id"], row["reaction"]) for row in rows]


# The most of the ranking a chosen position may drive.
#
# Not 1.0. At full weight the merit drops the co-preference score entirely, and
# that score is the only part of the ranking that predicts enjoyment — it orders
# a liked film above a disliked one 83% of the time against the moral axes' 57%.
# A deck ordered purely by what a film argues is reliably less watchable, so the
# ceiling keeps a fifth of the say with enjoyment. Enforced on read as well as on
# write, so a value stored before this cap existed behaves the way the screen
# says it does rather than the way it was saved.
MAX_MORAL_WEIGHT = 0.8


def moral_stance(user_id: str) -> tuple[str | None, float]:
    """The position this person chose, and how much of the ranking it drives.

    A missing row and an explicit zero are both "do not weight morality", and
    the caller cannot tell them apart from here — `stance_answered` can, and
    that is the one that decides whether to ask again.
    """
    _ensure_db()
    with db.connect(read_only=True) as con:
        row = con.execute(
            "SELECT moral_stance, moral_weight FROM users WHERE user_id=?",
            [user_id]).fetchone()
    if not row:
        return None, 0.0
    weight = row["moral_weight"]
    return row["moral_stance"], min(float(weight), MAX_MORAL_WEIGHT) if weight is not None else 0.0


def stance_answered(user_id: str) -> bool:
    """Whether they have answered at all — including by choosing to opt out."""
    _ensure_db()
    with db.connect(read_only=True) as con:
        row = con.execute("SELECT moral_weight FROM users WHERE user_id=?",
                          [user_id]).fetchone()
    return bool(row) and row["moral_weight"] is not None


def save_moral_stance(user_id: str, stance_id: str | None, weight: float) -> tuple[str | None, float]:
    """Record a chosen position. `stance_id` of None is the don't-care answer.

    The weight is stored even when the stance is None, because answering "none
    of these" is an answer and must not read as never having been asked.
    """
    _ensure_db()
    weight = max(0.0, min(MAX_MORAL_WEIGHT, float(weight)))
    if stance_id is None:
        weight = 0.0
    with db.connect() as con:
        con.execute("UPDATE users SET moral_stance=?, moral_weight=? WHERE user_id=?",
                    [stance_id, weight, user_id])
    return stance_id, weight


def user_pair_answers(user_id: str) -> list[tuple[str, list[str]]]:
    """(choice, [film_a, film_b]) for every blind pair the user answered.

    The answers only name pairs — "pair-3" — so each result is read against the
    deck of the session it was submitted in. Results saved before that token was
    recorded fall back to the decks of every session the user belongs to, which
    resolves them whenever the pair ids are unambiguous across those decks.
    """
    _ensure_db()
    with db.connect(read_only=True) as con:
        results = con.execute(
            "SELECT answers, session_share_token FROM test_results WHERE user_id=? "
            "ORDER BY submitted_at DESC", [user_id],
        ).fetchall()
        decks = con.execute(
            "SELECT s.share_token, s.deck_json FROM group_sessions s "
            "JOIN session_members m ON m.session_id=s.session_id WHERE m.user_id=?",
            [user_id],
        ).fetchall()

    by_token = {row["share_token"]: json.loads(row["deck_json"])
                for row in decks if row["deck_json"]}
    any_deck: dict[str, list[str]] = {}
    for deck in by_token.values():
        any_deck.update(_pair_lookup(deck))

    answers: list[tuple[str, list[str]]] = []
    seen: set[tuple[str, ...]] = set()
    for result in results:
        deck = by_token.get(result["session_share_token"])
        pairs = _pair_lookup(deck) if deck else any_deck
        for question_id, choice in json.loads(result["answers"]).items():
            film_ids = pairs.get(question_id)
            key = tuple(sorted(film_ids)) if film_ids else None
            if key is None or key in seen:
                continue
            seen.add(key)
            answers.append((choice, film_ids))
    return answers


def _pair_lookup(deck: dict[str, list[Any]]) -> dict[str, list[str]]:
    """Pair id -> the two films behind it, numbered as `blind_session_pairs` does."""
    return {f"pair-{index}": list(film_ids)
            for index, film_ids in enumerate(deck.get("pairs") or [], start=1)}


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


def _ensure_shortlist(con, session_id: str) -> None:
    if con.execute("SELECT 1 FROM session_shortlist_films WHERE session_id=?", [session_id]).fetchone():
        return
    member_ids = [row["user_id"] for row in con.execute(
        "SELECT user_id FROM session_members WHERE session_id=? ORDER BY joined_at", [session_id]
    ).fetchall()]
    # Import here because the ranking service reads preference helpers from this
    # module. A session keeps the resulting order forever, even as later votes
    # change a person's profile.
    from .shortlist_service import ranked_shortlist
    film_ids = [film["id"] for film in ranked_shortlist(member_ids, limit=None)]
    if not film_ids:
        film_ids = [row["film_id"] for row in con.execute("SELECT film_id FROM films").fetchall()]
        random.SystemRandom().shuffle(film_ids)
    con.executemany("INSERT INTO session_shortlist_films (session_id, film_id, position) VALUES (?,?,?)", [(session_id, film_id, position) for position, film_id in enumerate(film_ids)])


def reorder_shortlist(share_token: str, user_id: str) -> bool:
    """Throw away a session's deck order so the next request rebuilds it.

    A session materialises its order once and keeps it, which is right while the
    inputs are fixed and wrong the moment somebody changes their moral position:
    the control would save, report success, and deal the same cards forever.

    Only the ORDER is dropped. Votes live in `shortlist_reactions`, keyed by
    session and film rather than by position, so anything already swiped stays
    swiped and does not come back round.

    In a shared session this re-ranks the deck for everyone, which is the honest
    consequence of one deck serving two people — the ranking already scores each
    member separately and takes the worst, so the other person's say is not lost,
    it is re-applied.
    """
    _ensure_db()
    with db.connect() as con:
        session = con.execute(
            "SELECT session_id FROM group_sessions WHERE share_token=?",
            [share_token]).fetchone()
        if session is None:
            return False
        member = con.execute(
            "SELECT 1 FROM session_members WHERE session_id=? AND user_id=?",
            [session["session_id"], user_id]).fetchone()
        if not member:
            return False
        con.execute("DELETE FROM session_shortlist_films WHERE session_id=?",
                    [session["session_id"]])
    return True


def next_shortlist_film(share_token: str, user_id: str, since: int = 0) -> dict[str, Any] | None:
    """The next cards to judge — or the shortlist, once it holds something new.

    `since` is how many agreed films the asker has already been shown. It exists
    because "keep looking" was a dead end: a full shortlist ended the deck, so
    the screen asked for another card, was handed the same three films it had
    just closed, and sat on "Finding films for you…" forever. Saying what you
    have already seen turns a terminal state into a threshold — the deck keeps
    dealing until there is a film in the shortlist you have not seen.
    """
    _ensure_db()
    with db.connect() as con:
        session = con.execute("SELECT session_id, selected_film_id FROM group_sessions WHERE share_token=?", [share_token]).fetchone()
        if session is None or not con.execute("SELECT 1 FROM session_members WHERE session_id=? AND user_id=?", [session["session_id"], user_id]).fetchone():
            return None
        full = _shortlist_state(con, session["session_id"])
        if full["state"] == "shortlist" and len(full["films"]) > since:
            return full
        _ensure_shortlist(con, session["session_id"])
        # A queue, not a card. Swiping felt sluggish because each swipe posted a
        # vote and then asked for the next film, so the animation finished into a
        # wait for two round trips. Handing over the next few lets the screen
        # advance the moment a card leaves and send the vote behind it.
        rows = con.execute(
            "SELECT q.film_id FROM session_shortlist_films q WHERE q.session_id=? "
            "AND NOT EXISTS (SELECT 1 FROM shortlist_reactions n WHERE n.session_id=q.session_id AND n.film_id=q.film_id AND n.reaction='no') "
            "AND NOT EXISTS (SELECT 1 FROM shortlist_reactions mine WHERE mine.session_id=q.session_id AND mine.film_id=q.film_id AND mine.user_id=?) "
            "ORDER BY q.position LIMIT ?", [session["session_id"], user_id, QUEUE_AHEAD],
        ).fetchall()
    films = [card for row in rows if (card := film_card(row["film_id"]))]
    if not films:
        return {"state": "exhausted"}
    # `film` stays for anything still reading one card at a time.
    return {"state": "card", "film": films[0], "queue": films}


# How many films both of them have to want before the swiping stops.
#
# One was too few. Landing on a single title the moment it appears makes the
# choice for a couple who were enjoying making it, and leaves them with a verdict
# rather than an evening's options — the pair who tested this asked for a
# shortlist. Three is small enough to choose between without a second argument.
MATCHES_WANTED = 3

# How many cards ahead the client is given, so a swipe never waits on a request.
QUEUE_AHEAD = 6


def _agreed_films(con, session_id: str) -> list[str]:
    """Films every member said yes to and nobody said no to, oldest vote first.

    Derived from the votes rather than stored. There is nothing to migrate, no
    second source of truth to drift, and the answer is always consistent with the
    reactions it is computed from — including after someone's vote is removed.
    """
    members = con.execute(
        "SELECT count(*) FROM session_members WHERE session_id=?", [session_id]).fetchone()[0]
    if not members:
        return []
    return [row["film_id"] for row in con.execute(
        "SELECT film_id, MAX(submitted_at) agreed_at FROM shortlist_reactions "
        "WHERE session_id=? GROUP BY film_id "
        "HAVING COUNT(DISTINCT CASE WHEN reaction='yes' THEN user_id END)=? "
        "AND SUM(reaction='no')=0 ORDER BY agreed_at",
        [session_id, members])]


def _shortlist_state(con, session_id: str) -> dict[str, Any]:
    """What the pair should be seeing: still swiping, or a shortlist to choose from."""
    agreed = _agreed_films(con, session_id)
    if len(agreed) >= MATCHES_WANTED:
        return {"state": "shortlist",
                "films": [card for film_id in agreed if (card := film_card(film_id))]}
    return {"state": "pending", "matches": len(agreed), "wanted": MATCHES_WANTED}


def shortlist_selection(share_token: str, user_id: str) -> dict[str, Any] | None:
    _ensure_db()
    with db.connect(read_only=True) as con:
        session = con.execute("SELECT session_id, selected_film_id FROM group_sessions WHERE share_token=?", [share_token]).fetchone()
        if session is None or not con.execute("SELECT 1 FROM session_members WHERE session_id=? AND user_id=?", [session["session_id"], user_id]).fetchone():
            return None
        return _shortlist_state(con, session["session_id"])


def reopen_shortlist(share_token: str, user_id: str) -> dict[str, str] | None:
    _ensure_db()
    with db.connect() as con:
        session = con.execute(
            "SELECT s.session_id FROM group_sessions s JOIN session_members m ON m.session_id=s.session_id "
            "WHERE s.share_token=? AND m.user_id=?",
            [share_token, user_id],
        ).fetchone()
        if session is None:
            return None
        con.execute("UPDATE group_sessions SET selected_film_id=NULL WHERE session_id=?", [session["session_id"]])
        return _shortlist_state(con, session["session_id"])


def save_shortlist_reaction(share_token: str, user_id: str, film_id: str, reaction: str) -> dict[str, Any] | None:
    _ensure_db()
    with db.connect() as con:
        session = con.execute("SELECT session_id FROM group_sessions WHERE share_token=?", [share_token]).fetchone()
        if session is None:
            return None
        _ensure_shortlist(con, session["session_id"])
        if not con.execute("SELECT 1 FROM session_members WHERE session_id=? AND user_id=?", [session["session_id"], user_id]).fetchone() or not con.execute("SELECT 1 FROM session_shortlist_films WHERE session_id=? AND film_id=?", [session["session_id"], film_id]).fetchone():
            return None
        if con.execute(
            "SELECT 1 FROM shortlist_reactions WHERE session_id=? AND user_id=? AND film_id=?",
            [session["session_id"], user_id, film_id],
        ).fetchone():
            return {"state": "continue"}
        con.execute("INSERT INTO shortlist_reactions (reaction_id, session_id, user_id, film_id, reaction, submitted_at) VALUES (?,?,?,?,?,?)", [f"short_{uuid4().hex[:12]}", session["session_id"], user_id, film_id, reaction, db.now()])
        if reaction == "yes":
            progress = _shortlist_state(con, session["session_id"])
            if progress["state"] == "shortlist":
                return progress
            # Below the target this is still "keep swiping" as far as the deck is
            # concerned; the counts ride along so the screen can say how close
            # the two of them are.
            return {"state": "continue", **{k: v for k, v in progress.items() if k != "state"}}
    return {"state": "continue"}


def create_group_session(host_user_id: str) -> GroupSession:
    _ensure_db()
    deck = build_session_deck()
    if not deck["direct"]:
        raise ValueError(
            f"At least {MIN_CARDS} showable films are required to start a shared session.")
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


def mark_session_member_unready(share_token: str, user_id: str) -> GroupSession | None:
    _ensure_db()
    with db.connect() as con:
        row = con.execute(
            "SELECT s.* FROM group_sessions s JOIN session_members m ON m.session_id=s.session_id "
            "WHERE s.share_token=? AND s.status='in_progress' AND m.user_id=?",
            [share_token, user_id],
        ).fetchone()
        if row is None:
            return None
        con.execute(
            "UPDATE session_members SET completed_at=NULL WHERE session_id=? AND user_id=?",
            [row["session_id"], user_id],
        )
    return _group_session_from_row(row)


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


# How many more films to deal when somebody reaches the end of the deck and
# still has not said enough for the instrument to read them. Small on purpose:
# the point is to rescue a thin reading, not to restart the quiz.
TOP_UP_CARDS = 10


def extend_session_deck(share_token: str, user_id: str, count: int = TOP_UP_CARDS) -> list[dict[str, Any]]:
    """Add films to a session's deck, skipping the ones already dealt.

    A person can answer every card and still be unreadable: "haven't seen it"
    is an honest answer that carries no moral information, and somebody who
    gives it twenty times has told us nothing about themselves. Rather than
    show them an empty compass, deal more.

    The deck is shared, so this extends it for BOTH people — which is right.
    They are answering the same films, and a deck that forked would make the
    comparison between them meaningless.
    """
    _ensure_db()
    from .film_service import deck_eligible_films

    with db.connect() as con:
        row = con.execute(
            "SELECT s.session_id, s.deck_json FROM group_sessions s "
            "JOIN session_members m ON m.session_id=s.session_id "
            "WHERE s.share_token=? AND m.user_id=?", [share_token, user_id],
        ).fetchone()
        if row is None or not row["deck_json"]:
            return []
        deck = json.loads(row["deck_json"])
        already = set(deck.get("direct") or [])
        fresh = [film for film in deck_eligible_films() if film["film_id"] not in already]
        if not fresh:
            return []
        chooser = random.SystemRandom()
        picked = chooser.sample(fresh, k=min(count, len(fresh)))
        deck["direct"] = list(deck.get("direct") or []) + [f["film_id"] for f in picked]
        con.execute("UPDATE group_sessions SET deck_json=? WHERE session_id=?",
                    [json.dumps(deck), row["session_id"]])
    return [card for film in picked if (card := film_card(film["film_id"]))]


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
        if all(card and card.get("description") for card in cards):
            pairs.append({"id": f"pair-{index}", "choices": [
                {"id": "a", "label": "Story A", "copy": cards[0]["description"]},
                {"id": "b", "label": "Story B", "copy": cards[1]["description"]},
            ]})
    return pairs


def film_is_in_direct_session_deck(share_token: str, user_id: str, film_id: str) -> bool:
    deck = group_session_deck(share_token, user_id)
    return bool(deck and film_id in deck["direct"])
