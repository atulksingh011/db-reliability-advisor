# Workstreams

The six tickets divide implementation ownership without changing project-level contracts. The foundation is mock-first; real source collection and workloads are intentionally not claimed as implemented.

## DBADV-01 — Infrastructure, Real Scenarios and Triggers (M)

- **Objective / architecture:** Produce real telemetry and invoke analysis from workloads or alerts; at the Trigger/Scenario edge before Contract A.
- **Input / output / contract:** Real environment and controls → observable telemetry plus Contract A. Owns no new Contract A fields; it maps into the frozen three-field request.
- **Responsibilities:** Docker/observability relevant to scenarios, real query-regression and connection-pressure workloads, manual trigger, Prometheus alert, Alertmanager → Contract A mapping, orders-api scenario controls and telemetry generation.
- **Non-responsibilities:** Evidence interpretation, AI, reporting or audit persistence logic.
- **Files/modules:** `docker-compose.yml`, `infra/`, `services/orders_api/`, `services/scenario_runner/`, `scripts/`.
- **Mocks / start now:** Compose stack, deterministic seed, development mock selectors and alert bridge. Develop load controls, realistic scenarios and alert mapping without waiting for analysis changes.
- **Dependencies / tests:** Contract A and service URLs; test workload reproducibility, alert mapping and observed metrics/logs. Integration validation: run scenario, inspect Prometheus targets, Alertmanager payload mapping and Mongo logs.
- **Definition of Done:** Both real workloads generate measurable telemetry; manual and alert triggers produce valid Contract A; controls and observability are documented. Approximate size: **M**.

## DBADV-02 — Analysis Service: Adapters + Evidence Builder + Deterministic Analysis (L)

- **Objective / architecture:** Turn bounded Contract A requests into normalized Contract B evidence and deterministic findings.
- **Input / output / contract:** Contract A → Contract B.
- **Responsibilities:** Prometheus, Loki and Mongo metadata adapters; normalization, evidence builder, sanitization, bounded evidence, event discovery, deterministic calculations and missing-evidence behavior.
- **Non-responsibilities:** AI hypothesis, HTML report or feedback.
- **Files/modules:** `services/analysis_service/app/adapters/`, `evidence/`, `analyzers/`, Contract B models/schema/examples.
- **Mocks / start now:** Mock adapter, two scenario fixtures, provenance fields and deterministic analyzer. Implement/test adapter behavior against stable interfaces independently.
- **Dependencies / tests:** Source endpoints/metrics and Contract A/B. Test timeout, empty/malformed/missing data, bounds, provenance and calculation edge cases. Integration validation: compare normalized results to source queries and verify IDs/units.
- **Definition of Done:** Three bounded adapters emit sanitized canonical evidence; deterministic findings cite inputs, handle missing evidence safely and pass contract/integration tests. Real collection remains future DBADV-02 work. Approximate size: **L**.

## DBADV-03 — Grounded AI + Validator (M)

- **Objective / architecture:** Convert Contract B into safe, structured Contract C.
- **Input / output / contract:** Contract B → Contract C.
- **Responsibilities:** Provider adapter/Gemini, prompts, structured interpretation, grounding validator, one repair attempt, deterministic fallback and safe recommendation rules.
- **Non-responsibilities:** Source collection, deterministic calculations, HTML generation or feedback.
- **Files/modules:** `services/analysis_service/app/ai/`, `orchestration/pipeline.py`, Contract C models and schema.
- **Mocks / start now:** Mock provider, typed response and ID validator. Extend validation and provider failure handling in parallel using examples.
- **Dependencies / tests:** Contract B/C. Test schema and citations, numeric/semantic claims, contradictory evidence, unsafe recommendations, provider failures, repair/fallback and no-network mock mode.
- **Definition of Done:** Every report has valid citations and policy-safe recommendations; malformed/provider failures recover through one tested repair attempt or deterministic fallback. The interpretation separates observations from hypotheses, cites support and contradiction, explains actionable checks, and states material uncertainty/root-cause limits. Numeric grounding remains application-owned; production Gemini integration is configured separately and tested manually when credentials are available. Approximate size: **M**.

## DBADV-04 — HTML Report Generation (M)

- **Objective / architecture:** Present Contract C as accessible, inspectable server-rendered HTML.
- **Input / output / contract:** Contract C → HTML report and Contract D form rendering (not feedback storage).
- **Responsibilities:** Jinja templates, report structure, chart/table-friendly information, verification display, limitations and feedback form rendering.
- **Non-responsibilities:** AI analysis, feedback persistence, source queries or deterministic calculations.
- **Files/modules:** `services/analysis_service/app/reporting/`, `app/api/analyses.py`, HTML tests.
- **Mocks / start now:** Contract C examples and mock pipeline outputs. Improve report layout/accessibility without React or a new business contract.
- **Dependencies / tests:** Contract C and report routes. Test escaping, all report fields, links, form fields and page responses. Integration validation: run both demo commands and submit the rendered form.
- **Definition of Done:** Developers can manually trigger an analysis, open either report, and see trusted impact statistics, support/contradiction, verification provenance, next investigation, uncertainty and missing evidence; untrusted text is escaped; form serializes Contract D. Approximate size: **M**.

## DBADV-05 — Analysis Persistence and Audit (M)

- **Objective / architecture:** Preserve analysis lifecycle and replay/audit evidence on a side path, never as the live AI input path.
- **Input / output / contract:** Contract A, Contract B, AI attempts/validation and Contract C snapshots → SQLite audit records.
- **Responsibilities:** Analysis lifecycle records, request/evidence/findings snapshots, AI attempts, validation outcomes, final reports, replay/audit foundation and migration lifecycle; retention later.
- **Non-responsibilities:** Feedback business workflow or using SQLite to hydrate current analysis evidence for AI.
- **Files/modules:** `services/analysis_service/app/storage/repository.py`, `storage/models.py`, `migrations/`.
- **Mocks / start now:** SQLite, SQLAlchemy models, initial migration, in-memory repository and pipeline audit writes.
- **Dependencies / tests:** Project contracts and lifecycle. Test each persisted stage, failure status, migration and audit retrieval. Integration validation: run both scenarios and compare stored snapshots to pipeline contracts.
- **Definition of Done:** Every stage is recorded and retrievable with migrations; tests prove provider receives Contract B directly and persistence remains parallel. Approximate size: **M**.

## DBADV-06 — Feedback (S)

- **Objective / architecture:** Receive and retain user feedback separately from analysis lifecycle persistence.
- **Input / output / contract:** Contract D → validated feedback record and later review/evaluation linkage.
- **Responsibilities:** Feedback endpoint, Contract D validation, finding association, feedback repository operations, retrieval/review scaffolding and future evaluation-case linkage.
- **Non-responsibilities:** Analysis lifecycle persistence or HTML form presentation.
- **Files/modules:** `services/analysis_service/app/api/feedback.py`, `storage/feedback_repository.py`, Contract D model/schema.
- **Mocks / start now:** Contract D fixture and HTML form from DBADV-04; SQLite engine may be shared.
- **Dependencies / tests:** Analysis ID and optional finding ID. Test verdict validation, unknown analysis/finding behavior, storage, and retrieval. Integration validation: submit feedback from a rendered report and confirm its independent record.
- **Definition of Done:** Contract D is validated/stored behind a dedicated repository and later query/review remains separately implementable. Approximate size: **S**.
