from fastapi import APIRouter, HTTPException, Request, status

from ..contracts.models import Feedback

router = APIRouter(prefix="/api/v1")


@router.post("/analyses/{analysis_id}/feedback", status_code=status.HTTP_201_CREATED)
def submit_feedback(analysis_id: str, payload: Feedback, request: Request) -> dict[str, object]:
    if analysis_id != payload.analysis_id:
        raise HTTPException(status_code=422, detail="Path and payload analysisId must match")
    try:
        feedback_id = request.app.state.repository.add_feedback(payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Analysis not found") from exc
    return {"id": feedback_id, "status": "recorded"}
