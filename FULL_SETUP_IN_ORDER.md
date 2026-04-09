# Full Setup — One Order, No Confusion

**Use this as the single guide.** Do the steps **in chapter order**. Inventory is stored in **S3** (`discovery/inventory.json` by default); the API Lambda reads that file—**no DynamoDB** required.

---

## Table of contents

| Chapter | Title | Steps |
|---------|--------|--------|
| **1** | [Before you start](#chapter-1-before-you-start) | Fill values, prerequisites |
| **2** | [Storage — S3](#chapter-2-storage--s3) | 1 |
| **3** | [Spoke account — Roles, EC2, SSM](#chapter-3-spoke-account--roles-ec2-ssm) | 2–5 |
| **4** | [Discovery — Lambda & run](#chapter-4-discovery--lambda--run) | 6–8 |
| **5** | [API — Lambda & Gateway](#chapter-5-api--lambda--gateway) | 9–11 |
| **6** | [Optional — Automate discovery](#chapter-6-optional--automate-discovery) | 12–13 |
| **7** | [Order summary](#chapter-7-order-summary) | Dependency chain |

---

# Chapter 1 — Before you start

## 1.1 Fill this once

| What | Your value (fill in) |
|------|----------------------|
| **MANAGEMENT_ACCOUNT_ID** | 12-digit ID where Lambda, API, and **S3 bucket** live |
| **SPOKE_ACCOUNT_ID** | 12-digit ID where EC2 runs (comma-separate if several) |
| **BUCKET_NAME** | Globally unique S3 bucket (script **and** inventory JSON) |
| **REGION** | Hub region (Lambda/API/S3). Spokes can use **DISCOVERY_REGIONS** later. |

## 1.2 Prerequisites

One **Linux** EC2 in each spoke (or one spoke for a minimal demo), SSM-capable.

---

# Chapter 2 — Storage — S3

**Account: Management.** Script + inventory share one bucket (FinOps: one object per discovery run instead of many DB rows).

---

## Step 1 — S3 bucket and script (Account: **Management**)

1. **S3** → **Create bucket** → name = **BUCKET_NAME**, region = **REGION** → **Create**.
2. **Upload** `ssm/discovery_python.py` from this repo with key **`ssm/discovery_python.py`**.
3. After first discovery run, you will also see **`discovery/inventory.json`** (created automatically).

**Policy JSON (project `iam/`):** Replace **`YOUR_S3_BUCKET_NAME`** with **BUCKET_NAME** in:

- `iam/management-discovery-lambda-policy.json` → `s3:PutObject` on `arn:aws:s3:::BUCKET_NAME/discovery/*`
- `iam/api-lambda-policy.json` → `s3:GetObject` on the same ARN pattern

**You’ll use:** BUCKET_NAME in Lambda env vars and IAM.

---

# Chapter 3 — Spoke account — Roles, EC2, SSM

## Step 2 — Spoke role: let management assume it (Account: **Spoke**)

1. **IAM** → **Roles** → **Create role** → **Custom trust policy** → **Next**.
2. **Role name:** `DBDiscoverySpokeRole` → **Create role**.
3. **Trust relationships** → **Edit** → paste (replace **MANAGEMENT_ACCOUNT_ID**):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::MANAGEMENT_ACCOUNT_ID:root"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

4. **Permissions** → **Create inline policy** → JSON from **`iam/spoke-account-role-policy.json`** → name `DBDiscoverySpokePolicy`.

**Multi-spoke:** Repeat or extend trust/policy per account.

---

## Step 3 — EC2 role: SSM + S3 (Account: **Spoke**)

1. **IAM** → **Roles** → **Create role** → **EC2** → attach **AmazonSSMManagedInstanceCore** → name `EC2-SSM-Discovery-Role`.
2. Add inline policy **`s3:GetObject`** on `arn:aws:s3:::BUCKET_NAME/ssm/*` (see Step 1 patterns in older template).
3. **EC2** → your instance → **Modify IAM role** → **EC2-SSM-Discovery-Role**.

If the bucket is in **management**, add a **bucket policy** allowing this instance role (or spoke account) to `GetObject` on `ssm/*`.

---

## Step 4 — SSM document (Account: **Spoke**)

1. **Systems Manager** → **Documents** → **Create document** → name **`DBDiscovery`**.
2. Paste **`ssm/ssm-document.json`** → **Create**.

---

## Step 5 — Instance Online (Account: **Spoke**)

**Fleet Manager** → instance **Ping status** = **Online** before running discovery.

---

# Chapter 4 — Discovery — Lambda & run

**Account: Management.**

## Step 6 — Discovery Lambda role (Account: **Management**)

1. **IAM** → **Roles** → **Lambda** → **`iam/management-discovery-lambda-policy.json`** as inline policy (replace **YOUR_S3_BUCKET_NAME** and spoke ARN `DBDiscoverySpokeRole`).
2. Role name: **`DBDiscoveryLambdaRole`**.

---

## Step 7 — Discovery Lambda (Account: **Management**)

1. **Lambda** → **Create function** → **`db-discovery`**, Python 3.11 → role **DBDiscoveryLambdaRole**.
2. Paste **`lambda/discovery_handler.py`** → handler **`discovery_handler.lambda_handler`** → **Timeout** 5 min → **Deploy**.
3. **Environment variables:**

| Key | Value |
|-----|--------|
| `SPOKE_ACCOUNTS` | Optional manual IDs (comma-separated). **Required** if not using org-wide discovery. |
| `DISCOVER_ALL_ORG_ACCOUNTS` | Set **`true`** to list **every ACTIVE** account from **AWS Organizations** (no manual account list needed). **Lambda must run in the org *management* account** (or use a delegated admin role — advanced). |
| `ORG_EXCLUDE_ACCOUNT_IDS` | Optional comma list to skip (e.g. vendor sandboxes). |
| `ORG_SKIP_MANAGEMENT_ACCOUNT` | Optional **`true`** to skip the org root (management) account ID. |
| `DISCOVERY_REGIONS` | Regions to scan, e.g. `eu-west-1,ap-south-1` |
| `SPOKE_ROLE_NAME` | `DBDiscoverySpokeRole` |
| `SSM_DOCUMENT` | `DBDiscovery` |
| `S3_BUCKET` | **BUCKET_NAME** (script + default inventory bucket) |
| `RESULTS_S3_KEY` | Optional; default `discovery/inventory.json` |
| `RESULTS_S3_BUCKET` | Optional; omit to use **S3_BUCKET** |

**Org-wide mode:** New member accounts appear on the **next** run automatically **after** **`DBDiscoverySpokeRole`** (same trust to hub) exists in that account — no change to `SPOKE_ACCOUNTS`. Merge: set **`DISCOVER_ALL_ORG_ACCOUNTS=true`** **and** `SPOKE_ACCOUNTS` to add **non-org** IDs if needed.

**IAM:** Discovery role needs **`organizations:ListAccounts`** + **`sts:AssumeRole`** on `arn:aws:iam::*:role/DBDiscoverySpokeRole` — see **`iam/management-discovery-lambda-policy.json`**.

---

## Step 8 — Run discovery & verify S3 (Account: **Management**)

1. **Lambda** → **Test** → `{}` → **Succeeded**.
2. **S3** → bucket → **`discovery/inventory.json`** → open → JSON with **`records`** array.
3. If **`discovered`: 0**, check Fleet Manager **Online**, env vars, SSM document name, script path.

---

# Chapter 5 — API — Lambda & Gateway

## Step 9 — API Lambda (Account: **Management**)

1. **IAM** → **Lambda** role **DBDiscoveryApiRole** with **`iam/api-lambda-policy.json`** (same bucket, `discovery/*` **GetObject**).
2. **Lambda** → **`db-discovery-api`** → paste **`lambda/api_handler.py`** → handler **`api_handler.lambda_handler`** → **Deploy**.
3. **Environment variables:**

| Key | Value |
|-----|--------|
| `S3_BUCKET` or `RESULTS_S3_BUCKET` | Same as discovery inventory bucket |
| `RESULTS_S3_KEY` | Same as discovery (default `discovery/inventory.json`) |
| *(do not set)* | **`AWS_REGION`** is injected by Lambda (reserved). |

---

## Step 10 — API Gateway (Account: **Management**)

**REST API** (or HTTP API with equivalent routes). All **GET**, **Lambda proxy** → **`db-discovery-api`**:

| Path |
|------|
| `/health` |
| `/accounts` |
| `/databases` |
| `/regions` |
| `/regions/{region}/accounts` |
| `/accounts/{accountId}` *(optional)* |
| `/accounts/{accountId}/instances` |

**Deploy** stage **`prod`**. Note **Invoke URL**.

Enable **CORS** if you open **`inventory_ui.html`** from your laptop.

---

## Step 11 — Test API & dashboard

Browser or curl:

- `.../prod/health` → `"store":"s3"`, `total_records`
- `.../prod/regions`
- `.../prod/accounts/SPOKE_ACCOUNT_ID/instances?region=YOUR_REGION`

**`inventory_ui.html`:** set **`BASE_URL`** to `https://xxxx.execute-api.REGION.amazonaws.com/prod` (no trailing slash after `prod`).

---

# Chapter 6 — Optional — Automate discovery

## Step 12 — EventBridge schedule (no manual Test)

**Option A — Console**

1. **Amazon EventBridge** → **Rules** → **Create rule**.
2. **Schedule** expression e.g. `rate(1 day)` or `cron(0 6 * * ? *)` (daily 06:00 UTC).
3. **Target:** **AWS Lambda** → **`db-discovery`**.
4. **Add permission** when prompted so EventBridge can invoke the Lambda.

**Option B — CloudFormation (repeatable)**

- Template: **`automation/discovery-eventbridge-schedule.yaml`**
- Commands and parameters: **[automation/EVENTBRIDGE_DISCOVERY_SCHEDULE.md](automation/EVENTBRIDGE_DISCOVERY_SCHEDULE.md)**

New EC2 instances (SSM Online) appear on the **next** scheduled run. New **accounts** still require adding **`SPOKE_ACCOUNTS`** (and spoke IAM setup).

## Step 13 — Optional spoke bootstrap automation (StackSet)

If you onboard many spokes, automate setup with CloudFormation StackSets from the management account:

1. Use template **`automation/spoke-bootstrap-stackset.yaml`**.
2. Follow command guide in **`automation/STACKSET_AUTOMATION.md`**.
3. Deploy to account IDs (or OU) and target regions.
4. Keep `db-discovery` `SPOKE_ACCOUNTS` and `DISCOVERY_REGIONS` in sync.

---

# Chapter 7 — Order summary

| Chapter | Step | What | Account |
|---------|------|------|---------|
| 2 | 1 | S3 bucket + upload script | Management |
| 3 | 2 | DBDiscoverySpokeRole | Spoke |
| 3 | 3 | EC2 role + SSM + attach | Spoke |
| 3 | 4 | SSM document DBDiscovery | Spoke |
| 3 | 5 | Fleet Manager Online | Spoke |
| 4 | 6 | DBDiscoveryLambdaRole | Management |
| 4 | 7 | Lambda db-discovery + env | Management |
| 4 | 8 | Test discovery + S3 inventory | Management |
| 5 | 9 | Lambda db-discovery-api + env | Management |
| 5 | 10 | API Gateway + deploy | Management |
| 5 | 11 | curl / browser / inventory UI | Management |
| 6 | 12 | (Optional) EventBridge → db-discovery (console or `automation/discovery-eventbridge-schedule.yaml`) | Management |
| 6 | 13 | (Optional) StackSet spoke bootstrap | Management |

---

## Legacy DynamoDB

Older deployments used **`db-discovery-results`**. This repo version **does not require it**. You may delete that table after migrating to S3 if it is empty.
