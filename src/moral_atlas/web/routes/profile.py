from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import current_session
from ..profile_service import moral_profile
from ..schemas import MoralProfile
from ..store import Session

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("/moral", response_model=MoralProfile)
def get_moral_profile(
    session: Annotated[Session, Depends(current_session)],
    dim_version: str = "d1",
    bank_version: str = "b1",
) -> MoralProfile:
    """The user's score on each derived moral axis, from everything they have told us."""
    try:
        return moral_profile(session.user.id, dim_version, bank_version)
    except LookupError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error),
        ) from error
