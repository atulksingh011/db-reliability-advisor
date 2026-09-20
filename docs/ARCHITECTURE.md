# Architecture

The invariant flow is:

```text
Trigger -> Contract A -> Analysis Service -> Contract B -> AI/Validator
        -> Contract C -> Report UI -> Contract D -> SQLite
```

The Analysis Service owns the adapters, evidence builder, and deterministic analyzer. These are internal modules, not extra project-level contracts. Evidence records and deterministic findings stay conceptually distinct in Contract B so a later validator can trace conclusions precisely.

Prometheus, Loki, and read-only MongoDB metadata are the future live evidence inputs. SQLite stores the Contract A request, bounded evidence snapshots, deterministic results, AI attempts, validation outcomes, final Contract C reports, and feedback. It deliberately does not mirror raw Prometheus time series or Loki streams and is never the normal evidence path into AI.

Contract A has only `target`, `startTime`, and `endTime`. Release markers, alerts, and deployment changes are evidence discovered inside that window. Development-only endpoints choose fixtures outside the contract, then call the same pipeline.

AI receives Contract B and produces a typed interpretation. The grounding validator rejects references to evidence or deterministic findings that do not exist. Only an accepted interpretation is assembled into Contract C. Numeric facts remain authoritative only insofar as they are grounded in Contract B; AI text is not a source of numeric truth. AI providers have no MongoDB mutation capability.

The default provider and telemetry adapter are mock implementations. The real adapter classes expose the intended boundaries and fail explicitly until DBADV-02 implements them.
