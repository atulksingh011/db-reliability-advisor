#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

ROOT_DIR="$(cd -- "$(dirname -- "$BASH_SOURCE")/.." && pwd)"
cd "$ROOT_DIR"
GATEWAY_PORT=38000
NGROK_WEB_PORT=4040
LOCAL_BASE_URL="http://localhost:$GATEWAY_PORT"
LOCAL_READY_URL="$LOCAL_BASE_URL/advisor/"
TMP_DIR="$(mktemp -d /tmp/dbadv-ngrok.XXXXXX)"
NGROK_LOG="$TMP_DIR/ngrok.log"
NGROK_PID=""
NGROK_OWNED=0
RUNTIME_BASE_CHANGED=0
STOP_STACK=0
PUBLIC_URL=""
TUNNEL_READY=0

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  if [[ -n "$NGROK_PID" ]] && kill -0 "$NGROK_PID" 2>/dev/null; then
    kill "$NGROK_PID" 2>/dev/null || true
    wait "$NGROK_PID" 2>/dev/null || true
  fi
  if (( RUNTIME_BASE_CHANGED )); then
    printf 'Restoring local Docker URLs...\n'
    PUBLIC_BASE_URL="$LOCAL_BASE_URL" docker compose up -d --force-recreate \
      grafana prometheus alertmanager >/dev/null 2>&1 || \
      warn "could not restore local PUBLIC_BASE_URL runtime configuration"
  fi
  if (( STOP_STACK )); then docker compose stop >/dev/null 2>&1 || warn "could not stop Docker"; fi
  rm -rf "$TMP_DIR"
  if (( TUNNEL_READY )); then
    if (( STOP_STACK )); then
      printf 'Public tunnel stopped. Docker demo stopped locally.\n'
    else
      printf 'Public tunnel stopped. Docker demo remains running locally.\n'
    fi
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

while (($# > 0)); do
  case "$1" in
    --stop-stack-on-exit) STOP_STACK=1; shift ;;
    --domain)
      (($# >= 2)) || die "--domain requires an HTTPS ngrok URL"
      NGROK_DOMAIN="$2"; shift 2 ;;
    --help|-h)
      printf 'Usage: %s [--stop-stack-on-exit] [--domain https://name.ngrok.app]\n' "$0"
      exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

command -v docker >/dev/null 2>&1 || die "Docker CLI is required"
command -v curl >/dev/null 2>&1 || die "curl is required"
command -v python3 >/dev/null 2>&1 || die "python3 is required to read ngrok's local API"
command -v ngrok >/dev/null 2>&1 || die "ngrok is not installed. On macOS, run 'brew install ngrok', then authenticate with 'ngrok config add-authtoken <YOUR_TOKEN>'."
docker version >/dev/null 2>&1 || die "Docker is unavailable; start Docker Desktop and retry"
docker info >/dev/null 2>&1 || die "Docker daemon is unavailable; start Docker Desktop and retry"
docker compose version >/dev/null 2>&1 || die "Docker Compose is unavailable"
ngrok config check >/dev/null 2>&1 || die "ngrok configuration is invalid"

gateway_ports="$(docker compose ps --format '{{.Service}} {{.Ports}}' demo-gateway 2>/dev/null || true)"
[[ "$gateway_ports" == *"$GATEWAY_PORT"* ]] || die "DBADV demo-gateway does not own host port $GATEWAY_PORT"

local_code="$(curl -sS -o "$TMP_DIR/local-ready.html" -w '%{http_code}' --max-time 8 "$LOCAL_READY_URL")" || true
if [[ "$local_code" != 200 ]] || ! grep -q 'DB Reliability Advisor' "$TMP_DIR/local-ready.html"; then
  printf 'Local gateway is not ready; starting the existing Compose stack...\n'
  docker compose up -d >/dev/null
fi

deadline=$((SECONDS + 90))
while (( SECONDS < deadline )); do
  local_code="$(curl -sS -o "$TMP_DIR/local-ready.html" -w '%{http_code}' --max-time 5 "$LOCAL_READY_URL")" || local_code=000
  if [[ "$local_code" == 200 ]] && grep -q 'DB Reliability Advisor' "$TMP_DIR/local-ready.html"; then break; fi
  sleep 1
done
[[ "$local_code" == 200 ]] || die "local gateway did not become ready at $LOCAL_READY_URL"

ngrok_api() { curl -fsS --max-time 3 "http://127.0.0.1:$NGROK_WEB_PORT/api/tunnels"; }

extract_url() {
  python3 -c '
import json, sys
try: data = json.load(sys.stdin)
except Exception: raise SystemExit(0)
for tunnel in data.get("tunnels", []):
    url = str(tunnel.get("public_url", ""))
    addr = str(tunnel.get("config", {}).get("addr", "")).lower()
    normalized = addr.replace("http://", "").replace("https://", "").rstrip("/")
    if normalized in {"localhost:38000", "127.0.0.1:38000", "[::1]:38000"} and url.startswith("https://"):
        print(url.rstrip("/")); break
'
}

extract_any_https_url() {
  python3 -c '
import json, sys
try: data = json.load(sys.stdin)
except Exception: raise SystemExit(0)
for tunnel in data.get("tunnels", []):
    url = str(tunnel.get("public_url", ""))
    if url.startswith("https://"):
        print(url.rstrip("/")); break
'
}

existing="$(ngrok_api 2>/dev/null || true)"
if [[ -n "$existing" ]]; then
  PUBLIC_URL="$(printf '%s' "$existing" | extract_url)"
  [[ -n "$PUBLIC_URL" ]] || die "ngrok inspector port $NGROK_WEB_PORT has another tunnel; refusing to interfere"
  warn "reusing an existing ngrok tunnel forwarding localhost:$GATEWAY_PORT"
else
  ngrok_args=(http "$GATEWAY_PORT" --log="$NGROK_LOG" --log-format=logfmt)
  if [[ -n "${NGROK_DOMAIN:-}" ]]; then
    [[ "$NGROK_DOMAIN" == https://* ]] || die "--domain must be an HTTPS URL"
    ngrok_args+=(--url "$NGROK_DOMAIN")
  fi
  ngrok "${ngrok_args[@]}" >/dev/null 2>&1 &
  NGROK_PID=$!
  NGROK_OWNED=1
  deadline=$((SECONDS + 60))
  while (( SECONDS < deadline )); do
    tunnels="$(ngrok_api 2>/dev/null || true)"
    if [[ -n "$tunnels" ]]; then
      PUBLIC_URL="$(printf '%s' "$tunnels" | extract_any_https_url)"
      [[ -n "$PUBLIC_URL" ]] && break
    fi
    kill -0 "$NGROK_PID" 2>/dev/null || die "ngrok exited; authenticate with 'ngrok config add-authtoken <YOUR_TOKEN>' and retry"
    sleep 1
  done
  [[ -n "$PUBLIC_URL" ]] || die "timed out waiting for an HTTPS ngrok URL"
fi
[[ "$PUBLIC_URL" =~ ^https://[^/]+$ ]] || die "ngrok returned an invalid HTTPS URL"

printf 'Applying public base URL to Grafana, Prometheus, and Alertmanager...\n'
PUBLIC_BASE_URL="$PUBLIC_URL" docker compose up -d --force-recreate \
  grafana prometheus alertmanager >/dev/null
RUNTIME_BASE_CHANGED=1

check_route() {
  local url="$1" label="$2" marker="$3" body="$TMP_DIR/$2.body" code
  code="$(curl -sS -L -o "$body" -w '%{http_code}' --max-time 20 "$url")" || die "$label failed: $url"
  [[ "$code" =~ ^[23][0-9][0-9]$ ]] || die "$label returned HTTP $code: $url"
  [[ -z "$marker" ]] || grep -qi "$marker" "$body" || die "$label response marker missing: $url"
  printf '%-24s %s\n' "$label" "$code"
}

deadline=$((SECONDS + 120))
grafana_code=000
loki_code=000
while (( SECONDS < deadline )); do
  grafana_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "$LOCAL_BASE_URL/grafana/api/health")" || grafana_code=000
  loki_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "$LOCAL_BASE_URL/loki/ready")" || loki_code=000
  [[ "$grafana_code" == 200 && "$loki_code" == 200 ]] && break
  sleep 1
done
[[ "$grafana_code" == 200 ]] || die "Grafana did not become healthy after public URL configuration"
[[ "$loki_code" == 200 ]] || die "Loki did not become ready after public URL configuration"

printf '\nLocal routes\n'
check_route "$LOCAL_BASE_URL/" root 'DB Reliability Advisor'
check_route "$LOCAL_BASE_URL/grafana/" grafana grafana
check_route "$LOCAL_BASE_URL/prometheus/" prometheus Prometheus
check_route "$LOCAL_BASE_URL/alertmanager/" alertmanager Alertmanager
check_route "$LOCAL_BASE_URL/advisor/" advisor Analysis
check_route "$LOCAL_BASE_URL/orders/docs" orders 'Swagger UI'
check_route "$LOCAL_BASE_URL/loki/ready" loki_ready ready

check_public_route() {
  local path="$1" label="$2" marker="$3" body="$TMP_DIR/public-$2.body" headers="$TMP_DIR/public-$2.headers" code target
  code="$(curl -sS -L -D "$headers" -o "$body" -w '%{http_code}' --max-time 30 "$PUBLIC_URL$path")" || die "public request failed: $PUBLIC_URL$path"
  if [[ ! "$code" =~ ^[23][0-9][0-9]$ ]] && [[ "$label" != orders_dev_blocked || "$code" != 404 ]]; then
    die "public route returned HTTP $code: $PUBLIC_URL$path"
  fi
  while IFS= read -r target; do
    target="$(printf '%s' "$target" | sed -E 's/^[Ll]ocation:[[:space:]]*//; s/\r$//')"
    [[ "$target" =~ localhost|127\.0\.0\.1|grafana:3000|prometheus:9090|alertmanager:9093|analysis-service:8000|loki:3100 ]] && die "public redirect exposed a private target: $path -> $target"
    if [[ "$target" == http://* || "$target" == https://* ]] && [[ "$target" != "$PUBLIC_URL"* ]]; then
      die "public redirect left the public hostname: $path -> $target"
    fi
  done < <(grep -i '^location:' "$headers" || true)
  [[ -z "$marker" ]] || grep -qi "$marker" "$body" || die "public response marker missing: $PUBLIC_URL$path"
  # Embedded diagnostic/configuration text may contain local defaults; the
  # security boundary is enforced on actual redirect targets and asset URLs.
  printf '%-24s %s\n' "$label" "$code"
}

printf '\nPublic routes\n'
check_public_route / root 'DB Reliability Advisor'
check_public_route /grafana/ grafana grafana
check_public_route /prometheus/ prometheus Prometheus
check_public_route /alertmanager/ alertmanager Alertmanager
check_public_route /advisor/ advisor Analysis
check_public_route /orders/docs orders 'Swagger UI'
check_public_route /loki/ready loki_ready ready

check_public_route /orders/dev/blocked orders_dev_blocked ''
grep -q '404' "$TMP_DIR/public-orders_dev_blocked.body" || die "public /orders/dev/* was not blocked"

check_asset_references() {
  local body="$1" label="$2" ref
  while IFS= read -r ref; do
    [[ "$ref" =~ localhost|127\.0\.0\.1|grafana:3000|prometheus:9090|alertmanager:9093|analysis-service:8000|loki:3100 ]] &&
      die "$label exposed a private asset URL: $ref"
    if [[ "$ref" == http://* || "$ref" == https://* ]] && [[ "$ref" != "$PUBLIC_URL"* ]]; then
      die "$label asset URL left the public hostname: $ref"
    fi
  done < <(
    {
      grep -oE 'src="[^"]+"' "$body" | sed -E 's/^src="//; s/"$//'
      grep -oE 'rel="stylesheet"[^>]*href="[^"]+"' "$body" | sed -E 's/.*href="//; s/"$//'
    } || true
  )
}

check_asset_references "$TMP_DIR/public-grafana.body" grafana
check_asset_references "$TMP_DIR/public-advisor.body" advisor

curl -fsS --max-time 20 "$PUBLIC_URL/grafana/api/health" | grep -Eq '"database"[[:space:]]*:[[:space:]]*"ok"' || die "public Grafana health failed"
curl -fsS --max-time 20 "$PUBLIC_URL/grafana/api/dashboards/uid/dbadv-mvp-overview" | grep -q 'DB Reliability Advisor' || die "public dashboard API failed"
curl -fsSG --max-time 20 --data-urlencode 'query=sum(up)' \
  "$PUBLIC_URL/grafana/api/datasources/proxy/uid/prometheus/api/v1/query" | grep -q '"status":"success"' || die "public Prometheus query failed"
now_ns="$(date +%s%N)"
curl -fsSG --max-time 20 --data-urlencode 'query={service="orders-api",source="application-log"}' \
  --data-urlencode "start=$((now_ns - 3600000000000))" --data-urlencode "end=$now_ns" --data-urlencode 'limit=1' \
  "$PUBLIC_URL/grafana/api/datasources/proxy/uid/loki/loki/api/v1/query_range" | grep -q '"status":"success"' || die "public Loki query failed"
curl -fsS --max-time 20 "$PUBLIC_URL/advisor/static/report.css" >/dev/null || die "public Advisor CSS failed"

analysis_id="${ANALYSIS_ID:-}"
if [[ -n "$analysis_id" ]]; then
  check_public_route "/advisor/analyses/$analysis_id/report" report report
else
  printf '%-24s skipped (set ANALYSIS_ID to validate an existing report)\n' report
fi

TUNNEL_READY=1
printf '\n============================================================\nDB Reliability Advisor — Public Demo\n============================================================\n\n'
printf 'Public URL:\n%s\n\n' "$PUBLIC_URL"
printf 'Landing page:       %s/\nAdvisor:            %s/advisor/\nGrafana:            %s/grafana/\nPrometheus:         %s/prometheus/\nAlertmanager:       %s/alertmanager/\nOrders API docs:    %s/orders/docs\nLoki readiness:     %s/loki/ready\n\n' "$PUBLIC_URL" "$PUBLIC_URL" "$PUBLIC_URL" "$PUBLIC_URL" "$PUBLIC_URL" "$PUBLIC_URL" "$PUBLIC_URL"
printf 'Grafana mode: Anonymous Viewer\nGrafana Explore: Not available to anonymous Viewer by design.\n'
if (( NGROK_OWNED )); then printf 'ngrok inspector:    http://127.0.0.1:%s\n' "$NGROK_WEB_PORT"; else printf 'ngrok tunnel: Existing tunnel reused; it is not owned by this process.\n'; fi
printf '\nOnly localhost:%s is exposed. Press Ctrl-C to stop the tunnel.\nDocker services will remain running locally.\n============================================================\n' "$GATEWAY_PORT"

if (( NGROK_OWNED )); then
  wait "$NGROK_PID"
  die "ngrok exited unexpectedly"
fi
while :; do
  curl -fsS --max-time 5 "$PUBLIC_URL/" >/dev/null || die "the reused ngrok tunnel is no longer reachable"
  sleep 5
done
