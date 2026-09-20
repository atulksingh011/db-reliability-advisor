#!/usr/bin/env sh
set -eu

check() {
  name="$1"
  url="$2"
  curl \
    --fail \
    --silent \
    --show-error \
    --retry 20 \
    --retry-delay 2 \
    --retry-all-errors \
    "$url" >/dev/null
  echo "ok: $name"
}

docker compose exec -T mongo mongosh \
  --quiet \
  --username root \
  --password local_root_password \
  --authenticationDatabase admin \
  --eval 'quit(db.adminCommand({ping: 1}).ok ? 0 : 2)' \
  localhost:27017/admin >/dev/null
echo "ok: MongoDB"

check "MongoDB exporter" "http://localhost:9216/metrics"
check "Prometheus" "http://localhost:9090/-/ready"
check "Loki" "http://localhost:3100/ready"
check "Grafana" "http://localhost:3001/api/health"
check "Alertmanager" "http://localhost:9093/-/ready"
check "Analysis Service" "http://localhost:8000/health"
check "Orders API" "http://localhost:8001/health"
check "UI" "http://localhost:8080/"

report="$(curl --fail --silent --show-error -X POST http://localhost:8000/api/v1/dev/mock/query-regression)"
echo "$report" | grep -q '"schemaVersion":"1.0"'
echo "$report" | grep -q 'Query Efficiency Regression'
echo "ok: mock Contract C response"
