#!/bin/bash
# cloudrun_seed_probe/deploy.sh
# Builds and deploys the ConspiracyComments Seed Claim Probe Service to GCP Cloud Run.

set -e

# Change directory to the directory containing this script so gcloud builds submit can find the Dockerfile
cd "$(dirname "$0")"

PROJECT_ID="sapient-zodiac-502400-k2"
SERVICE_NAME="drilldown-seed-probe"
REGION="us-central1"
IMAGE_TAG="us-central1-docker.pkg.dev/${PROJECT_ID}/cloud-run-source-deploy/${SERVICE_NAME}:latest"
SERVICE_ACCOUNT="drilldown-api-sa@sapient-zodiac-502400-k2.iam.gserviceaccount.com"
BUCKET_NAME="sapient-zodiac-502400-k2-conspiracy-data"

echo "=== Step 1: Submitting build to Google Cloud Build ==="
gcloud builds submit --tag "${IMAGE_TAG}" --project "${PROJECT_ID}" --timeout="15m"

echo "=== Step 2: Deploying to Cloud Run ==="
gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE_TAG}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --platform managed \
  --memory 2Gi \
  --cpu 1 \
  --service-account "${SERVICE_ACCOUNT}" \
  --allow-unauthenticated \
  --set-env-vars="GCS_BUCKET_NAME=${BUCKET_NAME}" \
  --timeout="10m"

echo "=== Deployment Successful! ==="
gcloud run services describe "${SERVICE_NAME}" --project "${PROJECT_ID}" --region "${REGION}" --format="value(status.url)"
