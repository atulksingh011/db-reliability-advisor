from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(word.capitalize() for word in rest)


class ContractModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AnalysisRequest(ContractModel):
    target: str = Field(min_length=1)
    start_time: datetime
    end_time: datetime

    @model_validator(mode="after")
    def validate_window_order(self) -> "AnalysisRequest":
        if self.start_time >= self.end_time:
            raise ValueError("startTime must be earlier than endTime")
        return self


class AnalysisWindow(ContractModel):
    start_time: datetime
    end_time: datetime


class EvidenceSource(ContractModel):
    system: Literal["prometheus", "loki", "mongodb", "mock"]
    query: str | None = None


class EvidenceObservationWindow(ContractModel):
    start_time: datetime
    end_time: datetime


EvidenceKind = Literal[
    "event",
    "metric_comparison",
    "metric_window",
    "query_comparison",
    "query_window",
    "query_plan",
    "metadata",
]


class Evidence(ContractModel):
    id: str
    kind: EvidenceKind
    name: str
    value: Any
    unit: str | None = None
    source: EvidenceSource
    observation_window: EvidenceObservationWindow | None = None
    timestamp: datetime | None = None


class DeterministicFinding(ContractModel):
    id: str
    rule: str
    result: Any
    evidence_ids: list[str]


class AnalysisPackage(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    analysis_id: str
    target: str
    window: AnalysisWindow
    evidence: list[Evidence]
    deterministic_findings: list[DeterministicFinding]
    missing_evidence: list[str]


class ReportFact(ContractModel):
    text: str
    evidence_ids: list[str]
    deterministic_finding_ids: list[str]


class Hypothesis(ContractModel):
    text: str
    confidence: Literal["low", "medium", "high"]
    supporting_evidence_ids: list[str]
    contradicting_evidence_ids: list[str]


class VerificationQuery(ContractModel):
    system: Literal["prometheus", "loki"]
    query: str
    label: str | None = None


class ChartPoint(ContractModel):
    label: str
    value: float


class ReportChart(ContractModel):
    id: str
    title: str
    type: Literal["bar", "line"]
    unit: str | None = None
    series: list[ChartPoint]


class ReportSection(ContractModel):
    id: str
    category: str
    title: str
    facts: list[ReportFact]
    hypothesis: Hypothesis
    recommended_checks: list[str]
    limitations: list[str]
    verification: list[VerificationQuery]
    charts: list[ReportChart]


class ValidatedReport(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    analysis_id: str
    target: str
    window: AnalysisWindow
    status: Literal["healthy", "warning", "critical", "insufficient_data", "failed"]
    summary: str
    sections: list[ReportSection]
    limitations: list[str]


class Feedback(ContractModel):
    analysis_id: str
    finding_id: str | None = None
    verdict: Literal["correct", "partially_correct", "incorrect"]
    comment: str | None = None


class AnalysisAccepted(ContractModel):
    analysis_id: str
    status: str


class AnalysisStatus(ContractModel):
    analysis_id: str
    status: str
    request: AnalysisRequest
