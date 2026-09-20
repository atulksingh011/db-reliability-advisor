export type EvidenceFact = {
  text: string;
  evidenceIds: string[];
  deterministicFindingIds: string[];
};
export type ReportSection = {
  id: string;
  category: string;
  title: string;
  facts: EvidenceFact[];
  hypothesis: {
    text: string;
    confidence: "low" | "medium" | "high";
    supportingEvidenceIds: string[];
    contradictingEvidenceIds: string[];
  };
  recommendedChecks: string[];
  limitations: string[];
  verification: Array<{system: "prometheus" | "loki"; query: string; label?: string}>;
  charts: Array<{
    id: string;
    title: string;
    type: "bar" | "line";
    unit?: string;
    series: Array<{label: string; value: number}>;
  }>;
};

export type ValidatedReport = {
  schemaVersion: "1.0";
  analysisId: string;
  target: string;
  window: {startTime: string; endTime: string};
  status: "healthy" | "warning" | "critical" | "insufficient_data" | "failed";
  summary: string;
  sections: ReportSection[];
  limitations: string[];
};
