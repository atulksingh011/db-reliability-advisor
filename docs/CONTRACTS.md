# Contracts

`contracts/` contains the four project-level JSON Schemas. Examples are validated in CI. Internal Python models may evolve as long as project-level compatibility is preserved.

## Project-level contracts

### Contract A — trigger to Analysis Service

Exactly three required fields: non-empty `target`, `startTime`, and `endTime`. The typed model enforces `startTime < endTime`; the pipeline applies its configured maximum window. Deployment version, alert type, scenario, release time, and root cause are not request fields.

### Contract B — Analysis Service to AI/Validator

Top-level fields remain `schemaVersion`, `analysisId`, `target`, `window`, `evidence`, `deterministicFindings`, and `missingEvidence`. Evidence requires `id`, `kind`, `name`, `value`, and `source`; optional `unit` carries a canonical measurement unit where relevant. `source.system` is required; `source.query` is optional because not every source has a query concept.

Provenance is flexible: use `timestamp` for point events, `observationWindow` (`startTime`, `endTime`) for windowed observations, or neither when collection context is sufficient. These are optional and are not mutually required. Adapters should normalize units and retain source query/system where applicable.

### Contract C — AI/Validator to renderer

Contains status, summary, categorized sections, facts and citations, explicitly labelled hypotheses with supporting and contradicting evidence IDs, confidence, recommended checks, limitations, verification queries and chart-friendly deterministic data. Verification entries retain their source system, related evidence IDs, and whether a query is actual or illustrative. Mock queries are displayed as illustrative and must not be described as executed. It is structured data, never AI-authored HTML.

### Contract D — report to Feedback Service

Requires `analysisId` and verdict (`correct`, `partially_correct`, or `incorrect`). `findingId` and `comment` are optional. The HTML form serializes these same fields; the feedback service validates and stores Contract D.

## Internal Python models

Adapter observations, evidence-builder inputs, normalized `Evidence`, analyzer inputs/results, and provider interpretations are implementation models, not additional project-level contracts. Evolve them without expanding A/B/C/D unless architecture review approves a compatible contract change.
