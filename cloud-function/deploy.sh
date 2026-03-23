#!/bin/bash

# ═══════════════════════════════════════════════════════════════
# SOCRadar → Chronicle Cloud Function Deployment
# ═══════════════════════════════════════════════════════════════
#
# Prerequisites:
#   - gcloud CLI installed and authenticated
#   - GCP project with Cloud Functions, Cloud Scheduler, GCS APIs enabled
#   - SOCRadar API key and Company ID
#   - Chronicle Feed endpoint URL, API key, and secret
#
# ═══════════════════════════════════════════════════════════════

# ── 1. Set your variables ──
PROJECT_ID="your-gcp-project-id"
REGION="europe-west1"
FUNCTION_NAME="socradar-to-chronicle"
GCS_BUCKET="socradar-chronicle-state"

# SOCRadar credentials
SOCRADAR_API_KEY="YOUR_SOCRADAR_API_KEY"
SOCRADAR_COMPANY_ID="YOUR_SOCRADAR_COMPANY_ID"

# Chronicle credentials
CHRONICLE_FEED_URL="https://eu-chronicle.googleapis.com/v1alpha/projects/980739849191/locations/eu/instances/92ea4dab-a49a-4fe7-8f6a-bb8c2c4fe082/feeds/YOUR_FEED_ID:importPushLogs"
CHRONICLE_API_KEY="YOUR_CHRONICLE_API_KEY"
CHRONICLE_SECRET="YOUR_CHRONICLE_SECRET"

# ── 2. Create GCS bucket for state ──
echo "Creating GCS bucket for state..."
gcloud storage buckets create gs://${GCS_BUCKET} \
  --project=${PROJECT_ID} \
  --location=${REGION} \
  --uniform-bucket-level-access

# ── 3. Deploy Cloud Function ──
echo "Deploying Cloud Function..."
gcloud functions deploy ${FUNCTION_NAME} \
  --project=${PROJECT_ID} \
  --region=${REGION} \
  --runtime=python312 \
  --trigger-http \
  --allow-unauthenticated \
  --entry-point=socradar_to_chronicle \
  --timeout=120 \
  --memory=256MB \
  --source=. \
  --set-env-vars="SOCRADAR_API_KEY=${SOCRADAR_API_KEY},SOCRADAR_COMPANY_ID=${SOCRADAR_COMPANY_ID},CHRONICLE_FEED_URL=${CHRONICLE_FEED_URL},CHRONICLE_API_KEY=${CHRONICLE_API_KEY},CHRONICLE_SECRET=${CHRONICLE_SECRET},GCS_BUCKET=${GCS_BUCKET}"

# ── 4. Create Cloud Scheduler job (every 5 minutes) ──
echo "Creating Cloud Scheduler job..."
FUNCTION_URL=$(gcloud functions describe ${FUNCTION_NAME} \
  --project=${PROJECT_ID} \
  --region=${REGION} \
  --format='value(url)')

gcloud scheduler jobs create http socradar-chronicle-sync \
  --project=${PROJECT_ID} \
  --location=${REGION} \
  --schedule="*/5 * * * *" \
  --uri="${FUNCTION_URL}" \
  --http-method=GET \
  --description="Fetch SOCRadar incidents and push to Chronicle every 5 minutes"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Deployment complete!"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "  Cloud Function: ${FUNCTION_NAME}"
echo "  Schedule: Every 5 minutes"
echo "  State bucket: gs://${GCS_BUCKET}"
echo ""
echo "  Test manually:"
echo "    curl ${FUNCTION_URL}"
echo ""
echo "  View logs:"
echo "    gcloud functions logs read ${FUNCTION_NAME} --region=${REGION}"
echo ""
