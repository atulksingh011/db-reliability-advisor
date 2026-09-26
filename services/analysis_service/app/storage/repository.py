from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from ..contracts.models import AnalysisRequest
from .error_sanitizer import sanitize_audit_value, sanitize_error_message
from .models import (
    AIAttempt,
    AnalysisResult,
    AnalysisRun,
    DeterministicResult,
    EvidenceSnapshot,
    FallbackOutcome,
    LifecycleEvent,
    ValidationOutcome,
)


def _now() -> datetime:
    return datetime.now(UTC)


class AnalysisRepository:
    """Durable audit boundary; persisted data is never a live evidence source."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def create_run(
        self,
        analysis_id: str,
        request: AnalysisRequest,
        fixture_name: str,
        replayed_from: str | None = None,
    ) -> None:
        now = _now()
        with Session(self.engine) as session:
            session.add(
                AnalysisRun(
                    analysis_id=analysis_id,
                    status="created",
                    request_payload=request.model_dump(mode="json", by_alias=True),
                    fixture_name=fixture_name,
                    target=request.target,
                    replayed_from=replayed_from,
                    created_at=now,
                    started_at=now,
                    updated_at=now,
                )
            )
            session.flush()
            session.add_all(
                [
                    LifecycleEvent(analysis_id=analysis_id, status="created", created_at=now),
                    LifecycleEvent(analysis_id=analysis_id, status="running", created_at=now),
                ]
            )
            session.commit()

    def save_analysis_package(self, analysis_id: str, package: dict[str, Any]) -> None:
        with Session(self.engine) as session:
            session.add(EvidenceSnapshot(analysis_id=analysis_id, package_payload=package))
            session.add(
                DeterministicResult(
                    analysis_id=analysis_id, findings_payload=package["deterministicFindings"]
                )
            )
            session.commit()

    def save_ai_attempt(
        self,
        analysis_id: str,
        provider: str,
        response: dict[str, Any],
        validation_status: str,
        validation_errors: list[str] | None = None,
        *,
        model: str | None = None,
        error_category: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> int:
        with Session(self.engine) as session:
            previous = (
                session.scalar(
                    select(AIAttempt.attempt_number)
                    .where(AIAttempt.analysis_id == analysis_id)
                    .order_by(AIAttempt.attempt_number.desc())
                    .limit(1)
                )
                or 0
            )
            attempt = AIAttempt(
                analysis_id=analysis_id,
                attempt_number=previous + 1,
                provider=provider,
                model=model,
                response_payload=sanitize_audit_value(response),
                validation_status=validation_status,
                validation_errors=[
                    sanitize_error_message(error) for error in (validation_errors or [])
                ],
                error_category=error_category,
                started_at=started_at or _now(),
                completed_at=completed_at or _now(),
            )
            session.add(attempt)
            session.commit()
            session.refresh(attempt)
            return attempt.id

    def save_validation(
        self,
        analysis_id: str,
        attempt_id: int | None,
        attempt_number: int,
        passed: bool,
        errors: list[str] | None = None,
        repair_required: bool = False,
    ) -> None:
        with Session(self.engine) as session:
            session.add(
                ValidationOutcome(
                    analysis_id=analysis_id,
                    ai_attempt_id=attempt_id,
                    attempt_number=attempt_number,
                    passed=passed,
                    errors=[sanitize_error_message(error) for error in (errors or [])],
                    repair_required=repair_required,
                )
            )
            session.commit()

    def save_fallback(self, analysis_id: str, reason: list[str], report: dict[str, Any]) -> None:
        with Session(self.engine) as session:
            session.add(
                FallbackOutcome(
                    analysis_id=analysis_id,
                    reason=[sanitize_error_message(error) for error in reason],
                    report_payload=sanitize_audit_value(report),
                )
            )
            session.commit()

    def save_result(self, analysis_id: str, report: dict[str, Any]) -> None:
        now = _now()
        with Session(self.engine) as session:
            session.add(AnalysisResult(analysis_id=analysis_id, report_payload=report))
            run = session.get(AnalysisRun, analysis_id)
            if run:
                fallback = (
                    session.scalar(
                        select(FallbackOutcome.id).where(FallbackOutcome.analysis_id == analysis_id)
                    )
                    is not None
                )
                run.status = "completed_with_fallback" if fallback else "completed"
                run.completed_at = now
                run.updated_at = now
                session.add(
                    LifecycleEvent(analysis_id=analysis_id, status=run.status, created_at=now)
                )
            session.commit()

    def mark_failed(self, analysis_id: str, reason: str | None = None) -> None:
        now = _now()
        with Session(self.engine) as session:
            run = session.get(AnalysisRun, analysis_id)
            if run:
                run.status, run.failed_at, run.updated_at = "failed", now, now
                detail = (
                    {"reason": sanitize_error_message(reason, "Analysis failed.")}
                    if reason
                    else None
                )
                session.add(
                    LifecycleEvent(
                        analysis_id=analysis_id, status="failed", detail=detail, created_at=now
                    )
                )
                session.commit()

    @staticmethod
    def _run_payload(run: AnalysisRun) -> dict[str, Any]:
        return {
            "analysisId": run.analysis_id,
            "status": run.status,
            "request": run.request_payload,
            "fixtureName": run.fixture_name,
            "target": run.target,
            "replayedFrom": run.replayed_from,
            "createdAt": run.created_at.isoformat() if run.created_at else None,
            "startedAt": run.started_at.isoformat() if run.started_at else None,
            "completedAt": run.completed_at.isoformat() if run.completed_at else None,
            "failedAt": run.failed_at.isoformat() if run.failed_at else None,
        }

    def get_run(self, analysis_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            run = session.get(AnalysisRun, analysis_id)
            return self._run_payload(run) if run else None

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            return [
                self._run_payload(run)
                for run in session.scalars(
                    select(AnalysisRun).order_by(AnalysisRun.created_at.desc()).limit(limit)
                ).all()
            ]

    def get_package(self, analysis_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            row = session.scalar(
                select(EvidenceSnapshot)
                .where(EvidenceSnapshot.analysis_id == analysis_id)
                .order_by(EvidenceSnapshot.created_at.desc())
            )
            return row.package_payload if row else None

    def get_audit(self, analysis_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            run = session.get(AnalysisRun, analysis_id)
            if not run:
                return None
            evidence = session.scalar(
                select(EvidenceSnapshot)
                .where(EvidenceSnapshot.analysis_id == analysis_id)
                .order_by(EvidenceSnapshot.created_at.desc())
            )
            findings = session.scalar(
                select(DeterministicResult)
                .where(DeterministicResult.analysis_id == analysis_id)
                .order_by(DeterministicResult.created_at.desc())
            )
            attempts = session.scalars(
                select(AIAttempt)
                .where(AIAttempt.analysis_id == analysis_id)
                .order_by(AIAttempt.attempt_number)
            ).all()
            validations = session.scalars(
                select(ValidationOutcome)
                .where(ValidationOutcome.analysis_id == analysis_id)
                .order_by(ValidationOutcome.id)
            ).all()
            fallbacks = session.scalars(
                select(FallbackOutcome)
                .where(FallbackOutcome.analysis_id == analysis_id)
                .order_by(FallbackOutcome.id)
            ).all()
            events = session.scalars(
                select(LifecycleEvent)
                .where(LifecycleEvent.analysis_id == analysis_id)
                .order_by(LifecycleEvent.id)
            ).all()
            return {
                "run": self._run_payload(run),
                "lifecycle": [
                    {"status": e.status, "detail": e.detail, "createdAt": e.created_at.isoformat()}
                    for e in events
                ],
                "request": run.request_payload,
                "evidence": evidence.package_payload if evidence else None,
                "deterministicFindings": findings.findings_payload if findings else None,
                "aiAttempts": [
                    {
                        "attemptNumber": a.attempt_number,
                        "provider": a.provider,
                        "model": a.model,
                        "response": a.response_payload,
                        "validationStatus": a.validation_status,
                        "validationErrors": a.validation_errors,
                        "errorCategory": a.error_category,
                        "startedAt": a.started_at.isoformat() if a.started_at else None,
                        "completedAt": a.completed_at.isoformat() if a.completed_at else None,
                    }
                    for a in attempts
                ],
                "validation": [
                    {
                        "attemptNumber": v.attempt_number,
                        "passed": v.passed,
                        "errors": v.errors,
                        "repairRequired": v.repair_required,
                    }
                    for v in validations
                ],
                "fallback": [{"reason": f.reason, "report": f.report_payload} for f in fallbacks],
                "finalReport": self.get_result(analysis_id),
            }

    def get_result(self, analysis_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            result = session.get(AnalysisResult, analysis_id)
            return result.report_payload if result else None

    def count_records(self, model: type[Any]) -> int:
        with Session(self.engine) as session:
            return len(session.scalars(select(model)).all())

    def list_reports(self, limit: int = 20) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = session.execute(
                select(AnalysisResult.report_payload)
                .order_by(AnalysisResult.created_at.desc())
                .limit(limit)
            )
            return [row[0] for row in rows]
