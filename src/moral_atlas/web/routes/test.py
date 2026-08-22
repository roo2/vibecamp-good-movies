from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import current_session
from ..mock_data import QUESTIONS
from ..store import Session, list_test_results, save_test_result as persist_test_result
from ..schemas import TestResult, TestResultRequest

router = APIRouter(prefix="/api/test", tags=["test"])
VALID_ANSWERS = {
    question["id"]: {choice["id"] for choice in question["choices"]} | {"neither"}
    for question in QUESTIONS
}


@router.get("/questions")
def get_test_questions() -> dict[str, list[dict[str, object]]]:
    return {"questions": QUESTIONS}


@router.post("/results", response_model=TestResult, status_code=status.HTTP_201_CREATED)
def save_test_result(
    request: TestResultRequest,
    session: Annotated[Session, Depends(current_session)],
) -> TestResult:
    for question_id, choice_id in request.answers.items():
        if choice_id not in VALID_ANSWERS.get(question_id, set()):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown question or answer.")
    return persist_test_result(session.user.id, request.answers, request.session_share_token)


@router.get("/results", response_model=list[TestResult])
def get_test_results(session: Annotated[Session, Depends(current_session)]) -> list[TestResult]:
    return list_test_results(session.user.id)
