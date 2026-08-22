from typing import Annotated

from fastapi import APIRouter, Depends, status

from ..deps import current_session
from ..schemas import AccessRequest, AccessResponse, User
from ..store import Session, create_session

router = APIRouter(prefix="/api", tags=["access"])


@router.post("/access", response_model=AccessResponse, status_code=status.HTTP_201_CREATED)
def create_access(request: AccessRequest) -> AccessResponse:
    session = create_session(request.name)
    return AccessResponse(token=session.token, user=session.user)


@router.get("/access/me", response_model=User)
def get_current_user(session: Annotated[Session, Depends(current_session)]) -> User:
    return session.user
