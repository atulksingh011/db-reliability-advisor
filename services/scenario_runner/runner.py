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
) -> None:
    if scenario not in {"query-regression", "connection-pressure"}:
        raise typer.BadParameter("scenario must be query-regression or connection-pressure")
    if live:
        if scenario != "query-regression":
            raise typer.BadParameter("--live is currently supported only for query-regression")
        response = _run_live_query_regression(base_url, mongo_uri, loki_url)
    else:
        response = httpx.post(f"{base_url}/api/v1/dev/mock/{scenario}", timeout=30)
    response.raise_for_status()
    typer.echo(json.dumps(response.json(), indent=2))


def _run_live_query_regression(base_url: str, mongo_uri: str, loki_url: str) -> httpx.Response:
    scenario_id = uuid4().hex
    customer_id = f"DBADV-LIVE-{scenario_id}"
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    collection = client.get_default_database()["orders"]

    def server_time() -> datetime:
        value = client.admin.command("hello")["localTime"]
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    current_time = server_time()
    start_time = current_time - timedelta(seconds=2)
    last_marker = _latest_scenario_marker_time(loki_url, current_time)
    if last_marker is not None:
        start_time = max(start_time, last_marker + timedelta(seconds=1))
    while server_time() < start_time:
        time.sleep(0.05)
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
        for _attempt in range(5):
            list(collection.find({"customerId": customer_id}).batch_size(1000))

        before_log_time = _wait_for_slow_operation(
            loki_url,
            start_time,
            server_time() + timedelta(seconds=5),
            "customerId",
            customer_id,
            "IXSCAN",
        )
        marker_time = before_log_time + timedelta(milliseconds=10)
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

        for _attempt in range(3):
            list(collection.find({"demoScenarioId": f"{scenario_id}-missing"}).limit(1))
        after_log_time = _wait_for_slow_operation(
            loki_url,
            start_time,
            server_time() + timedelta(seconds=5),
            "demoScenarioId",
            f"{scenario_id}-missing",
            "COLLSCAN",
            after_time=marker_time,
        )
        end_time = after_log_time + timedelta(seconds=5)
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
