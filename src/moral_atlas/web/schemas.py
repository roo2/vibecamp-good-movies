"""Request and response types owned by the web API, not the atlas pipeline."""
from datetime import datetime

from pydantic import BaseModel, Field


class AccessRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class User(BaseModel):
    id: str
    name: str


class AccessResponse(BaseModel):
    token: str
    user: User


class TestResultRequest(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)
    session_share_token: str | None = Field(default=None, min_length=1, max_length=120)


class TestResult(BaseModel):
    id: str
    user_id: str
    answers: dict[str, str]
    answered_count: int
    submitted_at: datetime


class MovieRatingRequest(BaseModel):
    film_id: str = Field(min_length=1, max_length=120)
    reaction: str = Field(min_length=1, max_length=40)
    session_share_token: str | None = Field(default=None, min_length=1, max_length=120)


class MovieRating(BaseModel):
    id: str
    user_id: str
    film_id: str
    reaction: str
    submitted_at: datetime


class MoralScore(BaseModel):
    """Where one person sits on one derived moral axis."""
    dim_id: int
    name: str
    question: str
    pole_high: str
    pole_low: str
    score: float = Field(description="-1 (pole_low) to +1 (pole_high); 0 is uncommitted.")
    leaning: str = Field(description="high, low, or balanced.")
    stance: str = Field(description="What this leaning asserts, in the axis's own words.")
    evidence_items: float = Field(description="Weighted bank items behind the score.")
    films: int
    confidence: float = Field(description="0-1; how far the score has escaped the shrinkage prior.")


class ProfileEvidence(BaseModel):
    films_rated: int
    films_not_seen: int
    pairs_answered: int
    films_used: int
    films_without_scores: list[str] = Field(default_factory=list)


class MoralProfile(BaseModel):
    user_id: str
    dim_version: str
    bank_version: str
    scores: list[MoralScore]
    evidence: ProfileEvidence
    is_provisional: bool
    summary: str


class GroupSession(BaseModel):
    id: str
    share_token: str
    host_user_id: str
    status: str
    created_at: datetime
    started_at: datetime | None = None
    waiting_started_at: datetime | None = None
    continued_at: datetime | None = None


class SessionMember(BaseModel):
    user: User
    joined_at: datetime
    completed_at: datetime | None = None


class GroupSessionStatus(GroupSession):
    members: list[SessionMember]
    can_continue_without_members: bool
