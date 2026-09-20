# Development

Copy `.env.example` to `.env`, then choose Docker (`make up`) or a local Python/frontend workflow (`make setup`). The local Python entry points are:

```bash
.venv/bin/uvicorn services.analysis_service.app.main:app --reload --port 8000
.venv/bin/uvicorn services.orders_api.app.main:app --reload --port 8001
npm --prefix web run dev
```

Tests use temporary in-memory SQLite databases. Run all tests with `make test`, schema tests with `make test-contracts`, integration tests with `make test-integration`, and lint/format with `make lint` / `make format`.

## Replacing mocks

Implement telemetry retrieval behind `EvidenceAdapter`. Normalize external data to `Evidence`; do not leak raw exporter field names into the project contracts. Keep reads bounded by Contract A. Add deterministic rules only for explicitly specified signals and preserve their evidence IDs.

Implement AI providers behind `AIProvider.analyze`. Providers return `AIInterpretation`; they do not create Contract B, bypass grounding validation, query MongoDB directly, or persist data themselves. Add provider tests that prove no network call occurs in mock mode.

The repository boundary owns SQLAlchemy sessions. Business modules call repository methods rather than issuing queries. Use Alembic for schema evolution.

Development fixture selection belongs only in `APP_ENV=development`; never add `scenarioType` to Contract A.
