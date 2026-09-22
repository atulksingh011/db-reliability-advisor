# Architecture

The frozen project flow keeps audit persistence parallel to live analysis. Analysis Persistence and Feedback are separate responsibilities even though both currently use the same SQLite database.

```mermaid
flowchart LR
    T[Trigger / Scenario] -->|Contract A| AS[Analysis Service<br/>orchestrator, adapters, evidence builder, deterministic analysis]
    AS -->|Contract B| AI[AI Provider + Validator]
    AS -. request, evidence, findings .-> AP[(Analysis Persistence / Audit)]
    AI -->|Contract C| RR[Python Report Renderer<br/>Jinja2]
    AI -. attempts, validation, report .-> AP
    RR --> HTML[Server-rendered HTML report + feedback form]
    HTML -->|Contract D| FS[Feedback Service]
    FS --> FP[(Feedback Storage)]
    AP --- DB[(SQLite file)]
    FP --- DB
    PR[(Prometheus)] -. future DBADV-02 .-> AS
    LO[(Loki)] -. future DBADV-02 .-> AS
    MO[(MongoDB metadata)] -. future DBADV-02 .-> AS
```

Contract A is only `target`, `startTime`, and `endTime`. Trigger metadata and scenario selection do not expand the contract. Development-only fixture selectors use the same pipeline.

The Analysis Service sends Contract B directly to AI; it does not read current evidence back from SQLite. Persistence is a side path for audit/replay. AI returns a structured interpretation, the validator checks schema and referenced IDs, and normal Python code assembles Contract C. AI never generates HTML. Jinja renders Contract C with autoescaping enabled.

The default runtime uses `MockAdapter` and `MockAIProvider`. Prometheus/Loki/Mongo analysis, realistic workloads and advanced grounding remain future ticket work as defined in `WORKSTREAMS.md`. Grafana log visibility is infrastructure and is not the future Loki analysis adapter.
