# Contributing

Create focused feature branches (recommended: `dbadv-<ticket>-short-description`) from the current default branch. Keep changes within the ownership boundaries in `docs/WORKSTREAMS.md`, open a pull request, and explain any incomplete TODOs.

Before a pull request:

```bash
make lint
make test
npm --prefix web run build
```

Run `make smoke` when infrastructure or cross-service behavior changes.

The JSON Schemas in `contracts/` are frozen architecture contracts. Do not change Contract A, B, C, or D casually. Any breaking change requires explicit architecture review and coordinated fixture, model, UI, and test updates. Do not add scenario selection to Contract A.

Never commit `.env`, credentials, API keys, runtime databases, generated Grafana data, Python caches, `node_modules`, or frontend build output. Do not force-push shared branches.
