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


def test_development_query_regression_steps_use_orders_api_mongo_boundary(monkeypatch) -> None:
    collection = _Collection()
    monkeypatch.setattr(main, "orders_collection", lambda _uri: collection)

    with TestClient(main.app) as client:
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
