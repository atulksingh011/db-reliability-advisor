from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from ..contracts.models import Feedback
from .models import AnalysisRun, FeedbackRecord


class FeedbackRepository:
    """Storage boundary for Contract D feedback, separate from analysis audit."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def add_feedback(self, feedback: Feedback) -> int:
        with Session(self.engine) as session:
            if session.get(AnalysisRun, feedback.analysis_id) is None:
                raise KeyError(feedback.analysis_id)
            record = FeedbackRecord(
                analysis_id=feedback.analysis_id,
                finding_id=feedback.finding_id,
                verdict=feedback.verdict,
                comment=feedback.comment,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record.id

    def count_records(self, model: type[Any]) -> int:
        with Session(self.engine) as session:
            return len(session.scalars(select(model)).all())
