# Contributing

Create focused branches from the default branch and follow ticket boundaries in `docs/WORKSTREAMS.md`. Explain incomplete TODOs in pull requests.

Before a pull request:

```bash
make lint
make test
docker compose config --quiet
```

Run `make smoke` when infrastructure or cross-service behavior changes. Normal CI needs neither Docker nor Gemini credentials.

The JSON Schemas in `contracts/` define project-level Contracts A/B/C/D. Breaking changes require explicit architecture review and coordinated examples, models, renderer/provider, and tests. Internal Python models may evolve while public contracts stay compatible. Never add fixture selection to Contract A.

Analysis persistence (DBADV-05) and feedback (DBADV-06) are separate concerns/repository boundaries even when they share SQLite. Keep HTML rendering (DBADV-04) separate from AI and feedback storage.

Never commit `.env`, credentials, API keys, runtime databases, generated Grafana data, Python caches, or build output. Do not force-push shared branches.
