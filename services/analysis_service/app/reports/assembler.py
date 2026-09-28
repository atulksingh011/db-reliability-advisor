from ..ai.base import AIInterpretation
from ..contracts.models import AnalysisPackage, Hypothesis, ReportSection, ValidatedReport
from .data_builder import TrustedReportData


class ReportAssembler:
    @staticmethod
    def _trusted_for_section(trusted_section, section, section_count):
        if section_count == 1:
            return trusted_section
        evidence_ids = set(section.hypothesis.supporting_evidence_ids)
        evidence_ids.update(section.hypothesis.contradicting_evidence_ids)
        evidence_ids.update(section.supporting_evidence_ids)
        evidence_ids.update(section.contradicting_evidence_ids)
        finding_ids = set(section.deterministic_finding_ids)

        facts = [
            fact
            for fact in trusted_section.facts
            if evidence_ids.intersection(fact.evidence_ids)
            or finding_ids.intersection(fact.deterministic_finding_ids)
        ]
        verification = [
            item
            for item in trusted_section.verification
            if evidence_ids.intersection(item.evidence_ids)
        ]
        charts = [
            chart
            for chart in trusted_section.charts
            if evidence_ids.intersection(trusted_section.chart_evidence_ids.get(chart.id, []))
        ]
        return type(trusted_section)(
            facts=facts,
            charts=charts,
            verification=verification,
            chart_evidence_ids={
                chart.id: trusted_section.chart_evidence_ids[chart.id] for chart in charts
            },
        )

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
        section_count = len(interpretation.sections)
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
                    facts=(
                        section_trusted := self._trusted_for_section(
                            trusted_section, section, section_count
                        )
                    ).facts,
                    hypothesis=Hypothesis(
                        text=section.hypothesis.text,
                        confidence=section.hypothesis.confidence,
                        supporting_evidence_ids=section.hypothesis.supporting_evidence_ids,
                        contradicting_evidence_ids=section.hypothesis.contradicting_evidence_ids,
                    ),
                    recommended_checks=[check.description for check in section.recommended_checks],
                    limitations=self._limitations(section.limitations, package.missing_evidence),
                    verification=section_trusted.verification,
                    charts=section_trusted.charts,
                )
                for section in interpretation.sections
            ],
            limitations=self._limitations(interpretation.limitations, package.missing_evidence),
        )
