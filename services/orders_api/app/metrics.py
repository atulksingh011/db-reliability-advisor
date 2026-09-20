from prometheus_client import Counter, Histogram

REQUESTS = Counter(
    "orders_api_requests_total", "Orders API HTTP requests", ["method", "path", "status"]
)
REQUEST_DURATION = Histogram(
    "orders_api_request_duration_seconds", "Orders API request duration", ["method", "path"]
)
ERRORS = Counter("orders_api_errors_total", "Orders API errors", ["path", "error_type"])
