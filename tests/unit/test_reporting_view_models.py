from services.analysis_service.app.reporting.renderer import TEMPLATES
from services.analysis_service.app.reporting.view_models import report_page_model, select_metrics


def _chart(chart_id: str, title: str) -> dict:
    return {
        "id": chart_id,
        "title": title,
        "unit": "percent" if chart_id.endswith("percent") else "ms",
        "series": [{"value": 1}, {"value": 2}],
    }


def test_query_metrics_prefer_query_plan_over_documents_examined() -> None:
    metrics = select_metrics(
        {
            "charts": [
                _chart("request-p95-ms", "Request p95 ms"),
                _chart("scan-ratio", "Scan ratio"),
                _chart("documents-examined", "Documents examined"),
                _chart("query-plan", "Query plan"),
            ]
        }
    )

    assert [metric["id"] for metric in metrics] == [
        "request-p95-ms",
        "scan-ratio",
        "query-plan",
    ]
    assert [metric["label"] for metric in metrics] == [
        "Request p95",
        "Scan ratio",
        "Query plan",
    ]


def test_query_metrics_fall_back_to_documents_examined_without_query_plan() -> None:
    metrics = select_metrics(
        {
            "charts": [
                _chart("request-p95-ms", "Request p95 ms"),
                _chart("scan-ratio", "Scan ratio"),
                _chart("documents-examined", "Documents examined"),
            ]
        }
    )

    assert [metric["id"] for metric in metrics] == [
        "request-p95-ms",
        "scan-ratio",
        "documents-examined",
    ]


def test_query_plan_metric_uses_trusted_package_evidence_when_chart_is_absent() -> None:
    metrics = select_metrics(
        {
            "charts": [
                _chart("request-p95-ms", "Request p95 ms"),
                _chart("scan-ratio", "Scan ratio"),
                _chart("documents-examined", "Documents examined"),
            ]
        },
        {"evidence": [{"name": "query_plan", "value": {"before": "IXSCAN", "after": "COLLSCAN"}}]},
    )

    assert [metric["id"] for metric in metrics] == [
        "request-p95-ms",
        "scan-ratio",
        "query-plan",
    ]
    assert metrics[2]["before"] == "IXSCAN"
    assert metrics[2]["after"] == "COLLSCAN"


def test_connection_metrics_keep_accepted_order_and_friendly_labels() -> None:
    metrics = select_metrics(
        {
            "charts": [
                _chart("request-error-rate-percent", "Request error rate percent"),
                _chart("connection-utilization-percent", "Connection utilization percent"),
                _chart("request-p95-ms", "Request p95 ms"),
                _chart("query-plan", "Query plan"),
            ]
        }
    )

    assert [metric["id"] for metric in metrics] == [
        "request-p95-ms",
        "connection-utilization-percent",
        "request-error-rate-percent",
    ]
    assert [metric["label"] for metric in metrics] == [
        "Request p95",
        "Connection utilization",
        "Request error rate",
    ]


def test_evidence_rows_use_trusted_evidence_names() -> None:
    page = report_page_model(
        {
            "status": "completed",
            "window": {},
            "sections": [
                {
                    "charts": [],
                    "facts": [
                        {"text": "Deployment changed", "evidenceIds": ["E1"]},
                        {"text": "Latency increased", "evidenceIds": ["E2"]},
                    ],
                    "hypothesis": {
                        "supportingEvidenceIds": ["E1", "E2"],
                        "contradictingEvidenceIds": [],
                    },
                }
            ],
            "limitations": [],
        },
        package={
            "evidence": [
                {"id": "E1", "name": "deployment"},
                {"id": "E2", "name": "request_p95_ms"},
            ]
        },
    )

    assert [row["signal"] for row in page["sections"][0]["supporting_rows"]] == [
        "Deployment event",
        "Request p95",
    ]
    assert [row["evidence"] for row in page["sections"][0]["supporting_rows"]] == [
        ["E1"],
        ["E2"],
    ]


def _report(
    facts: list[dict], supporting: list[str], contradicting: list[str], limitations: list[str]
):
    return {
        "status": "critical",
        "window": {},
        "limitations": limitations,
        "sections": [
            {
                "charts": [],
                "facts": facts,
                "hypothesis": {
                    "supportingEvidenceIds": supporting,
                    "contradictingEvidenceIds": contradicting,
                },
            }
        ],
    }


def test_query_rows_prefer_trusted_derived_findings_without_losing_evidence_ids() -> None:
    page = report_page_model(
        _report(
            [
                {"text": "Deployment event", "evidenceIds": ["E1"]},
                {"text": "Request p95 changed", "evidenceIds": ["E2"]},
                {"text": "Documents examined changed", "evidenceIds": ["E3"]},
                {"text": "Documents returned changed", "evidenceIds": ["E4"]},
                {"text": "Query plan changed", "evidenceIds": ["E5"]},
                {
                    "text": "Latency increased",
                    "evidenceIds": ["E2"],
                    "deterministicFindingIds": ["D1"],
                },
                {
                    "text": "Scan ratio changed",
                    "evidenceIds": ["E3", "E4"],
                    "deterministicFindingIds": ["D2"],
                },
                {
                    "text": "Query plan changed",
                    "evidenceIds": ["E5"],
                    "deterministicFindingIds": ["D3"],
                },
            ],
            ["E1", "E2", "E3", "E4", "E5"],
            [],
            [],
        ),
        package={
            "evidence": [
                {"id": "E1", "name": "deployment", "value": {"service": "orders-api"}},
                {
                    "id": "E2",
                    "name": "request_p95_ms",
                    "value": {"before": 200, "after": 1000, "unit": "ms"},
                },
                {
                    "id": "E3",
                    "name": "documents_examined",
                    "value": {"before": 1000, "after": 200000},
                },
                {"id": "E4", "name": "documents_returned", "value": {"before": 50, "after": 50}},
                {
                    "id": "E5",
                    "name": "query_plan",
                    "value": {"before": "IXSCAN", "after": "COLLSCAN"},
                },
            ],
            "deterministicFindings": [
                {"id": "D1", "rule": "latency_percent_change", "result": {}, "evidenceIds": ["E2"]},
                {
                    "id": "D2",
                    "rule": "scan_ratio_change",
                    "result": {"before": 20, "after": 4000},
                    "evidenceIds": ["E3", "E4"],
                },
                {
                    "id": "D3",
                    "rule": "query_plan_change",
                    "result": {"before": "IXSCAN", "after": "COLLSCAN"},
                    "evidenceIds": ["E5"],
                },
            ],
        },
    )

    rows = page["sections"][0]["supporting_rows"]
    assert [(row["signal"], row["observation"], row["evidence"]) for row in rows] == [
        ("Deployment event", "Deployment event", ["E1"]),
        ("Request p95", "200 ms → 1000 ms", ["E2"]),
        ("Scan ratio", "20 → 4000", ["E3", "E4"]),
        ("Query plan", "IXSCAN → COLLSCAN", ["E5"]),
    ]


def test_connection_rows_keep_raw_signals_and_split_stable_contradiction() -> None:
    page = report_page_model(
        _report(
            [
                {"text": "Connection utilization changed", "evidenceIds": ["E1"]},
                {"text": "Request p95 changed", "evidenceIds": ["E2"]},
                {"text": "Request errors changed", "evidenceIds": ["E3"]},
                {"text": "Connection failures", "evidenceIds": ["E4"]},
                {"text": "Query plan remained IXSCAN", "evidenceIds": ["E5"]},
                {"text": "Scan ratio changed from 20 to 21", "evidenceIds": ["E6"]},
                {
                    "text": "Connection pressure",
                    "evidenceIds": ["E1", "E4"],
                    "deterministicFindingIds": ["D1"],
                },
                {
                    "text": "Latency increased",
                    "evidenceIds": ["E2"],
                    "deterministicFindingIds": ["D2"],
                },
                {
                    "text": "Stable plan and ratio",
                    "evidenceIds": ["E5", "E6"],
                    "deterministicFindingIds": ["D3"],
                },
            ],
            ["E1", "E2", "E3", "E4"],
            ["E5", "E6"],
            [],
        ),
        package={
            "evidence": [
                {
                    "id": "E1",
                    "name": "connection_utilization_percent",
                    "value": {"before": 25, "after": 92},
                },
                {
                    "id": "E2",
                    "name": "request_p95_ms",
                    "value": {"before": 220, "after": 1100, "unit": "ms"},
                },
                {
                    "id": "E3",
                    "name": "request_error_rate_percent",
                    "value": {"before": 0, "after": 8},
                },
                {"id": "E4", "name": "connection_failures", "value": {"count": 14}},
                {
                    "id": "E5",
                    "name": "query_plan",
                    "value": {"before": "IXSCAN", "after": "IXSCAN"},
                },
                {"id": "E6", "name": "scan_ratio", "value": {"before": 20, "after": 21}},
            ],
            "deterministicFindings": [
                {
                    "id": "D1",
                    "rule": "connection_pressure",
                    "result": {},
                    "evidenceIds": ["E1", "E4"],
                },
                {"id": "D2", "rule": "latency_percent_change", "result": {}, "evidenceIds": ["E2"]},
                {
                    "id": "D3",
                    "rule": "query_plan_stable",
                    "result": {"plan": "IXSCAN"},
                    "evidenceIds": ["E5", "E6"],
                },
            ],
        },
    )

    section = page["sections"][0]
    assert [row["signal"] for row in section["supporting_rows"]] == [
        "Connection utilization",
        "Request p95",
        "Request error rate",
        "Connection failures",
    ]
    assert [(row["signal"], row["evidence"]) for row in section["contradicting_rows"]] == [
        ("Query plan", ["E5"]),
        ("Scan ratio", ["E6"]),
    ]


def test_limitations_group_by_deterministic_source_categories() -> None:
    page = report_page_model(
        _report(
            [],
            [],
            [],
            [
                "Observed correlation does not prove causation.",
                "Definitive root cause is not established by this evidence.",
                "Source client identities are not present.",
                "Telemetry is sourced from mock fixtures rather than production.",
                "Real production telemetry is not collected in mock mode.",
            ],
        )
    )

    assert page["limitations"] == [
        "Definitive root cause is not established by this evidence.",
        "Source client identities are not present.",
        "Telemetry is sourced from mock fixtures rather than production.",
    ]


def test_fallback_ai_and_root_cause_caveats_share_one_category() -> None:
    page = report_page_model(
        _report(
            [],
            [],
            [],
            [
                "AI interpretation unavailable; deterministic findings are shown.",
                "AI interpretation was unavailable; definitive root cause is not established.",
                "Definitive root cause is not established by this evidence.",
            ],
        )
    )

    assert page["limitations"] == [
        "AI interpretation was unavailable; definitive root cause is not established."
    ]


def test_fallback_hides_confidence_and_keeps_ai_state_out_of_trusted_summary() -> None:
    report = _report([], [], [], [])
    report["summary"] = (
        "AI interpretation unavailable. Request latency increased from 200 ms to 1000 ms."
    )
    report["sections"][0].update(
        {
            "id": "SEC-1",
            "hypothesis": {
                "text": (
                    "No causal hypothesis was established because AI interpretation was "
                    "unavailable."
                ),
                "confidence": "low",
                "supportingEvidenceIds": [],
                "contradictingEvidenceIds": [],
            },
        }
    )
    page = report_page_model(
        report,
        run={"status": "completed_with_fallback"},
        package={"evidence": []},
    )
    html = TEMPLATES.env.get_template("report.html").render(page=page)

    assert page["ai_unavailable"] is True
    assert page["trusted_summary"] == "Request latency increased from 200 ms to 1000 ms."
    assert "AI interpretation unavailable" in html
    assert "Confidence" not in html


def test_ai_success_keeps_confidence_for_query_and_connection() -> None:
    for category in ("database_query", "database_connections"):
        report = _report([], [], [], [])
        report["sections"][0].update(
            {
                "id": "SEC-1",
                "category": category,
                "hypothesis": {
                    "text": "Trusted hypothesis",
                    "confidence": "high",
                    "supportingEvidenceIds": [],
                    "contradictingEvidenceIds": [],
                },
            }
        )
        page = report_page_model(report, run={"status": "completed"}, package={"evidence": []})
        html = TEMPLATES.env.get_template("report.html").render(page=page)

        assert page["ai_unavailable"] is False
        assert "Trusted hypothesis" in html
        assert "Confidence" in html
