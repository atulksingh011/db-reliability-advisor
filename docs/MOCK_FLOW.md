# Mock flow

Every value described here is mock / illustrative.

## Query regression

`make demo-query` posts to a development-only selector. It creates the ordinary three-field Contract A request, loads mock evidence through `MockAdapter`, builds Contract B, and computes:

- request p95: 200 ms → 1000 ms (400% increase)
- documents examined: 1,000 → 200,000
- documents returned: 50 → 50
- scan ratio: 20:1 → 4000:1
- plan: IXSCAN → COLLSCAN

The mock provider labels the changed-query explanation as a hypothesis. The validator checks every `E*` and `D*` citation, Contract C is persisted, and the UI can submit Contract D feedback.

## Connection pressure

`make demo-connection` enters the same `AnalysisPipeline` with another development fixture:

- connection utilization: 25% → 92%
- request p95: 220 ms → 1100 ms
- error rate: 0% → 8%; connection failures are present
- plan: IXSCAN → IXSCAN; scan efficiency is approximately stable

The resulting hypothesis says connection pressure is better supported than a query/index regression. No alternate application architecture exists for this scenario. The Alertmanager development webhook also maps to this same three-field request and pipeline.
