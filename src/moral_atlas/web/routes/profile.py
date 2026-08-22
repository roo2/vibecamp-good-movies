from fastapi import APIRouter

from ..mock_data import COMPASS_PROFILE

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("/compass")
def get_compass_profile() -> dict[str, object]:
    return COMPASS_PROFILE
