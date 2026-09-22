# Database Reliability Advisor

An intentionally lightweight, **mock-first foundation** for an AI-assisted database reliability advisor. Default execution uses `MockAdapter` and `MockAIProvider`; it makes no Gemini call and requires no AI credentials. Fixture values are illustrative, not production telemetry.

## Architecture

```mermaid
flowchart LR
    T[Trigger / Scenario] -->|Contract A| AS[Analysis Service]
    AS -->|Contract B| AI[AI + Validator]
    AS -. audit snapshots .-> AP[(Analysis Persistence)]
    AI -->|Contract C| RR[Python + Jinja2 Renderer]
    AI -. attempts / outcomes .-> AP
    RR --> HTML[HTML report + form]
    HTML -->|Contract D| FB[Feedback Service]
    FB --> FS[(Feedback Storage)]
    AP --- DB[(SQLite file)]
    FS --- DB
```

Analysis persistence and feedback are separate workstreams/repositories even though SQLite is shared. SQLite is not used to find current evidence for AI. AI returns structured data, normal Python code assembles Contract C, and Jinja2 renders escaped HTML.

## Quick start

Requirements: Docker Compose, `curl`, and Python 3.

```bash
cp .env.example .env
make up
make demo-query
make demo-connection
make smoke
make test
```

Each demo prints its report URL; the report index is `http://localhost:8000/`. Open Grafana at `http://localhost:3001` (`admin` / `admin` locally). The **MongoDB Diagnostic Logs** panel is configured for the runtime-verified Loki query `{service="mongodb"}` over the last six hours. Alloy reads `/var/log/mongodb/mongod.log`; Loki exposes `service="mongodb"` and `source="diagnostic-log"` labels.

Other endpoints: Analysis Service/OpenAPI `http://localhost:8000/docs`, Orders API `http://localhost:8001/docs`, Prometheus `http://localhost:9090`, Alertmanager `http://localhost:9093`, Loki readiness `http://localhost:3100/ready`.

The demos call development-only selectors that build ordinary Contract A requests and enter the same pipeline. Scenario selection is never part of Contract A. Run `make setup` for Python-only development, `make lint` for Ruff, and `docker compose config --quiet` to validate Compose. `make reset` removes named volumes, including local SQLite and Mongo data.

## Future work boundaries

- Real workloads/triggers belong to **DBADV-01**.
- Prometheus/Loki/Mongo analysis belongs to **DBADV-02**; connectivity/visualization does not mean a real analysis adapter exists.
- Advanced grounding, repair/fallback policy and production Gemini behavior belong to **DBADV-03**.
- **DBADV-04** owns server-rendered HTML; **DBADV-05** owns analysis audit; **DBADV-06** owns feedback workflow/storage.

See [docs/WORKSTREAMS.md](docs/WORKSTREAMS.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and [docs/CONTRACTS.md](docs/CONTRACTS.md).

## Optional Gemini provider

The Google GenAI SDK is available for deliberate network-backed experiments. Configure `AI_PROVIDER=gemini`, `GEMINI_API_KEY`, and `GEMINI_MODEL`; mock mode remains the default. This foundation does not claim advanced semantic grounding.

## Repository map

```text
contracts/                         Project-level JSON Schemas and examples
services/analysis_service/app/     Pipeline, adapters, AI, storage, Jinja reports
services/orders_api/app/           Instrumented MongoDB demo API
services/scenario_runner/          Mock scenario CLI
infra/                             MongoDB, Prometheus, Alertmanager, Loki, Alloy, Grafana
migrations/                        Alembic lifecycle
tests/                             Contract, unit, integration and smoke tests
scripts/                           Seed, demo and smoke utilities
docs/                              Architecture, contracts, development and ownership
```
