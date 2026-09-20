# Frozen contracts

The JSON Schemas in `contracts/` are authoritative. Examples in `contracts/examples/` are validated in CI with Draft 2020-12 and date-time format checking.

## Contract A — trigger to Analysis Service

Requires only a non-empty `target`, `startTime`, and `endTime`. The typed runtime model enforces `startTime < endTime`; the pipeline enforces `MAX_ANALYSIS_WINDOW_MINUTES`. A release time, version, alert type, root cause, or scenario type is not part of this contract.

## Contract B — Analysis Service to AI/Validator

Carries the analysis identity/window, canonical evidence, deterministic findings, and missing-evidence notices. Evidence has reproducible source metadata where available. AI hypotheses are forbidden here.

## Contract C — AI/Validator to UI

Carries a validated status, summary, sections, grounded facts, explicitly labelled hypotheses, checks, limitations, Prometheus/Loki verification queries, and trusted chart-ready data. Fact citation fields point back to Contract B IDs.

## Contract D — UI to feedback persistence

Requires `analysisId` and a verdict (`correct`, `partially_correct`, or `incorrect`). `findingId` and `comment` are optional.

Cross-field invariants that JSON Schema cannot express portably are enforced by Pydantic and covered by tests.
