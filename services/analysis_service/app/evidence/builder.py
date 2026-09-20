from ..adapters.base import CollectedEvidence
from ..contracts.models import AnalysisPackage, AnalysisRequest, AnalysisWindow


class EvidenceBuilder:
    def build(
        self,
        analysis_id: str,
        request: AnalysisRequest,
        collected: CollectedEvidence,
    ) -> AnalysisPackage:
        return AnalysisPackage(
            analysis_id=analysis_id,
            target=request.target,
            window=AnalysisWindow(start_time=request.start_time, end_time=request.end_time),
            evidence=collected.evidence,
            deterministic_findings=[],
            missing_evidence=collected.missing_evidence,
        )
