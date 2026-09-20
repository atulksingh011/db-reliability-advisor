from ..ai.base import AIInterpretation
from ..contracts.models import AnalysisPackage, ValidatedReport


class ReportAssembler:
    def assemble(
        self, package: AnalysisPackage, interpretation: AIInterpretation
    ) -> ValidatedReport:
        return ValidatedReport(
            analysis_id=package.analysis_id,
            target=package.target,
            window=package.window,
            status=interpretation.status,
            summary=interpretation.summary,
            sections=interpretation.sections,
            limitations=interpretation.limitations,
        )
