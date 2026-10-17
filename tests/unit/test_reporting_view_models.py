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
