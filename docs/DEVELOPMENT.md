# Development

Copy `.env.example` to `.env`, then run `make setup` for local Python or `make up` for Docker Compose. The Analysis Service serves the report index at `http://localhost:8000/`, report pages at `/analyses/{analysis_id}/report`, and OpenAPI at `/docs`.

```bash
.venv/bin/uvicorn services.analysis_service.app.main:app --reload --port 8000
.venv/bin/uvicorn services.orders_api.app.main:app --reload --port 8001
make demo-query
make demo-connection
make test
make lint
```

The demo commands print the report URL. Tests use temporary SQLite databases and require neither Gemini credentials nor Docker. `make smoke` validates the running Compose stack.

## Ticket entry points

- **DBADV-01:** `docker-compose.yml`, `infra/`, `services/orders_api/`, `services/scenario_runner/`, and `scripts/`. Mock fixtures and the development alert bridge are available; real workloads, triggers and telemetry generation remain future work.
- **DBADV-02:** `services/analysis_service/app/adapters/`, `evidence/`, and `analyzers/`. `MockAdapter`, canonical Contract B examples, and fixtures provide seams; Prometheus, Loki and Mongo collectors remain TODOs.
- **DBADV-03:** `services/analysis_service/app/ai/` and `services/analysis_service/app/orchestration/pipeline.py`. Mock and Gemini provider boundaries plus Contract B fixtures are available; advanced grounding and policy remain TODOs.
- **DBADV-04:** `services/analysis_service/app/reporting/` and HTML routes in `app/api/analyses.py`. Contract C examples and mock pipeline output are available; extend accessible templates without changing report semantics.
- **DBADV-05:** `services/analysis_service/app/storage/repository.py`, `app/storage/models.py`, `migrations/`. SQLite audit snapshots, AI attempts, outcomes and reports are recorded; retention/replay policy remains future work.
- **DBADV-06:** `services/analysis_service/app/api/feedback.py`, `app/storage/feedback_repository.py`, and Contract D. The report form and feedback persistence are runnable; listing/review and evaluation linkage remain future work.

## Replacing mocks

Implement collectors behind `EvidenceAdapter`; normalize evidence and keep queries bounded by Contract A. Do not leak exporter field names or raw source payloads into project contracts. Provider implementations return structured interpretations only; they do not collect evidence, persist data, bypass validation, or generate HTML.

Analysis and feedback repositories own separate business operations and may share the SQLite engine and SQLAlchemy metadata. Use Alembic for schema evolution. Fixture selection is development-only and never belongs in Contract A. Numeric/semantic grounding is not fully implemented; see DBADV-03 in `WORKSTREAMS.md`.

MongoDB diagnostic logs are visible in Grafana via the runtime-verified Loki selector `{service="mongodb"}` (labels include `source="diagnostic-log"`). This infrastructure view does not imply a production Loki evidence adapter.
