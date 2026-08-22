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


class MovieRating(BaseModel):
    id: str
    user_id: str
    film_id: str
    reaction: str
    submitted_at: datetime


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
