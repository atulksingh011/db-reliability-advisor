from ..ai.base import AIInterpretation
from ..contracts.models import AnalysisPackage, ReportSection, ValidatedReport
from .data_builder import TrustedReportData


class ReportAssembler:
    @staticmethod
    def _limitations(values: list[str], missing: list[str]) -> list[str]:
        result = list(dict.fromkeys([*values, *missing]))
        root_cause_limit = "Definitive root cause is not established by this evidence."
        if root_cause_limit not in result:
            result.append(root_cause_limit)
        return result

    def assemble(
        self,
        package: AnalysisPackage,
        trusted: TrustedReportData,
        interpretation: AIInterpretation,
    ) -> ValidatedReport:
        trusted_section = trusted.sections["default"]
        return ValidatedReport(
            analysis_id=package.analysis_id,
            target=package.target,
            window=package.window,
            status=interpretation.status,
            summary=interpretation.summary,
            sections=[
                ReportSection(
                    id=section.id,
                    category=section.category,
                    title=section.title,
                    facts=trusted_section.facts,
                    hypothesis=section.hypothesis,
                    recommended_checks=section.recommended_checks,
                    limitations=self._limitations(section.limitations, package.missing_evidence),
                    verification=trusted_section.verification,
                    charts=trusted_section.charts,
                )
                for section in interpretation.sections
            ],
            limitations=self._limitations(interpretation.limitations, package.missing_evidence),
        )
