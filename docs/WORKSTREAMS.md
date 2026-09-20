# Workstreams

The foundation supplies frozen contracts, runnable mock scenarios, a shared synchronous pipeline, basic audit persistence, an instrumented orders API, local infrastructure, a report scaffold, and verification tests. TODO markers intentionally identify production work rather than pretending it is complete.

## DBADV-01 — Infrastructure and scenarios

Own real scenario generation, exporter metric verification, alert-label/time-window mapping, load controls, seed ergonomics, and production-like observability hardening. The foundation provides Compose, deterministic seeding, a demo alert rule, and a controlled Alertmanager bridge.

## DBADV-02 — Analysis Service

Implement bounded Prometheus range queries, Loki LogQL retrieval, allow-listed MongoDB metadata reads, canonical normalization, missing-evidence behavior, and the specified deterministic rules. The foundation provides adapter interfaces, connectivity helpers, evidence construction, and only the two explicit mock rule paths.

## DBADV-03 — AI and validator

Design evaluated prompts, provider error/retry behavior, numeric-claim verification, deeper grounding/contradiction checks, and Gemini integration tests. The foundation provides the provider boundary, no-network mock provider, optional official Google GenAI client, typed interpretation, and ID-based validator.

## DBADV-04 — Report UI

Replace the scaffold with the final accessible report experience, richer trusted charts, polling/error states, and verification-query links. Preserve Contract C. The foundation displays both reports and submits feedback.

## DBADV-05 — Persistence and feedback

Add migration lifecycle policy, replay workflows, retention, richer feedback queries, and operational safeguards. The foundation persists all required audit stages and Contract D using a compact SQLAlchemy repository and initial Alembic migration.
