from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from ..contracts.models import Feedback

router = APIRouter(prefix="/api/v1")


@router.post("/analyses/{analysis_id}/feedback", response_model=None, status_code=201)
async def submit_feedback(analysis_id: str, request: Request) -> dict[str, object] | HTMLResponse:
    if request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
        fields = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        payload_data = {key: values[-1] for key, values in fields.items()}
        payload_data["comment"] = payload_data.get("comment") or None
        is_html_form = True
    else:
        payload_data = await request.json()
        is_html_form = False
    try:
        payload = Feedback.model_validate(payload_data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    if analysis_id != payload.analysis_id:
        raise HTTPException(status_code=422, detail="Path and payload analysisId must match")
    try:
        feedback_id = request.app.state.feedback_repository.add_feedback(payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Analysis not found") from exc
    if is_html_form:
        return HTMLResponse(
            "<!doctype html><html lang='en'><meta charset='utf-8'>"
            "<title>Feedback recorded</title><p>Feedback recorded. "
            f"<a href='/analyses/{analysis_id}/report'>Return to report</a></p></html>",
            status_code=201,
        )
    return {"id": feedback_id, "status": "recorded"}
