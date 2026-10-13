import json
import os
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

import httpx
import typer
from pymongo import MongoClient

app = typer.Typer(help="Run mock/illustrative scenarios through the Analysis Service.")

BASELINE_SECONDS = 35
COMPARISON_SECONDS = 35
PROMETHEUS_WAIT_SECONDS = 45
REQUEST_INTERVAL_SECONDS = 0.5


@app.command()
def run(
    scenario: Annotated[str, typer.Argument(help="query-regression or connection-pressure")],
    base_url: Annotated[
        str,
        typer.Option(help="Analysis Service base URL"),
    ] = os.getenv("ANALYSIS_SERVICE_URL", "http://localhost:8000"),
    live: Annotated[bool, typer.Option(help="Run query-regression against live telemetry")] = False,
    mongo_uri: Annotated[
        str,
        typer.Option(help="MongoDB URI for the live query scenario"),
    ] = os.getenv(
        "MONGODB_URI",
        "mongodb://app_user:app_password@localhost:27017/reliability_demo?authSource=reliability_demo",
    ),
    loki_url: Annotated[str, typer.Option(help="Loki base URL")] = os.getenv(
        "LOKI_URL", "http://localhost:3100"
    ),
    orders_api_url: Annotated[str, typer.Option(help="Orders API base URL")] = os.getenv(
        "ORDERS_API_URL", "http://localhost:8001"
    ),
    prometheus_url: Annotated[str, typer.Option(help="Prometheus base URL")] = os.getenv(
        "PROMETHEUS_URL", "http://localhost:9090"
    ),
) -> None:
    if scenario not in {"query-regression", "connection-pressure"}:
        raise typer.BadParameter("scenario must be query-regression or connection-pressure")
    if live:
        if scenario != "query-regression":
            raise typer.BadParameter("--live is currently supported only for query-regression")
        response = _run_live_query_regression(
            base_url,
            mongo_uri,
            loki_url,
            orders_api_url,
            prometheus_url,
        )
    else:
        response = httpx.post(f"{base_url}/api/v1/dev/mock/{scenario}", timeout=30)
    response.raise_for_status()
    typer.echo(json.dumps(response.json(), indent=2))


def _run_live_query_regression(
    base_url: str,
    mongo_uri: str,
    loki_url: str,
    orders_api_url: str,
    prometheus_url: str,
) -> httpx.Response:
    scenario_id = uuid4().hex
    customer_id = f"DBADV-LIVE-{scenario_id}"
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    collection = client.get_default_database()["orders"]

    def server_time() -> datetime:
        value = client.admin.command("hello")["localTime"]
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    current_time = server_time()
    last_marker = _latest_scenario_marker_time(loki_url, current_time)
    try:
        collection.insert_many(
            [
                {
                    "orderId": f"LIVE-{scenario_id}-{index}",
                    "customerId": customer_id,
                    "status": "pending",
                    "createdAt": datetime.now(UTC),
                    "demoScenarioId": scenario_id,
                }
                for index in range(10_000)
            ],
            ordered=False,
        )
        start_time = server_time()
        if last_marker is not None:
            start_time = max(start_time, last_marker + timedelta(seconds=1))
        baseline_end = _run_orders_api_phase(
            orders_api_url,
            "indexed",
            customer_id,
            scenario_id,
            BASELINE_SECONDS,
        )
        before_log_time = _wait_for_slow_operation(
            loki_url,
            start_time,
            baseline_end + timedelta(seconds=5),
            "customerId",
            customer_id,
            "IXSCAN",
        )
        marker_time = max(before_log_time, server_time()) + timedelta(milliseconds=10)
        marker = {
            "event": "scenario_marker",
            "service": "orders-api",
            "scenario": "live-query-regression",
            "scenarioId": scenario_id,
            "timestamp": marker_time.isoformat(),
        }
        httpx.post(
            f"{loki_url.rstrip('/')}/loki/api/v1/push",
            json={
                "streams": [
                    {
                        "stream": {"service": "orders-api", "source": "scenario-marker"},
                        "values": [
                            [str(int(marker_time.timestamp() * 1_000_000_000)), json.dumps(marker)]
                        ],
                    }
                ]
            },
            timeout=10,
        ).raise_for_status()

        comparison_end = _run_orders_api_phase(
            orders_api_url,
            "regression",
            customer_id,
            scenario_id,
            COMPARISON_SECONDS,
        )
        after_log_time = _wait_for_slow_operation(
            loki_url,
            start_time,
            comparison_end + timedelta(seconds=5),
            "demoScenarioId",
            f"{scenario_id}-missing",
            "COLLSCAN",
            after_time=marker_time,
        )
        end_time = _wait_for_prometheus_observation(
            prometheus_url,
            comparison_end,
            start_time,
            after_log_time,
        )
        return httpx.post(
            f"{base_url.rstrip('/')}/api/v1/dev/live/analyses",
            json={
                "target": "orders-api",
                "startTime": start_time.isoformat().replace("+00:00", "Z"),
                "endTime": end_time.isoformat().replace("+00:00", "Z"),
            },
            timeout=60,
        )
    finally:
        collection.delete_many({"demoScenarioId": scenario_id})
        client.close()


def _run_orders_api_phase(
    orders_api_url: str,
    mode: str,
    customer_id: str,
    scenario_id: str,
    duration_seconds: int,
) -> datetime:
    deadline = time.monotonic() + duration_seconds
    while time.monotonic() < deadline:
        response = httpx.get(
            f"{orders_api_url.rstrip('/')}/dev/scenario/query-regression",
            params={
                "mode": mode,
                "customerId": customer_id,
                "scenarioId": scenario_id,
            },
            timeout=10,
        )
        response.raise_for_status()
        time.sleep(REQUEST_INTERVAL_SECONDS)
    return datetime.now(UTC)


def _wait_for_prometheus_observation(
    prometheus_url: str,
    comparison_end: datetime,
    start_time: datetime,
    fallback_end: datetime,
) -> datetime:
    query = 'orders_api_requests_total{job="orders-api",path="/dev/scenario/query-regression"}'
    deadline = time.monotonic() + PROMETHEUS_WAIT_SECONDS
    latest_timestamp = None
    while time.monotonic() < deadline:
        response = httpx.get(
            f"{prometheus_url.rstrip('/')}/api/v1/query",
            params={"query": query},
            timeout=5,
        )
        response.raise_for_status()
        result = response.json().get("data", {}).get("result", [])
        timestamps = [
            float(item["value"][0])
            for item in result
            if isinstance(item.get("value"), list) and len(item["value"]) == 2
        ]
        if timestamps:
            latest_timestamp = max(timestamps)
            if latest_timestamp >= comparison_end.timestamp():
                return max(
                    datetime.fromtimestamp(latest_timestamp, UTC),
                    fallback_end,
                    start_time + timedelta(seconds=1),
                )
        time.sleep(1)
    raise RuntimeError(
        "Timed out waiting for Prometheus to scrape the Orders API comparison phase"
    )


def _wait_for_slow_operation(
    loki_url: str,
    start_time: datetime,
    end_time: datetime,
    filter_field: str,
    filter_value: str,
    expected_plan: str,
    after_time: datetime | None = None,
) -> datetime:
    query = (
        '{service="mongodb",source="diagnostic-log"} | json | msg="Slow query" '
        f"|= {json.dumps(filter_value)}"
    )
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        response = httpx.get(
            f"{loki_url.rstrip('/')}/loki/api/v1/query_range",
            params={
                "query": query,
                "start": str(int(start_time.timestamp() * 1_000_000_000)),
                "end": str(int(end_time.timestamp() * 1_000_000_000)),
                "limit": 100,
                "direction": "forward",
            },
            timeout=5,
        )
        response.raise_for_status()
        matching_times = []
        for stream in response.json().get("data", {}).get("result", []):
            for timestamp_ns, line in stream.get("values", []):
                try:
                    log = json.loads(line)
                    attributes = log.get("attr", {})
                    command = attributes.get("command", {})
                    query_filter = command.get("filter", {})
                    timestamp = datetime.fromtimestamp(int(timestamp_ns) / 1_000_000_000, UTC)
                except (json.JSONDecodeError, TypeError):
                    continue
                plan = attributes.get("planSummary")
                if (
                    attributes.get("ns") != "reliability_demo.orders"
                    or query_filter.get(filter_field) != filter_value
                    or not isinstance(plan, str)
                    or plan.split()[0] != expected_plan
                    or (after_time is not None and timestamp <= after_time)
                ):
                    continue
                matching_times.append(timestamp)
        if matching_times:
            return max(matching_times)
        time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for the {expected_plan} query log in Loki")


def _latest_scenario_marker_time(
    loki_url: str,
    end_time: datetime,
) -> datetime | None:
    response = httpx.get(
        f"{loki_url.rstrip('/')}/loki/api/v1/query_range",
        params={
            "query": '{service="orders-api",source="scenario-marker"}',
            "start": str(int((end_time - timedelta(days=1)).timestamp() * 1_000_000_000)),
            "end": str(int(end_time.timestamp() * 1_000_000_000)),
            "limit": 100,
            "direction": "backward",
        },
        timeout=10,
    )
    response.raise_for_status()
    timestamps = []
    for stream in response.json().get("data", {}).get("result", []):
        for timestamp_ns, line in stream.get("values", []):
            try:
                event = json.loads(line)
                timestamp = datetime.fromtimestamp(int(timestamp_ns) / 1_000_000_000, UTC)
            except (json.JSONDecodeError, TypeError):
                continue
            if event.get("event") == "scenario_marker":
                timestamps.append(timestamp)
    return max(timestamps) if timestamps else None


if __name__ == "__main__":
    app()
