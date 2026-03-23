# SOCRadar Integration for Google Chronicle SecOps

Native integration between **SOCRadar Extended Threat Intelligence (XTI)** and **Google Chronicle SecOps** (SIEM). Enables real-time ingestion of SOCRadar CTI alarms into Chronicle with automated UDM normalization and YARA-L based detection.

## Overview

This integration provides:

- **Webhook Push Feed** — Real-time alarm forwarding from SOCRadar to Chronicle
- **Custom Parser** — Normalizes SOCRadar JSON into Chronicle UDM (Unified Data Model)
- **Dynamic Content Handling** — Supports all 200+ SOCRadar alarm types without parser modifications
- **YARA-L Detection Rule** — Severity-based risk scoring and automated alerting
- **Cloud Function (Optional)** — Serverless auto-pull from SOCRadar Incidents API every 5 minutes

## Architecture

```
┌──────────────┐     Webhook POST      ┌─────────────────────┐
│   SOCRadar   │ ──────────────────────►│  Chronicle SecOps   │
│   CTI/XTI    │     (JSON payload)     │                     │
└──────────────┘                        │  Push Feed          │
                                        │    ↓                │
┌──────────────┐     Cloud Function     │  Custom Parser      │
│  SOCRadar    │ ──────────────────────►│    ↓                │
│  API v2      │   (every 5 minutes)    │  UDM Event          │
└──────────────┘                        │    ↓                │
                                        │  YARA-L Rule        │
                                        │    ↓                │
                                        │  Alert / Case       │
                                        └─────────────────────┘
```

## Supported Alarm Types

The integration dynamically handles all SOCRadar alarm types, including but not limited to:

| Category | Alarm Types |
|----------|-------------|
| **Fraud Protection** | Creditcard Leak, BIN Leak |
| **Dark Web Monitoring** | Credential Leak, Data Leak, Blackmarket Data |
| **Brand Protection** | Phishing Domain, Brand Mention, Impersonating Domain |
| **Attack Surface Management** | Vulnerability, Exposed Service, SSL Certificate |
| **Cyber Threat Intelligence** | Malware, Botnet, APT Activity |
| **Supply Chain Security** | Third-party Risk, Vendor Breach |

> **No parser changes required for new alarm types.** The `content` field is handled as a dynamic JSON string.

## Quick Start

### Prerequisites

- Google Chronicle SecOps instance
- SOCRadar CTI/XTI platform access
- SOCRadar API Key and Company ID

### Method 1: Webhook (Real-time)

1. **Create a Feed in Chronicle**
   - Settings → SIEM Settings → Feeds → Add New Feed
   - Feed Name: `SOCRadar Webhook`
   - Source Type: `Webhook`
   - Log Type: `SOCRADAR_INCIDENTS_CUSTOM` ([create custom log type](#creating-custom-log-type) if not available)
   - Submit → Generate Secret Key → Save endpoint URL and secret

2. **Create the Custom Parser**
   - Settings → SIEM Settings → Parsers → Create Parser
   - Log Source: `SOCRADAR_INCIDENTS_CUSTOM`
   - Select "Start with Raw Logs Only"
   - Paste the contents of [`parser/socradar_chronicle_parser.conf`](parser/socradar_chronicle_parser.conf)
   - Preview with [`test/sample_logs.json`](test/sample_logs.json) → Validate → Submit

3. **Configure SOCRadar Webhook**
   - In SOCRadar: Settings → Notifications → Webhook
   - URL: `CHRONICLE_ENDPOINT?key=API_KEY&secret=SECRET`
   - Payload Template: Use [`webhook/payload_template.json`](webhook/payload_template.json)

4. **Enable Detection Rule**
   - Detection → Rules → New
   - Paste [`detection-rules/socradar_alarm.yaral`](detection-rules/socradar_alarm.yaral)
   - Save → Enable for Live Data → Enable for Alerting

### Method 2: Cloud Function (Auto-pull)

Deploy the included Google Cloud Function to automatically poll SOCRadar's Incidents API every 5 minutes. See [`cloud-function/README.md`](cloud-function/README.md) for deployment instructions.

## Creating Custom Log Type

If `SOCRADAR_INCIDENTS_CUSTOM` is not in the log type dropdown:

1. Settings → SIEM Settings → Parsers → Create Parser
2. Click "Request a Log Type" at the bottom of the log source dropdown
3. Select "Create a custom log type on your own"
4. Vendor / Product: `SOCRadar`
5. Log Type: `SOCRADAR_INCIDENTS`
6. Click "Create Log Type" → final name will be `SOCRADAR_INCIDENTS_CUSTOM`

## UDM Field Mapping

### Core Fields

| SOCRadar Field | UDM Field | Description |
|---|---|---|
| _(static)_ | `metadata.vendor_name` | `SOCRadar` |
| _(static)_ | `metadata.product_name` | `SOCRadar CTI` |
| _(static)_ | `metadata.event_type` | `GENERIC_EVENT` |
| `date` | `metadata.event_timestamp` | Alarm timestamp (ISO 8601) |
| `alarm_title` | `metadata.description` | Human-readable alarm title |
| `alarm_sub_type` | `metadata.product_event_type` | Alarm sub-type (e.g., `Credential Leak`) |
| _(static)_ | `principal.hostname` | `socradar-cti` |
| _(static)_ | `principal.application` | `SOCRadar CTI Platform` |

### Security Result

| SOCRadar Field | UDM Field | Description |
|---|---|---|
| `alarm_risk_level` | `security_result.severity` | `CRITICAL` / `HIGH` / `MEDIUM` / `LOW` |
| `alarm_title` | `security_result.summary` | Alarm summary |
| `alarm_text` | `security_result.description` | Full alarm description |
| `alarm_main_type` | `security_result.category_details[]` | Category (e.g., `Fraud Protection`) |

### Detection Fields

| Key | Source |
|---|---|
| `alarm_id` | SOCRadar alarm ID |
| `alarm_status` | `OPEN` / `RESOLVED` / `CLOSED` |
| `approved_by` | Approval source |
| `notification_id` | SOCRadar notification ID |
| `alarm_sub_type` | Alarm sub-type |

### Additional Fields

| Key | Description |
|---|---|
| `content` | **Dynamic JSON string** — contains all alarm-type-specific data |
| `alarm_asset` | Affected asset |
| `tags` | Alarm tags |
| `alarm_main_type` | Main category |
| `alarm_sub_type` | Sub category |
| `mitigation_plan` | Recommended actions |
| `compliance_frameworks` | Relevant compliance frameworks |
| `alarm_text` | Raw alarm text |

### Dynamic Content Field

The `content` field stores the entire SOCRadar content object as a JSON string. This varies per alarm type:

| Alarm Type | Content Contains |
|---|---|
| Creditcard Leak | `bank`, `card_number`, `bin_number`, `cvv`, `country` |
| Credential Leak | `email`, `password_hash`, `source`, `domain`, `leak_date` |
| Phishing Domain | `domain`, `registrar`, `ip_address`, `ssl_cert`, `similarity_score` |
| Vulnerability | `ip_address`, `port`, `service`, `cve_id`, `cvss_score` |
| Data Leak | `paste_url`, `source`, `keywords_matched`, `snippet` |
| Brand Mention | `platform`, `post_url`, `author`, `sentiment`, `followers` |

Content can be searched via regex in UDM Search:
```
additional.fields["content"] = /CVE-2021-44228/
```

## YARA-L Detection Rule

The included detection rule creates alerts for all SOCRadar alarms with dynamic risk scoring:

| SOCRadar Severity | Risk Score | Chronicle Priority |
|---|---|---|
| CRITICAL | 95 | Immediate response |
| HIGH | 80 | High priority |
| MEDIUM | 50 | Standard triage |
| LOW | 25 | Low priority review |

## UDM Search Examples

```
// All SOCRadar events
metadata.vendor_name = "SOCRadar"

// Critical and High severity
metadata.vendor_name = "SOCRadar" AND
(security_result.severity = "CRITICAL" OR security_result.severity = "HIGH")

// Specific alarm type
metadata.vendor_name = "SOCRadar" AND metadata.product_event_type = "Credential Leak"

// Search within dynamic content
metadata.vendor_name = "SOCRadar" AND additional.fields["content"] = /company\.com/

// Search by alarm ID
security_result.detection_fields["alarm_id"] = "872"
```

## Validation Results

| Metric | Result |
|---|---|
| Log entries parsed | 11 |
| Successfully normalized | 11 (100%) |
| Failed log count | 0 |
| Invalid log count | 0 |
| on_error count | 0 |
| Avg parse duration | < 1ms |

## Repository Structure

```
├── README.md                          # This file
├── LICENSE
├── parser/
│   └── socradar_chronicle_parser.conf # Chronicle custom parser
├── webhook/
│   └── payload_template.json          # SOCRadar webhook payload template
├── detection-rules/
│   └── socradar_alarm.yaral           # YARA-L detection rule
├── cloud-function/
│   ├── README.md                      # Cloud Function deployment guide
│   ├── main.py                        # Cloud Function code
│   ├── requirements.txt               # Python dependencies
│   └── deploy.sh                      # One-command deployment script
├── test/
│   ├── sample_logs.json               # Sample logs for parser testing
│   ├── test_send.sh                   # Single alarm test script
│   └── test_send_all.sh               # Multi-alarm test script (5 types)
└── docs/
    └── integration_guide.docx         # Full integration guide document
```

## Support

- **SOCRadar Integration Support** : integration@socradar.io
- **Google Chronicle Documentation:** [https://cloud.google.com/chronicle/docs](https://cloud.google.com/chronicle/docs)
- **Issues:** Please reach out integration@socradar.io

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.
