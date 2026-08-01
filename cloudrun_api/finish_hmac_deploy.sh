#!/bin/bash
# One-shot: wait for HMAC key creation to succeed (org policy propagation),
# then redeploy Cloud Run with the HMAC creds wired in, then smoke-test.
# Progress goes to stderr (visible in the task's output file); only ONE
# final line goes to stdout, to minimize Monitor notifications.
set -uo pipefail
cd /Users/nash/Projects/ConspiracyComments

SA="drilldown-api-sa@sapient-zodiac-502400-k2.iam.gserviceaccount.com"
PROJECT="sapient-zodiac-502400-k2"

HMAC_OUT=""
for i in $(seq 1 40); do
  HMAC_OUT=$(gcloud storage hmac create "$SA" --project="$PROJECT" 2>&1)
  if echo "$HMAC_OUT" | grep -q "Access ID"; then
    echo "HMAC key created on attempt $i" >&2
    break
  fi
  echo "attempt $i failed, waiting 20s..." >&2
  sleep 20
done

if ! echo "$HMAC_OUT" | grep -q "Access ID"; then
  echo "FINAL: HMAC key creation never succeeded after 40 attempts (~13min). Org policy may not have propagated, or something else is wrong -- needs a look."
  exit 1
fi

KEY_ID=$(echo "$HMAC_OUT" | grep "Access ID" | awk '{print $3}')
SECRET=$(echo "$HMAC_OUT" | grep "Secret" | awk '{print $2}')

if [ -z "$KEY_ID" ] || [ -z "$SECRET" ]; then
  echo "FINAL: HMAC key created but couldn't parse KEY_ID/SECRET from output: $HMAC_OUT"
  exit 1
fi
echo "Parsed HMAC key id: $KEY_ID" >&2

DEPLOY_OUT=$(gcloud run deploy drilldown-api \
  --source cloudrun_api/ \
  --project="$PROJECT" \
  --region=us-central1 \
  --service-account="$SA" \
  --memory=1.5Gi \
  --cpu=1 \
  --max-instances=3 \
  --allow-unauthenticated \
  --add-volume=name=gcs-data,type=cloud-storage,bucket=sapient-zodiac-502400-k2-conspiracy-data,readonly=true \
  --add-volume-mount=volume=gcs-data,mount-path=/mnt/gcs \
  --set-env-vars="API_TOKEN=wCcvTs2IfGhWn64xDhZ8CQxS8Fa5uMzS,DUCKDB_MEMORY_LIMIT=1200MB,GCS_HMAC_KEY_ID=${KEY_ID},GCS_HMAC_SECRET=${SECRET}" \
  2>&1)
echo "$DEPLOY_OUT" >&2

if ! echo "$DEPLOY_OUT" | grep -q "has been deployed and is serving"; then
  echo "FINAL: Cloud Run deploy failed. See task output file for the full gcloud run deploy log."
  exit 1
fi

echo "Deploy succeeded, smoke-testing search..." >&2
SEARCH_RESULT=$(curl -s -m 45 -w "\nHTTP_CODE=%{http_code} TIME=%{time_total}" \
  "https://drilldown-api-887655513733.us-central1.run.app/api/ats_search?q=chemtrails&limit=3&token=wCcvTs2IfGhWn64xDhZ8CQxS8Fa5uMzS")
echo "$SEARCH_RESULT" >&2

if echo "$SEARCH_RESULT" | grep -q "HTTP_CODE=200"; then
  TIME_TAKEN=$(echo "$SEARCH_RESULT" | grep -o "TIME=[0-9.]*" | cut -d= -f2)
  echo "FINAL: SUCCESS. HMAC + gs:// ATTACH works. Search query took ${TIME_TAKEN}s (was 78s before, hung indefinitely over FUSE before that)."
else
  echo "FINAL: Deploy succeeded but search smoke-test did not return 200. Check task output file for the raw response/logs."
fi
