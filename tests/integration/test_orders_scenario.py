import importlib

from fastapi.testclient import TestClient

from services.orders_api.app import main


class _Cursor:
    def __init__(self, documents: list[dict[str, object]]) -> None:
        self.documents = documents

    def sort(self, *_args: object, **_kwargs: object) -> "_Cursor":
        return self

    def limit(self, limit: int) -> "_Cursor":
        self.documents = self.documents[:limit]
        return self

    def __iter__(self):
        return iter(self.documents)


class _Collection:
    def __init__(self) -> None:
        self.queries: list[dict[str, object]] = []

    def find(self, query: dict[str, object]) -> _Cursor:
        self.queries.append(query)
        if "customerId" in query:
            return _Cursor([{"orderId": "baseline"}])
        return _Cursor([])


def _reload_orders_api(monkeypatch, app_env: str):
    monkeypatch.setenv("APP_ENV", app_env)
    main.get_settings.cache_clear()
    return importlib.reload(main)


def test_development_query_regression_steps_use_orders_api_mongo_boundary(monkeypatch) -> None:
    orders_main = _reload_orders_api(monkeypatch, "development")
    collection = _Collection()
    monkeypatch.setattr(orders_main, "orders_collection", lambda _uri: collection)

    with TestClient(orders_main.app) as client:
        indexed = client.get(
            "/dev/scenario/query-regression",
            params={"mode": "indexed", "customerId": "customer-1", "scenarioId": "scenario-1"},
        )
        regression = client.get(
            "/dev/scenario/query-regression",
            params={"mode": "regression", "customerId": "customer-1", "scenarioId": "scenario-1"},
        )

    assert indexed.status_code == 200
    assert indexed.json() == {"mode": "indexed", "count": 1}
    assert regression.status_code == 200
    assert regression.json() == {"mode": "regression", "count": 0}
    assert collection.queries == [
        {"customerId": "customer-1"},
        {"demoScenarioId": "scenario-1-missing"},
    ]


def test_test_environment_does_not_expose_development_scenario_route(monkeypatch) -> None:
    orders_main = _reload_orders_api(monkeypatch, "test")

    response = TestClient(orders_main.app).get(
        "/dev/scenario/query-regression",
        params={"mode": "indexed", "customerId": "customer-1", "scenarioId": "scenario-1"},
    )

    assert response.status_code == 404


def test_production_does_not_expose_development_scenario_route(monkeypatch) -> None:
    orders_main = _reload_orders_api(monkeypatch, "production")

    response = TestClient(orders_main.app).get(
        "/dev/scenario/query-regression",
        params={"mode": "indexed", "customerId": "customer-1", "scenarioId": "scenario-1"},
    )

    assert response.status_code == 404
