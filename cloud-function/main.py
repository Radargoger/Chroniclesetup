import functions_framework
import requests
import json
import os
from datetime import datetime, timedelta, timezone
from google.cloud import storage

# ═══════════════════════════════════════════════════════════════
# SOCRadar → Google Chronicle SecOps
# Google Cloud Function (runs every 5 minutes via Cloud Scheduler)
#
# Flow:
#   1. Read last poll timestamp from GCS state file
#   2. Fetch new incidents from SOCRadar API v2
#   3. Push each incident to Chronicle via importPushLogs
#   4. Update last poll timestamp in GCS
#
# Environment Variables (set in Cloud Function config):
#   SOCRADAR_API_KEY        - SOCRadar API key
#   SOCRADAR_COMPANY_ID     - SOCRadar Company ID
#   CHRONICLE_FEED_URL      - Chronicle Push Feed endpoint URL
#   CHRONICLE_API_KEY       - Chronicle API key
#   CHRONICLE_SECRET        - Chronicle Feed secret key
#   GCS_BUCKET              - GCS bucket for state file
#   GCS_STATE_FILE          - State file name (default: socradar_last_poll.json)
# ═══════════════════════════════════════════════════════════════


# ── Configuration ──
SOCRADAR_API_KEY = os.environ.get("SOCRADAR_API_KEY", "YOUR_SOCRADAR_API_KEY")
SOCRADAR_COMPANY_ID = os.environ.get("SOCRADAR_COMPANY_ID", "YOUR_COMPANY_ID")
SOCRADAR_BASE_URL = "https://platform.socradar.com/api/v2"

CHRONICLE_FEED_URL = os.environ.get("CHRONICLE_FEED_URL",
    "https://eu-chronicle.googleapis.com/v1alpha/projects/980739849191/locations/eu/instances/92ea4dab-a49a-4fe7-8f6a-bb8c2c4fe082/feeds/YOUR_FEED_ID:importPushLogs")
CHRONICLE_API_KEY = os.environ.get("CHRONICLE_API_KEY", "YOUR_CHRONICLE_API_KEY")
CHRONICLE_SECRET = os.environ.get("CHRONICLE_SECRET", "YOUR_CHRONICLE_SECRET")

GCS_BUCKET = os.environ.get("GCS_BUCKET", "socradar-chronicle-state")
GCS_STATE_FILE = os.environ.get("GCS_STATE_FILE", "socradar_last_poll.json")

# How far back to look on first run (no state file)
INITIAL_LOOKBACK_HOURS = 24


def get_last_poll_time():
    """Read last poll timestamp from GCS."""
    try:
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET)
        blob = bucket.blob(GCS_STATE_FILE)

        if blob.exists():
            state = json.loads(blob.download_as_text())
            return state.get("last_poll_time")
    except Exception as e:
        print(f"[WARN] Could not read state from GCS: {e}")

    # First run - look back INITIAL_LOOKBACK_HOURS
    return (datetime.now(timezone.utc) - timedelta(hours=INITIAL_LOOKBACK_HOURS)).strftime("%Y-%m-%d %H:%M:%S")


def save_last_poll_time(timestamp):
    """Save last poll timestamp to GCS."""
    try:
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET)
        blob = bucket.blob(GCS_STATE_FILE)

        state = {
            "last_poll_time": timestamp,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        blob.upload_from_string(json.dumps(state), content_type="application/json")
        print(f"[INFO] State saved: last_poll_time={timestamp}")
    except Exception as e:
        print(f"[ERROR] Could not save state to GCS: {e}")


def fetch_socradar_incidents(start_date):
    """Fetch incidents from SOCRadar API v2."""
    url = f"{SOCRADAR_BASE_URL}/company/{SOCRADAR_COMPANY_ID}/incidents"

    headers = {
        "API-Key": SOCRADAR_API_KEY,
        "Content-Type": "application/json"
    }

    params = {
        "start_date": start_date,
        "limit": 50,
        "page": 1
    }

    all_incidents = []

    while True:
        try:
            print(f"[INFO] Fetching SOCRadar incidents page {params['page']} from {start_date}")
            response = requests.get(url, headers=headers, params=params, timeout=30)

            if response.status_code == 429:
                print("[WARN] SOCRadar rate limit hit, stopping pagination")
                break

            if response.status_code != 200:
                print(f"[ERROR] SOCRadar API returned {response.status_code}: {response.text[:500]}")
                break

            data = response.json()

            if not data.get("is_success"):
                print(f"[ERROR] SOCRadar API error: {data.get('message')}")
                break

            incidents = data.get("data", [])

            if not incidents:
                print(f"[INFO] No more incidents on page {params['page']}")
                break

            all_incidents.extend(incidents)
            print(f"[INFO] Fetched {len(incidents)} incidents on page {params['page']}")

            # Check if there are more pages
            if len(incidents) < params["limit"]:
                break

            params["page"] += 1

        except Exception as e:
            print(f"[ERROR] Failed to fetch from SOCRadar: {e}")
            break

    return all_incidents


def transform_incident(incident):
    """Transform SOCRadar incident to the flat JSON format our Chronicle parser expects."""
    alarm_type_details = incident.get("alarm_type_details", {})
    content_obj = incident.get("content", {})

    # Stringify content object for dynamic handling
    try:
        content_str = json.dumps(content_obj) if isinstance(content_obj, dict) else str(content_obj)
    except Exception:
        content_str = str(content_obj)

    # Build tags string
    tags = incident.get("tags", [])
    tags_str = ", ".join(tags) if isinstance(tags, list) else str(tags)

    # Build compliance string
    compliance_list = alarm_type_details.get("alarm_compliance_list", [])
    if isinstance(compliance_list, list):
        compliance_str = ", ".join([
            f"{c.get('name', '')} ({c.get('control_item', '')})"
            for c in compliance_list
        ])
    else:
        compliance_str = str(compliance_list)

    return {
        "alarm_id": incident.get("alarm_id"),
        "alarm_risk_level": incident.get("alarm_risk_level", ""),
        "alarm_asset": incident.get("alarm_asset", ""),
        "alarm_text": incident.get("alarm_text", ""),
        "alarm_title": alarm_type_details.get("alarm_generic_title", ""),
        "alarm_main_type": alarm_type_details.get("alarm_main_type", ""),
        "alarm_sub_type": alarm_type_details.get("alarm_sub_type", ""),
        "status": incident.get("status", ""),
        "approved_by": incident.get("approved_by", ""),
        "date": incident.get("date", ""),
        "notification_id": incident.get("notification_id"),
        "tags": tags_str,
        "content": content_str,
        "mitigation_plan": alarm_type_details.get("alarm_default_mitigation_plan", ""),
        "compliance": compliance_str
    }


def push_to_chronicle(payload):
    """Push a single log entry to Chronicle via importPushLogs."""
    url = f"{CHRONICLE_FEED_URL}?key={CHRONICLE_API_KEY}&secret={CHRONICLE_SECRET}"

    headers = {
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        if response.status_code == 200:
            return True
        else:
            print(f"[ERROR] Chronicle push failed ({response.status_code}): {response.text[:300]}")
            return False

    except Exception as e:
        print(f"[ERROR] Chronicle push exception: {e}")
        return False


@functions_framework.http
def socradar_to_chronicle(request):
    """Main Cloud Function entry point (HTTP trigger for Cloud Scheduler)."""
    print("=" * 60)
    print(f"[START] SOCRadar → Chronicle sync at {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # 1. Get last poll time
    last_poll = get_last_poll_time()
    print(f"[INFO] Polling incidents since: {last_poll}")

    # 2. Fetch new incidents from SOCRadar
    incidents = fetch_socradar_incidents(last_poll)
    print(f"[INFO] Total incidents fetched: {len(incidents)}")

    if not incidents:
        print("[INFO] No new incidents. Done.")
        return json.dumps({"status": "ok", "incidents_fetched": 0, "incidents_pushed": 0}), 200

    # 3. Transform and push each incident to Chronicle
    pushed = 0
    failed = 0
    latest_date = last_poll

    for incident in incidents:
        # Transform to flat JSON
        transformed = transform_incident(incident)

        # Push to Chronicle
        if push_to_chronicle(transformed):
            pushed += 1
            # Track latest incident date for state
            inc_date = incident.get("date", "")
            if inc_date > latest_date:
                latest_date = inc_date
        else:
            failed += 1

    # 4. Update last poll time
    if pushed > 0:
        save_last_poll_time(latest_date)

    result = {
        "status": "ok",
        "incidents_fetched": len(incidents),
        "incidents_pushed": pushed,
        "incidents_failed": failed,
        "last_poll_updated_to": latest_date
    }

    print(f"[DONE] {json.dumps(result)}")
    return json.dumps(result), 200


# ═══════════════════════════════════════════════════════════════
# Local testing
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Running locally...")
    result, status = socradar_to_chronicle(None)
    print(f"Status: {status}")
    print(f"Result: {result}")
