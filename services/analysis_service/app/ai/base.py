from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..contracts.models import AnalysisPackage, ReportSection, to_camel


class AIInterpretation(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    status: Literal["healthy", "warning", "critical", "insufficient_data", "failed"]
    summary: str = Field(min_length=1)
    sections: list[ReportSection]
    limitations: list[str]


class AIProvider(ABC):
    name: str

    @abstractmethod
    def analyze(self, package: AnalysisPackage) -> AIInterpretation:
        """Return a structured interpretation; never mutate evidence sources."""
