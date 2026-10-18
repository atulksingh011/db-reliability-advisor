# Self-hosted reporting assets

The reporting UI self-hosts these pinned vendor assets:

- Bootstrap 5.3.3 (`bootstrap/bootstrap.min.css`, `bootstrap/bootstrap.bundle.min.js`)
- Bootstrap Icons 1.11.3 (`bootstrap-icons/bootstrap-icons.min.css`, `bootstrap-icons/font/bootstrap-icons.woff2`)

Sources:

- https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css
- https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js
- https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css
- https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/fonts/bootstrap-icons.woff2

The bundled Bootstrap JavaScript is loaded for the Observability dropdown. Report disclosures remain native HTML `<details>` elements so their existing behavior is unchanged. Vendor files are unmodified.
