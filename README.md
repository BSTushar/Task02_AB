# Task_02: Database Discovery on EC2 Across AWS Accounts

**Discover all databases installed on EC2 instances across multiple AWS accounts and expose via API.**

> **Confidentiality Notice:** This project is confidential and proprietary to AIRBUS. Unauthorized distribution, disclosure, or use is strictly prohibited.

[![AWS](https://img.shields.io/badge/AWS-Lambda%20%7C%20SSM%20%7C%20DynamoDB-orange)](https://aws.amazon.com)
[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## Overview

This proof-of-concept discovers databases (MySQL, PostgreSQL, MongoDB) installed on EC2 instances across AWS accounts, captures type, version, database sizing, system sizing, **EC2 instance type (t-shirt size)**, and **instance tags**, and exposes the results via a REST API.

### Key Features

- **Cross-account discovery** — Hub-and-spoke model with STS AssumeRole
- **No SSH** — Uses AWS Systems Manager (SSM) Run Command
- **Read-only** — No database connections, no config modifications
- **API exposed** — REST endpoints for dashboards, CMDB, compliance

### Architecture

```
Management Account                    Spoke Accounts
┌─────────────────────┐              ┌──────────────────┐
│ EventBridge         │              │ EC2 + SSM Agent  │
│       ↓             │   AssumeRole │       ↓          │
│ Discovery Lambda ───┼─────────────►│ SSM Run Command  │
│       ↓             │              │       ↓          │
│ DynamoDB ◄──────────┘              │ discovery_python │
│       ↑                            └──────────────────┘
│ API Gateway + Lambda
└─────────────────────┘
```

---

## Quick Start

1. **Clone & setup**
   ```bash
   git clone https://github.com/BSTushar/Task02_AB.git
   cd Task02_AB
   ```

2. **Follow setup** — See [FULL_SETUP_IN_ORDER.md](FULL_SETUP_IN_ORDER.md) or [DEMO_BABY_STEPS.md](DEMO_BABY_STEPS.md) for step-by-step instructions (Console & CLI)

3. **Run discovery**
   ```bash
   aws lambda invoke --function-name db-discovery --payload '{}' response.json
   cat response.json
   ```

4. **Call API**
   ```bash
   curl https://YOUR_API_ID.execute-api.eu-west-1.amazonaws.com/prod/health
   curl https://YOUR_API_ID.execute-api.eu-west-1.amazonaws.com/prod/accounts
   ```

---

## Project Structure

| Path | Description |
|------|-------------|
| `iam/` | IAM policies (trust, spoke role, Lambda roles, EC2 instance) |
| `ssm/` | Discovery script (`discovery_python.py`) and SSM document |
| `lambda/` | Discovery handler and API handler |
| `schema/` | DynamoDB table definition and example record |
| `api/` | API Gateway config and curl examples |
| `FULL_SETUP_IN_ORDER.md` / `DEMO_BABY_STEPS.md` | Step-by-step setup (Console & CLI) |
| `TASK_02_SENIOR_REVIEW_PACKAGE.md` | Full review package, Q&A, demo script |
| `TASK_02_PRESENTATION.pptx` | PowerPoint presentation |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check, total records |
| GET | `/accounts` | List accounts with discovery data |
| GET | `/accounts/{accountId}/instances` | Instances, databases, **instance_type**, and **tags** per account |
| GET | `/databases` | All databases (optional: `?engine=mysql&account_id=123`) |

Full REST API reference (request/response fields): [api/api-gateway-config.md](api/api-gateway-config.md)

### Example Response

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

## Prerequisites

- AWS CLI configured
- Management account + 1–2 member accounts
- EC2 instances with SSM agent (managed instances)
- Python 3.11 (for Lambda)

---

## Configuration

Replace these placeholders before deployment:

| Placeholder | Description |
|-------------|-------------|
| `MANAGEMENT_ACCOUNT_ID` | Management account ID |
| `SPOKE_ACCOUNT_1_ID`, `SPOKE_ACCOUNT_2_ID` | Member account IDs |
| `YOUR_BUCKET_NAME` | S3 bucket for discovery script |
| `YOUR_API_ID` | API Gateway ID |

---

## Limitations

- Only SSM-managed instances
- MySQL, PostgreSQL, MongoDB only
- Batch discovery (not real-time)
- Single region
- No RDS/Aurora; no container discovery

---

## Authors

- **BSTushar** — [GitHub](https://github.com/BSTushar)
- Airbus Cloud Intern Project — Task_02

---

## License

MIT License — See [LICENSE](LICENSE) for details.
