# SOCRadar → Chronicle Cloud Function

Serverless Google Cloud Function that automatically polls SOCRadar's Incidents API every 5 minutes and pushes new incidents to Chronicle via the Push Feed endpoint.

## How It Works

1. Cloud Scheduler triggers the function every 5 minutes
2. Function reads the last poll timestamp from a GCS state file
3. Fetches new incidents from SOCRadar API v2 (with pagination)
4. Transforms each incident to the flat JSON format matching the Chronicle parser
5. Pushes each incident to Chronicle via `importPushLogs`
6. Saves the updated poll timestamp to GCS

## Prerequisites

- Google Cloud project with these APIs enabled:
  - Cloud Functions
  - Cloud Scheduler
  - Cloud Storage
- SOCRadar API Key and Company ID
- Chronicle Feed endpoint URL, API Key, and Secret Key

## Deployment

### 1. Edit `deploy.sh`

Replace the placeholder values:

```bash
PROJECT_ID="your-gcp-project-id"
SOCRADAR_API_KEY="your-socradar-api-key"
SOCRADAR_COMPANY_ID="your-company-id"
CHRONICLE_FEED_URL="your-chronicle-feed-endpoint"
CHRONICLE_API_KEY="your-chronicle-api-key"
CHRONICLE_SECRET="your-chronicle-secret"
```

### 2. Run deployment

```bash
chmod +x deploy.sh
./deploy.sh
```

This will:
- Create a GCS bucket for state management
- Deploy the Cloud Function
- Create a Cloud Scheduler job running every 5 minutes

### 3. Test manually

```bash
curl YOUR_FUNCTION_URL
```

### 4. View logs

```bash
gcloud functions logs read socradar-to-chronicle --region=europe-west1
```

## Environment Variables

| Variable | Description |
|---|---|
| `SOCRADAR_API_KEY` | SOCRadar API key |
| `SOCRADAR_COMPANY_ID` | SOCRadar Company ID |
| `CHRONICLE_FEED_URL` | Chronicle Push Feed endpoint URL |
| `CHRONICLE_API_KEY` | Chronicle API key |
| `CHRONICLE_SECRET` | Chronicle Feed secret key |
| `GCS_BUCKET` | GCS bucket name for state file |
| `GCS_STATE_FILE` | State file name (default: `socradar_last_poll.json`) |

## Deduplication

The function tracks the last successful poll timestamp in a GCS state file. On each run, it only fetches incidents newer than the last poll time, preventing duplicates. On first run (no state file), it looks back 24 hours.
