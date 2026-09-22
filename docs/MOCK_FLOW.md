# Mock flow

All fixture values are explicitly mock/illustrative and are not production telemetry. `make demo-query` and `make demo-connection` select fixtures only in `APP_ENV=development`; both execute the exact same runtime path:

```text
Contract A -> AnalysisPipeline -> MockAdapter -> EvidenceBuilder
-> DeterministicAnalyzer -> Contract B -> MockAIProvider -> Validator
-> Contract C -> Jinja2 HTML report -> Contract D feedback -> FeedbackRepository
```

The only variable is fixture evidence (or, later, the trigger). Contract A remains the same three-field request. Demo windows are relative to the current time; the mock adapter maps fixture observations to that requested window for display while preserving their illustrative nature.

## Scenario A — query regression

- Request p95: 200 ms → 1000 ms; examined documents: 1,000 → 200,000; returned: 50 → 50.
- Scan ratio: 20:1 → 4000:1; plan: IXSCAN → COLLSCAN.
- The provider frames the changed-query explanation as a hypothesis, cites Contract B IDs and generates no HTML.

## Scenario B — connection pressure

- Connection utilization: 25% → 92%; request p95: 220 ms → 1100 ms; mock errors/failures rise.
- Contradicting evidence for query/index regression is structured: `E5` keeps the plan at IXSCAN, and `E6` shows scan ratio moving only 20 → 21. Both IDs appear in `contradictingEvidenceIds`.
- The report shows supporting and contradicting evidence separately. The development Alertmanager hook also enters this same pipeline and Contract A shape.

Analysis audit writes happen alongside, not in front of, AI: SQLite does not supply the live Contract B to the provider. Feedback uses a distinct repository boundary and Contract D.
