#!/usr/bin/env bash
# Deploy the authenticated demo to Cloud Run:
#   rag-api      : literature API/login/service-key API (private index remains in GCS)
#   research-api : one-PhD validation flow from the completed W3 branch
#   web          : React frontend from FRONTEND_REF, built with both API URLs
#
# Usage:
#   FRONTEND_REPO=https://github.com/<owner>/<frontend-repo> FRONTEND_REF=main \
#   DEMO_USERS_FILE=/absolute/path/to/demo-users.json \
#   SMOKE_USER=... SMOKE_PASSWORD=... \
#   ./deploy.sh PROJECT_ID [REGION]
#
# Secret values are created locally or read from Secret Manager; this script never echoes them.
# Safe to re-run: existing secrets are left unchanged and Cloud Run resources are updated in place.
set -euo pipefail

PROJECT=${1:?usage: ./deploy.sh PROJECT_ID [REGION]}
REGION=${2:-asia-southeast1}
GEMINI_MODEL=${GEMINI_MODEL:-gemini-3.8-flash}
GEMINI_LOCATION=${GEMINI_LOCATION:-global}
FRONTEND_REPO=${FRONTEND_REPO:?set FRONTEND_REPO to the frontend git repo URL}
# W1's lockfile commit is on this branch; keep the override so it can be tested before merge.
FRONTEND_REF=${FRONTEND_REF:-main}
RESEARCH_SRC=${RESEARCH_SRC:-}
SMOKE_RUN_TIMEOUT_SECONDS=${SMOKE_RUN_TIMEOUT_SECONDS:-300}

HERE=$(cd "$(dirname "$0")" && pwd)
[[ -n "$RESEARCH_SRC" ]] || RESEARCH_SRC="$HERE/../api"
BUCKET="${PROJECT}-litrag-index"
SA="sa-agents@${PROJECT}.iam.gserviceaccount.com"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
step() { printf '\n== %s\n' "$*"; }

# Resolve RESEARCH_SRC relative to the caller, while making the default relative to this deploy bundle.
case "$RESEARCH_SRC" in
  /*) ;;
  *) RESEARCH_SRC="$PWD/$RESEARCH_SRC" ;;
esac
[[ -f "$RESEARCH_SRC/Dockerfile" ]] || {
  echo "research source Dockerfile not found at $RESEARCH_SRC/Dockerfile" >&2
  exit 2
}

# Fail before making project changes when the required deploy/smoke inputs or tools are absent.
for tool in curl git gcloud openssl python3 unzip; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "required tool not found: $tool" >&2
    exit 2
  }
done
[[ -n "${SMOKE_USER:-}" && -n "${SMOKE_PASSWORD:-}" ]] || {
  echo "SMOKE_USER and SMOKE_PASSWORD are required for authenticated smoke tests" >&2
  exit 2
}
[[ "$SMOKE_RUN_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]] || {
  echo "SMOKE_RUN_TIMEOUT_SECONDS must be a positive integer" >&2
  exit 2
}

secret_exists() {
  gcloud secrets describe "$1" --project "$PROJECT" >/dev/null 2>&1
}

# Keep the generated value local to this shell/process and pass it directly to Secret Manager.
create_random_secret() {
  local name=$1
  if ! secret_exists "$name"; then
    local value
    value=$(openssl rand -base64 48)
    printf '%s' "$value" | gcloud secrets create "$name" \
      --project "$PROJECT" --data-file=- --quiet >/dev/null
  fi
}

create_demo_users_secret() {
  if secret_exists demo-users; then
    return
  fi
  [[ -n "${DEMO_USERS_FILE:-}" ]] || {
    echo "DEMO_USERS_FILE is required because demo-users does not exist" >&2
    exit 2
  }
  [[ -f "$DEMO_USERS_FILE" ]] || {
    echo "DEMO_USERS_FILE does not exist: $DEMO_USERS_FILE" >&2
    exit 2
  }
  # Syntax-check without displaying account names, hashes, or the file contents.
  python3 -m json.tool "$DEMO_USERS_FILE" >/dev/null
  gcloud secrets create demo-users --project "$PROJECT" \
    --data-file "$DEMO_USERS_FILE" --quiet >/dev/null
}

json_field() {
  python3 - "$1" "$2" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    value = json.load(handle).get(sys.argv[2], "")
print(value)
PY
}

health_ok() {
  local url=$1
  curl -fsS --max-time 20 "$url/health" 2>/dev/null | python3 -c '
import json
import sys

try:
    exit(0 if json.load(sys.stdin).get("status") == "ok" else 1)
except Exception:
    exit(1)
' >/dev/null
}

wait_for_health() {
  local label=$1 url=$2 attempt
  for attempt in $(seq 1 60); do
    if health_ok "$url"; then
      echo "$label health: ok"
      return
    fi
    sleep 5
  done
  echo "$label did not become healthy" >&2
  return 1
}

terminal_run_status() {
  python3 - "$1" <<'PY'
import json
import sys

status = ""
with open(sys.argv[1], encoding="utf-8") as handle:
    for raw in handle:
        line = raw.strip()
        if not line.startswith("data:"):
            continue
        try:
            payload = json.loads(line[5:].strip())
        except json.JSONDecodeError:
            continue
        event_type = payload.get("event_type")
        if event_type in {"awaiting_signoff", "escalated", "signed_off", "failed"}:
            status = event_type
print(status)
PY
}

step "Project $PROJECT, region $REGION"
gcloud config set project "$PROJECT" >/dev/null
PN=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')

step "Enabling APIs"
gcloud services enable \
  run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  aiplatform.googleapis.com storage.googleapis.com iam.googleapis.com \
  secretmanager.googleapis.com

step "Service account sa-agents (Vertex, index, and Secret Manager access)"
gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 \
  || gcloud iam service-accounts create sa-agents --display-name "Agents (rag and research APIs)"
gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$SA" \
  --role roles/aiplatform.user --condition=None -q >/dev/null
gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$SA" \
  --role roles/secretmanager.secretAccessor --condition=None -q >/dev/null

step "Build permissions for source deploys (default compute account)"
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member "serviceAccount:${PN}-compute@developer.gserviceaccount.com" \
  --role roles/run.builder --condition=None -q >/dev/null \
  || echo "  (could not grant roles/run.builder; continuing, the build may still work)"

step "Creating idempotent authentication secrets"
create_random_secret auth-secret
create_random_secret service-key
create_demo_users_secret

step "Private index bucket gs://$BUCKET"
gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 \
  || gcloud storage buckets create "gs://$BUCKET" --location "$REGION" \
       --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member "serviceAccount:$SA" \
  --role roles/storage.objectViewer >/dev/null
# litrag-index.zip (built from copyrighted papers) is private and not shipped here; build your own with `python -m litrag`.
unzip -q "$HERE/litrag-index.zip" -d "$TMP/idx"
gcloud storage rsync -r "$TMP/idx/index" "gs://$BUCKET/index"
gcloud storage ls "gs://$BUCKET/index/meta.json" >/dev/null

step "Deploying rag-api (Cloud Build builds the image; first build takes several minutes)"
gcloud run deploy rag-api --source "$HERE/rag-api" --region "$REGION" --quiet \
  --service-account "$SA" --allow-unauthenticated \
  --memory 2Gi --cpu 2 --cpu-boost --timeout 300 --concurrency 20 \
  --min-instances 0 --max-instances 3 --session-affinity \
  --set-env-vars "GEMINI_MODEL=$GEMINI_MODEL,GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=$GEMINI_LOCATION,LITRAG_INDEX_URI=gs://$BUCKET/index,CORS_ORIGINS=*" \
  --set-secrets "AUTH_SECRET=auth-secret:latest,SERVICE_KEY=service-key:latest,DEMO_USERS=demo-users:latest"
API_URL=$(gcloud run services describe rag-api --region "$REGION" --format 'value(status.url)')
echo "rag-api: $API_URL"
wait_for_health "rag-api" "$API_URL"

step "Deploying research-api from $RESEARCH_SRC"
gcloud run deploy research-api --source "$RESEARCH_SRC" --region "$REGION" --quiet \
  --service-account "$SA" --allow-unauthenticated \
  --memory 2Gi --cpu 2 --cpu-boost --timeout 3600 --concurrency 20 \
  --min-instances 0 --max-instances 1 --session-affinity \
  --set-env-vars "WEB_FLOW_BACKEND=adk,AGENT_MODEL=$GEMINI_MODEL,GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=global,REVIEW_MAX_ROUNDS=3,FLOW_INCLUDE_ETCH=false,WEB_CORS_ORIGINS=*,LITRAG_API_URL=$API_URL,WEB_RATE_LIMIT_PER_IP_PER_HOUR=10,WEB_DAILY_RUN_CAP=60,WEB_MAX_CONCURRENT_RUNS=1" \
  --set-secrets "AUTH_SECRET=auth-secret:latest,SERVICE_KEY=service-key:latest"
RESEARCH_URL=$(gcloud run services describe research-api --region "$REGION" --format 'value(status.url)')
echo "research-api: $RESEARCH_URL"
wait_for_health "research-api" "$RESEARCH_URL"

step "Deploying web (frontend from $FRONTEND_REPO@$FRONTEND_REF)"
git clone -q --depth 1 --branch "$FRONTEND_REF" "$FRONTEND_REPO" "$TMP/fe"
FE="$TMP/fe/frontend"
[[ -f "$FE/package-lock.json" ]] || {
  echo "$FRONTEND_REF does not contain frontend/package-lock.json" >&2
  exit 2
}
cp "$HERE/frontend-docker/Dockerfile" "$HERE/frontend-docker/nginx.conf" "$HERE/frontend-docker/.dockerignore" "$FE/"
printf 'REACT_APP_RAG_API_URL=%s\nREACT_APP_RESEARCH_API_URL=%s\n' "$API_URL" "$RESEARCH_URL" \
  > "$FE/.env.production"
cat > "$FE/.gcloudignore" <<'EOF'
.git
.playwright-cli/
node_modules/
build/
qa-screenshots/
playwright-report/
test-results/
.env*.local
EOF
gcloud run deploy web --source "$FE" --region "$REGION" --quiet --allow-unauthenticated \
  --memory 256Mi --cpu 1 --min-instances 0 --max-instances 3 --port 8080
WEB_URL=$(gcloud run services describe web --region "$REGION" --format 'value(status.url)')

step "Locking both API CORS policies to $WEB_URL"
# status.url is the exact regional run.app URL, not the project-number alias.
gcloud run services update rag-api --region "$REGION" --quiet \
  --update-env-vars "CORS_ORIGINS=$WEB_URL"
gcloud run services update research-api --region "$REGION" --quiet \
  --update-env-vars "WEB_CORS_ORIGINS=$WEB_URL"

step "Smoke tests"
curl -fsS -o /dev/null --max-time 30 -w "web: HTTP %{http_code}\n" "$WEB_URL"
wait_for_health "rag-api" "$API_URL"
wait_for_health "research-api" "$RESEARCH_URL"

# Write the login payload with Python so credentials containing quotes remain valid JSON.
SMOKE_USER="$SMOKE_USER" SMOKE_PASSWORD="$SMOKE_PASSWORD" python3 - > "$TMP/login.json" <<'PY'
import json
import os

print(json.dumps({
    "username": os.environ["SMOKE_USER"],
    "password": os.environ["SMOKE_PASSWORD"],
}))
PY
chmod 600 "$TMP/login.json"
login_code=$(curl -sS --max-time 30 -o "$TMP/login-response.json" \
  -w '%{http_code}' -X POST "$API_URL/v1/auth/login" \
  -H 'Content-Type: application/json' --data-binary "@$TMP/login.json")
[[ "$login_code" == 200 ]] || {
  echo "rag-api login smoke test failed (HTTP $login_code)" >&2
  exit 1
}
TOKEN=$(json_field "$TMP/login-response.json" token)
EXPIRES_AT=$(json_field "$TMP/login-response.json" expires_at)
[[ -n "$TOKEN" && "$EXPIRES_AT" =~ ^[0-9]+$ ]] || {
  echo "rag-api login response was missing a usable token or expiry" >&2
  exit 1
}
(( EXPIRES_AT > $(date +%s) )) || {
  echo "rag-api login returned an already-expired token" >&2
  exit 1
}
echo "rag-api login: ok"

search_code=$(curl -sS --max-time 60 -o "$TMP/search.json" -w '%{http_code}' \
  -X POST "$API_URL/v1/search" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query":"electron temperature global model","top_k":2}')
[[ "$search_code" == 200 ]] || {
  echo "authenticated rag-api search failed (HTTP $search_code)" >&2
  exit 1
}
python3 - "$TMP/search.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    result = json.load(handle)
if result.get("status") != "success" or not isinstance(result.get("results"), list):
    raise SystemExit("authenticated rag-api search returned an unexpected payload")
print(f"authenticated search: ok ({len(result['results'])} results)")
PY

unauth_code=$(curl -sS --max-time 30 -o /dev/null -w '%{http_code}' \
  -X POST "$API_URL/v1/search" -H 'Content-Type: application/json' \
  -d '{"query":"smoke unauthenticated","top_k":1}')
[[ "$unauth_code" == 401 ]] || {
  echo "unauthenticated rag-api search expected HTTP 401, got $unauth_code" >&2
  exit 1
}
echo "unauthenticated search rejected: ok (HTTP 401)"

create_code=$(curl -sS --max-time 60 -o "$TMP/run.json" -w '%{http_code}' \
  -X POST "$RESEARCH_URL/runs" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"preset_id":"good_argon_baseline"}')
[[ "$create_code" == 201 ]] || {
  echo "research-api run creation failed (HTTP $create_code)" >&2
  exit 1
}
RUN_ID=$(json_field "$TMP/run.json" run_id)
EVENTS_URL=$(json_field "$TMP/run.json" events_url)
[[ -n "$RUN_ID" && -n "$EVENTS_URL" ]] || {
  echo "research-api run response was missing run_id or events_url" >&2
  exit 1
}
echo "research-api smoke run: $RUN_ID"

# The server intentionally keeps the stream open at awaiting_signoff, so stop reading client-side.
curl -sS -N --max-time 330 "$RESEARCH_URL$EVENTS_URL" \
  -H "Authorization: Bearer $TOKEN" > "$TMP/events.sse" 2>"$TMP/events.error" &
events_pid=$!
events_deadline=$((SECONDS + SMOKE_RUN_TIMEOUT_SECONDS))
stream_done=0
while kill -0 "$events_pid" 2>/dev/null; do
  if grep -Eq '"event_type"[[:space:]]*:[[:space:]]*"(awaiting_signoff|escalated|signed_off|failed)"' \
    "$TMP/events.sse" 2>/dev/null; then
    stream_done=1
    kill "$events_pid" 2>/dev/null || true
    break
  fi
  if (( SECONDS >= events_deadline )); then
    kill "$events_pid" 2>/dev/null || true
    break
  fi
  sleep 1
done
wait "$events_pid" 2>/dev/null || true

RUN_STATUS=$(terminal_run_status "$TMP/events.sse")
if [[ "$stream_done" == 1 && "$RUN_STATUS" == awaiting_signoff ]]; then
  echo "research-api run reached: awaiting_signoff"
elif [[ "$stream_done" == 1 && "$RUN_STATUS" == escalated ]]; then
  echo "research-api run reached: escalated"
else
  echo "research-api run did not reach awaiting_signoff or escalated within ${SMOKE_RUN_TIMEOUT_SECONDS}s (last terminal event: ${RUN_STATUS:-none})" >&2
  exit 1
fi

printf '\nDONE\n  App (live URL):          %s\n  Literature API:          %s\n  Validation API:          %s\n' \
  "$WEB_URL" "$API_URL" "$RESEARCH_URL"
