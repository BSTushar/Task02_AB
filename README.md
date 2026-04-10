# Task_02: Database Discovery on EC2 Across AWS Accounts

**Discover databases (MySQL, PostgreSQL, MongoDB) on EC2 across AWS accounts — no SSH — and expose results via a REST API and optional web UI.**

> **Confidentiality Notice:** This project is confidential and proprietary to AIRBUS. Unauthorized distribution, disclosure, or use is strictly prohibited.

[![AWS](https://img.shields.io/badge/AWS-Lambda%20%7C%20SSM%20%7C%20S3-orange)](https://aws.amazon.com)
[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Repository:** [github.com/BSTushar/Task02_AB](https://github.com/BSTushar/Task02_AB)

---

## Overview

This proof-of-concept runs a **read-only** probe on **SSM-managed Linux** instances (per account/region), collects engine metadata (type, version, sizing hints, tags, instance type), writes a **single S3 snapshot** (`discovery/inventory.json` by default), and serves it through **API Gateway + Lambda**.

### Key Features

| Feature | Description |
|--------|-------------|
| **Cross-account** | Management account assumes **`DBDiscoverySpokeRole`** in spokes (STS). |
| **No SSH** | **SSM Run Command** + custom document runs `discovery_python.py`. |
| **FinOps-friendly store** | One JSON object per run in S3 (not per-row DynamoDB for this POC). |
| **REST API** | Regions, accounts, instances grouped with DBs; **CORS** enabled for browsers. |
| **Optional UI** | `inventory_ui.html` — region/account dashboard; set **`BASE_URL`** to your API stage. |
| **Spoke bootstrap** | CloudFormation **StackSet** template under `automation/` for roles + SSM document. |

### Architecture

```
Management Account                           Spoke Accounts
┌────────────────────────┐                  ┌─────────────────────────┐
│ EventBridge (schedule) │                 │ EC2 (Linux) + SSM Agent │
│          ↓             │   AssumeRole    │          ↓              │
│  db-discovery Lambda ──┼────────────────►│  SSM SendCommand        │
│          ↓             │                  │          ↓              │
│  S3 : inventory.json   │                  │  discovery_python.py    │
│          ↑             │                  └─────────────────────────┘
│  db-discovery-api Lambda ◄── GET (read same S3 object)
│          ↑
│  API Gateway (HTTP/REST)
└────────────────────────┘
```

---

## Quick Start

1. **Clone**
   ```bash
   git clone https://github.com/BSTushar/Task02_AB.git
   cd Task02_AB
   ```

2. **Deploy / configure** — Follow [FULL_SETUP_IN_ORDER.md](FULL_SETUP_IN_ORDER.md) (S3, Lambdas, API, IAM, spokes). Spoke bulk install: [automation/STACKSET_AUTOMATION.md](automation/STACKSET_AUTOMATION.md).

3. **Run discovery** (management profile, adjust function/region):
   ```bash
   aws lambda invoke --function-name db-discovery --payload "{}" response.json --cli-binary-format raw-in-base64-out
   type response.json    # Windows
   ```

4. **Call the API** (replace host with your `execute-api` URL and stage):
   ```bash
   curl "https://YOUR_API_ID.execute-api.REGION.amazonaws.com/prod/health"
   curl "https://YOUR_API_ID.execute-api.REGION.amazonaws.com/prod/regions"
   curl "https://YOUR_API_ID.execute-api.REGION.amazonaws.com/prod/accounts?region=ap-south-1"
   curl "https://YOUR_API_ID.execute-api.REGION.amazonaws.com/prod/accounts/123456789012/instances?region=ap-south-1"
   ```

5. **Optional UI** — Open `inventory_ui.html` locally or host statically; set **`BASE_URL`** at the top of the file to the same API **stage URL** (no trailing slash).

---

## Documentation Map

| Document | Purpose |
|----------|---------|
| [FULL_SETUP_IN_ORDER.md](FULL_SETUP_IN_ORDER.md) | Step-by-step setup (console-oriented) |
| [COST_AND_STOP_RESOURCES.md](COST_AND_STOP_RESOURCES.md) | Stop EC2, disable EventBridge, teardown notes |
| [DEMO_RUNBOOK_FRIDAY.md](DEMO_RUNBOOK_FRIDAY.md) | Demo-day checklist, architecture pitch, Q&A (new account / new EC2) |
| [automation/STACKSET_AUTOMATION.md](automation/STACKSET_AUTOMATION.md) | StackSet create/update, OU vs account targets |
| [automation/EVENTBRIDGE_DISCOVERY_SCHEDULE.md](automation/EVENTBRIDGE_DISCOVERY_SCHEDULE.md) | Deploy EventBridge schedule → `db-discovery` (IaC) |
| [api/api-gateway-config.md](api/api-gateway-config.md) | Example routes and curl |
| [automation/TIER3_RESEARCH_SHEET.md](automation/TIER3_RESEARCH_SHEET.md) | Tier 3 / automation research notes |

---

## Project Structure

| Path | Description |
|------|-------------|
| `iam/` | IAM policies (trust, spoke role, Lambda, EC2 instance profile) |
| `ssm/` | `discovery_python.py`, SSM document JSON |
| `lambda/` | `discovery_handler.py`, `api_handler.py`, `lambda_function.py` (zip entry shim) |
| `schema/` | Example inventory record shape |
| `api/` | API Gateway notes |
| `automation/` | StackSet template, `discovery-eventbridge-schedule.yaml`, docs |
| `inventory_ui.html` | Browser dashboard (CORS + `BASE_URL`) |

---

## API Summary

Lambda returns **CORS** headers and handles **OPTIONS** for browser clients.

| Method | Resource | Description |
|--------|----------|-------------|
| GET | `/health` | Status and record count |
| GET | `/` or `/{stage}` | Small service index |
| GET | `/regions` | Distinct regions in the current S3 snapshot |
| GET | `/accounts` | All account IDs in snapshot, or filter with **`?region=`** (used by `inventory_ui.html`) |
| GET | `/regions/{region}/accounts` | Accounts that have rows in that region *(if this path is deployed on API Gateway)* |
| GET | `/accounts/{accountId}` | Flat records; optional **`?region=`** |
| GET | `/accounts/{accountId}/instances` | Instances + `databases[]`; **`?region=`** recommended |
| GET | `/databases` | All rows; optional **`?engine=`**, **`?account_id=`** |

> **Note:** If API Gateway only exposes a subset of paths, prefer **`GET /accounts?region=`** for region-scoped account lists — the Lambda supports it even when nested `/regions/.../accounts` is not wired.

Full detail: [api/api-gateway-config.md](api/api-gateway-config.md)

## Third-party integration (PCP portal / Airbus dashboard)

Use the API as a read-only data source for internal dashboards. Recommended patterns:

- **Direct client-side fetch** (quickest): dashboard frontend calls API Gateway endpoints
  - `GET /regions`
  - `GET /accounts?region=<region>`
  - `GET /accounts/{accountId}/instances?region=<region>`
- **Backend proxy** (preferred for enterprise): PCP/Airbus backend calls this API and exposes normalized JSON to UI clients.

### v2.3 API improvements

`/databases` now supports richer server-side filters so PCP/Airbus portals can request exactly what they need:

- `region=<aws-region>`
- `account_id=<12-digit-account-id>`
- `engine=<mysql|postgres|postgresql|mongodb|none>`
- `instance_id=<ec2-instance-id>`
- `discovery_status=<success|failed|...>`
- `ec2_state=<running|stopped|...>`

### Suggested contract for dashboard consumers

1. Load regions.
2. Load accounts for selected region.
3. Load grouped instances for selected account + region.
4. Apply client filters (engine, status, etc.) or call dedicated backend filtering if needed.

### Security and access recommendations

- Put API Gateway behind the organization identity model:
  - Cognito/JWT authorizer or IAM auth
  - Optional API key + usage plan for partner/internal apps
- Restrict CORS origins to known portal domains in production.
- For cross-org integrations, front the API with an internal service gateway/reverse proxy and enforce RBAC there.
- Add CloudWatch metrics/alarms and access logs for auditability.

### Example (backend-to-backend fetch)

```bash
curl "https://YOUR_API_ID.execute-api.REGION.amazonaws.com/prod/regions"
curl "https://YOUR_API_ID.execute-api.REGION.amazonaws.com/prod/accounts?region=ap-south-1"
curl "https://YOUR_API_ID.execute-api.REGION.amazonaws.com/prod/accounts/123456789012/instances?region=ap-south-1"
```

### Example (`/instances` grouped)

```json
{
  "account_id": "123456789012",
  "instances": [
    {
      "instance_id": "i-0abc123",
      "instance_type": "t3.medium",
      "tags": { "Name": "db-server-01", "Environment": "production" },
      "discovery_status": "success",
      "databases": [
        {
          "db_id": "mysql-3306",
          "engine": "mysql",
          "version": "8.0.35",
          "status": "running",
          "data_size_mb": 2048
        }
      ]
    }
  ]
}
```

---

## Discovery Lambda (high level)

| Env var | Role |
|---------|------|
| `SPOKE_ACCOUNTS` | Comma-separated spoke IDs (manual list) |
| `DISCOVERY_REGIONS` | Regions to scan per account |
| `DISCOVER_ALL_ORG_ACCOUNTS` | If `true`, merge org member accounts (management account) |
| `ORG_SKIP_MANAGEMENT_ACCOUNT`, `ORG_EXCLUDE_ACCOUNT_IDS` | Optional filters |
| `RESULTS_S3_BUCKET`, `RESULTS_S3_KEY` | Snapshot location |
| `SPOKE_ROLE_NAME`, `SSM_DOCUMENT` | Assume role name and SSM document name |

After each run, the **API** reads the latest object — no separate database sync.

---

## Prerequisites

- AWS CLI configured for **management** (and console access for spokes as needed)
- Spokes: **`DBDiscoverySpokeRole`** + EC2 instance profile with **SSM**; instances **Online** in Fleet Manager
- **Linux** probe path (Windows instances are not targeted by the current listing filter)

---

## Limitations

- **SSM-managed** instances only; probe must complete within command timeout
- Engines: **MySQL, PostgreSQL, MongoDB** (script-defined)
- **Snapshot / batch** model — not live streaming; re-run Lambda or schedule for updates
- **No** RDS/Aurora/ECS discovery in this POC

---

## Authors

- **Tushar Bapu Shashikumar** ([@BSTushar](https://github.com/BSTushar)) — *tusharsabapu@gmail.com*  
- Airbus Cloud Intern Project — **Task_02**

---

## License

The badge above is informational. Redistribution is subject to the **Confidentiality Notice** at the top of this README and your organization’s policies. There is no separate `LICENSE` file in the repository.
