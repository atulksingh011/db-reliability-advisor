from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..contracts.models import AnalysisPackage, Hypothesis, to_camel


class StrictAIModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class AIInterpretationSection(StrictAIModel):
    id: str
    category: str
    title: str
    hypothesis: Hypothesis
    recommended_checks: list[str]
    limitations: list[str]
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    deterministic_finding_ids: list[str] = Field(default_factory=list)


class AIInterpretation(StrictAIModel):

    status: Literal["healthy", "warning", "critical", "insufficient_data", "failed"]
    summary: str = Field(min_length=1)
    sections: list[AIInterpretationSection]
    limitations: list[str]


class AIProvider(ABC):
    name: str

    @abstractmethod
    def analyze(self, package: AnalysisPackage) -> AIInterpretation:
        """Return a structured interpretation; never mutate evidence sources."""
