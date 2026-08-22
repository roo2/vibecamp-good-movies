from fastapi import APIRouter, status

from ..mock_store import store
from ..schemas import AccessRequest, AccessResponse

router = APIRouter(prefix="/api", tags=["access"])


@router.post("/access", response_model=AccessResponse, status_code=status.HTTP_201_CREATED)
def create_access(request: AccessRequest) -> AccessResponse:
    session = store.create_session(request.name)
    return AccessResponse(token=session.token, user=session.user)
