import json
import os
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_public_demo_script_is_safe_and_targets_only_gateway() -> None:
    script = ROOT / "scripts" / "expose-demo.sh"
    text = script.read_text()

    assert script.is_file()
    assert os.access(script, os.X_OK)
    assert "GATEWAY_PORT=38000" in text
    assert 'ngrok_args=(http "$GATEWAY_PORT"' in text
    assert 'PUBLIC_BASE_URL="$PUBLIC_URL"' in text
    assert "grafana prometheus alertmanager" in text
    assert "/orders/dev/blocked" in text
    for port in ("8000", "8001", "3001", "9090", "9093", "3100"):
        assert f'ngrok_args=(http "{port}"' not in text


def test_loki_provisioning_and_live_dashboard_queries_are_explicit() -> None:
    datasource = (ROOT / "infra/grafana/provisioning/datasources/datasources.yml").read_text()
    dashboard = json.loads((ROOT / "infra/grafana/dashboards/mvp-overview.json").read_text())
    assert 'uid: loki' in datasource
    assert 'url: http://loki:3100' in datasource
    loki_targets = [
        panel["targets"][0]["expr"]
        for panel in dashboard["panels"]
        if panel["datasource"]["type"] == "loki"
    ]
    assert any('service="orders-api",source="application-log"' in query for query in loki_targets)
    assert any(
        "Slow query" in query
        and "reliability_demo.orders" in query
        and 'attr_appName="orders-api"' in query
        for query in loki_targets
    )
    assert any('source="scenario-marker"' in query for query in loki_targets)


def test_gateway_exposes_only_documented_read_oriented_surface_paths() -> None:
    config = (ROOT / "infra/gateway/nginx.conf").read_text()
    landing = (ROOT / "infra/gateway/index.html").read_text()
    for path in ("/grafana/", "/prometheus/", "/alertmanager/", "/advisor/", "/orders/", "/loki/"):
        assert path in config or path in landing
    assert "location /orders/dev/ { return 404; }" in config
    assert "127.0.0.1:38000:8080" in (ROOT / "docker-compose.yml").read_text()
    assert "location /advisor/static/" in config


def test_gateway_resolves_backend_dns_at_request_time() -> None:
    config = (ROOT / "infra/gateway/nginx.conf").read_text()

    assert "resolver 127.0.0.11 valid=10s ipv6=off;" in config
    for backend, target in {
        "grafana": "grafana:3000",
        "prometheus": "prometheus:9090",
        "alertmanager": "alertmanager:9093",
        "advisor": "analysis-service:8000",
        "orders": "orders-api:8001",
        "loki": "loki:3100",
    }.items():
        assert f"zone {backend}_backend 64k;" in config
        assert f"server {target} resolve;" in config
