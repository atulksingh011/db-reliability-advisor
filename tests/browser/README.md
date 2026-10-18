# Advisor browser interaction smoke

Start the normal development Docker Compose stack, then run with an installed Playwright runtime:

```sh
PLAYWRIGHT_PACKAGE=/absolute/path/to/playwright node tests/browser/advisor-ui.mjs
```

The browser is visible by default. Set `UI_HEADLESS=1` only for supplemental automation.
The default run is read-only apart from intentionally invalid form submissions. It uses existing
reports; pass `UI_QUERY_URL`, `UI_CONNECTION_URL`, and `UI_FALLBACK_URL` for known report states.

For full local acceptance, `UI_MUTATIONS=1` creates one query demo, one connection demo, and one
manual analysis. `UI_FEEDBACK=1` submits exactly one feedback record. Use a mock report for feedback.
Do not enable these flags for a production environment or repeat feedback unnecessarily.

`UI_BASE_URL` defaults to `http://localhost:38000`. `UI_OUTPUT` defaults to
`.scratch/final-ui-interaction-qa` (never commit generated evidence).

The suite checks six viewports, real clipboard contents, both disclosure sequences, native and
server form validation, dropdown mouse/keyboard/focus behavior, safe external-tool links,
context/row geometry, fallback confidence, same-origin requests, asset MIME types, and console
and network failures. It writes an interaction matrix, sanitized network metadata, and screenshots.
Expected 422 validation responses are recorded separately from unexpected errors.
