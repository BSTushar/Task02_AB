# Full Setup — One Order, No Confusion

**Use this as the single guide.** Do the steps **in chapter order**. Each step says which account (Management or Spoke) and what you need from earlier steps. No jumping between docs—everything is here and interconnected.

---

## Table of contents

| Chapter | Title | Steps |
|---------|--------|--------|
| **1** | [Before you start](#chapter-1-before-you-start) | Fill values, prerequisites |
| **2** | [Storage — S3 & DynamoDB](#chapter-2-storage--s3--dynamodb) | 1–2 |
| **3** | [Spoke account — Roles, EC2, SSM](#chapter-3-spoke-account--roles-ec2-ssm) | 3–6 |
| **4** | [Discovery — Lambda & run](#chapter-4-discovery--lambda--run) | 7–9 |
| **5** | [API — Lambda & Gateway](#chapter-5-api--lambda--gateway) | 10–12 |
| **6** | [Order summary](#chapter-6-order-summary) | Dependency chain |

---

# Chapter 1 — Before you start

## 1.1 Fill this once

| What | Your value (fill in) |
|------|----------------------|
| **MANAGEMENT_ACCOUNT_ID** | 12-digit ID of the account where Lambda/DynamoDB/API live (e.g. `111111111111`) |
| **SPOKE_ACCOUNT_ID** | 12-digit ID of the account where EC2 runs (e.g. `222222222222`) |
| **BUCKET_NAME** | Name you will use for the S3 bucket (e.g. `mycompany-db-discovery`) |
| **REGION** | Same region for everything (e.g. `eu-west-1`) |

## 1.2 Prerequisites

You need **one EC2 instance in the spoke account** (Linux). Create one if you don't have it. It will be SSM-managed later.

---

# Chapter 2 — Storage — S3 & DynamoDB

**Account: Management.** Create the bucket and script first, then the table where discovery will write.

---

## Step 1 — S3 bucket and script (Account: **Management**)

**Why first:** The discovery script must exist in S3 before anything can run it.

1. In **management** account: **Services** → **S3** → **Create bucket**.
2. **Bucket name:** use your **BUCKET_NAME** (e.g. `mycompany-db-discovery`). Must be globally unique.
3. **Region:** your **REGION**. Leave other settings default → **Create bucket**.
4. Open the bucket → **Upload** → **Add files** → select `ssm/discovery_python.py` from your project.
5. Under “Destination”, set path to **`ssm/discovery_python.py`** (create folder `ssm` if needed) → **Upload**.

**You’ll use:** BUCKET_NAME in Steps 5, 8.

---

## Step 2 — DynamoDB table (Account: **Management**)

**Why here:** Discovery Lambda will write results here. Create the table before creating the Lambda.

1. In **management** account: **Services** → **DynamoDB** → **Tables** → **Create table**.
2. **Table name:** `db-discovery-results` (exact).
3. **Partition key:** `account_id` (String).
4. **Sort key:** `instance_db_id` (String).
5. **Table settings:** **Customize** if needed → **Capacity mode:** **On-demand** → **Create table**.

**You’ll use:** table name in Steps 8, 10.

---

# Chapter 3 — Spoke account — Roles, EC2, SSM

**Account: Spoke.** Set up trust for management, EC2 role for SSM + S3, SSM document, and confirm instance is Online.

---

## Step 3 — Spoke role: let management assume it (Account: **Spoke**)

**Why here:** The discovery Lambda (in management) must assume a role in the spoke to run SSM. Create that role in the spoke first.

1. Switch to **spoke** account. **Services** → **IAM** → **Roles** → **Create role**.
2. **Trusted entity:** Custom trust policy → **Next**.
3. **Permissions:** Skip (Next).
4. **Role name:** `DBDiscoverySpokeRole` → **Create role**.
5. Open **DBDiscoverySpokeRole** → **Trust relationships** → **Edit**.
6. Replace the JSON with (use your **MANAGEMENT_ACCOUNT_ID**):

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

7. **Update policy**.
8. **Permissions** tab → **Add permissions** → **Create inline policy** → **JSON**.
9. Paste contents of **`iam/spoke-account-role-policy.json`** → **Next** → **Policy name:** `DBDiscoverySpokePolicy` → **Create policy**.

**You’ll use:** This role is what the discovery Lambda assumes (Step 8).

---

## Step 4 — EC2 role: SSM + S3 (Account: **Spoke**)

**Why here:** The EC2 instance must have a role that allows SSM (to receive commands) and S3 (to download the script from Step 1).

1. Still in **spoke** account: **IAM** → **Roles** → **Create role**.
2. **Trusted entity:** AWS service → **EC2** → **Next**.
3. **Permissions:** Search **AmazonSSMManagedInstanceCore** → check it → **Next**.
4. **Role name:** `EC2-SSM-Discovery-Role` → **Create role**.
5. Open **EC2-SSM-Discovery-Role** → **Permissions** → **Add permissions** → **Create inline policy** → **JSON**.
6. Paste this and replace **BUCKET_NAME** with the value from your table at the top:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3GetDiscoveryScript",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::BUCKET_NAME/ssm/*"
    }
  ]
}
```

7. **Next** → **Policy name:** `EC2-Discovery-S3` → **Create policy**.
8. **EC2** → **Instances** → select your Linux instance → **Actions** → **Security** → **Modify IAM role** → choose **EC2-SSM-Discovery-Role** → **Update IAM role**.

**You’ll use:** Instance must show as **Online** in Fleet Manager (Step 6). If the bucket is in management account, add a bucket policy on that bucket allowing this role/account to `s3:GetObject` on `arn:aws:s3:::BUCKET_NAME/ssm/*`.

---

## Step 5 — SSM document (Account: **Spoke**)

**Why here:** The discovery Lambda will invoke this document on the instance. The document pulls the script from S3 (Step 1) and runs it.

1. Still in **spoke** account: **Services** → **Systems Manager** → **Documents** (left: Shared Resources → Documents).
2. **Create document**.
3. **Name:** `DBDiscovery` (exact).
4. **Document type:** Command or Session document.
5. **Content:** switch to **Editor** / JSON, delete default, paste the full content of **`ssm/ssm-document.json`** from your project.
6. **Create document**.

**You’ll use:** Document name `DBDiscovery` in Step 8.

---

## Step 6 — Check instance is managed (Account: **Spoke**)

**Why here:** Discovery only runs on instances that SSM shows as Online.

1. In **spoke** account: **Systems Manager** → **Fleet Manager** (or Node Management → Fleet Manager).
2. Under managed nodes, find your EC2 instance. **Ping status** must be **Online**.
3. If **Offline** or missing: ensure the instance has **EC2-SSM-Discovery-Role** (Step 4), has outbound HTTPS (443), and SSM agent is running. Wait a few minutes and refresh.

**You’ll use:** Nothing to copy; you just need at least one Online instance before Step 8.

---

# Chapter 4 — Discovery — Lambda & run

**Account: Management.** Create the discovery Lambda role and function, then run discovery and verify DynamoDB.

---

## Step 7 — Discovery Lambda role and policy (Account: **Management**)

**Why here:** The db-discovery Lambda needs a role that can assume the spoke role (Step 3) and write to DynamoDB (Step 2).

1. Switch to **management** account. **IAM** → **Roles** → **Create role**.
2. **Trusted entity:** AWS service → **Lambda** → **Next**.
3. **Permissions:** **Create inline policy** → **JSON**.
4. Paste contents of **`iam/management-discovery-lambda-policy.json`**.
5. In that JSON, replace the placeholder account ID with your **SPOKE_ACCOUNT_ID** (one ARN is enough if you have only one spoke). Example:

```json
"Resource": [
  "arn:aws:iam::SPOKE_ACCOUNT_ID:role/DBDiscoverySpokeRole"
]
```

6. **Next** → **Policy name:** `DBDiscoveryLambdaPolicy` → **Create policy**.
7. Back in “Add permissions”: refresh, select **DBDiscoveryLambdaPolicy** → **Next**.
8. **Role name:** `DBDiscoveryLambdaRole` → **Create role**.

**You’ll use:** Role name in Step 8.

---

## Step 8 — Discovery Lambda (Account: **Management**)

**Why here:** This is the function that runs discovery. It needs: S3 (Step 1), DynamoDB (Step 2), spoke role (Step 3), SSM document (Step 5), and the Lambda role (Step 7).

1. In **management** account: **Lambda** → **Functions** → **Create function**.
2. **Author from scratch**. **Function name:** `db-discovery`. **Runtime:** Python 3.11. **Architecture:** x86_64.
3. **Permissions:** **Use an existing role** → **DBDiscoveryLambdaRole** (from Step 7) → **Create function**.
4. **Code** tab: delete default code, paste full contents of **`lambda/discovery_handler.py`** → **Deploy**.
5. **Configuration** → **General configuration** → **Edit** → **Timeout:** 5 min → **Save**.
6. **Configuration** → **Environment variables** → **Edit** → Add (use your **BUCKET_NAME** and **SPOKE_ACCOUNT_ID**):

| Key | Value |
|-----|--------|
| SPOKE_ACCOUNTS | Your **SPOKE_ACCOUNT_ID** (single ID, no comma) |
| SPOKE_ROLE_NAME | `DBDiscoverySpokeRole` |
| SSM_DOCUMENT | `DBDiscovery` |
| DYNAMODB_TABLE | `db-discovery-results` |
| S3_BUCKET | Your **BUCKET_NAME** from Step 1 |

7. **Save**.

**You’ll use:** Run Test in Step 9.

---

## Step 9 — Run discovery and check DynamoDB (Account: **Management**)

**Why here:** Confirms Steps 1–8 work before you build the API.

1. **Lambda** → **db-discovery** → **Test** tab.
2. **Create new event** if needed: Event name `demo`, Event JSON `{}` → **Save**.
3. **Test** → wait 30–90 seconds.
4. Response should show **Succeeded** and e.g. `"discovered": 1` (or more). If `"discovered": 0`, check: Fleet Manager instance Online (Step 6), S3 path `ssm/discovery_python.py` (Step 1), SSM document name (Step 5), env vars (Step 8).
5. **DynamoDB** → **Tables** → **db-discovery-results** → **Explore table items** → **Run**. You should see items with `account_id`, `instance_id`, `instance_type`, `tags`, etc.

**You’ll use:** Nothing; this step only verifies. Then continue to Chapter 5.

---

# Chapter 5 — API — Lambda & Gateway

**Account: Management.** Create the API Lambda role and function, wire API Gateway, then test the API.

---

## Step 10 — API Lambda role and function (Account: **Management**)

**Why here:** The REST API needs a Lambda that reads from the same DynamoDB table (Step 2).

1. In **management** account: **IAM** → **Roles** → **Create role**.
2. **Trusted entity:** AWS service → **Lambda** → **Next**.
3. **Create inline policy** → **JSON** → paste contents of **`iam/api-lambda-policy.json`** → **Next** → **Policy name:** `DBDiscoveryApiPolicy` → **Create policy**.
4. Attach **DBDiscoveryApiPolicy** → **Next** → **Role name:** `DBDiscoveryApiRole` → **Create role**.
5. **Lambda** → **Create function** → **Author from scratch** → **Function name:** `db-discovery-api` → **Runtime:** Python 3.11.
6. **Permissions:** **Use an existing role** → **DBDiscoveryApiRole** → **Create function**.
7. **Code** tab: delete default, paste full contents of **`lambda/api_handler.py`** → **Deploy**.
8. **Configuration** → **Environment variables** → **Edit** → Add: Key **DYNAMODB_TABLE**, Value **db-discovery-results** → **Save**.

**You’ll use:** Function name in Step 11.

---

## Step 11 — API Gateway (Account: **Management**)

**Why here:** Exposes the data from DynamoDB via REST. Needs the API Lambda from Step 10.

1. **API Gateway** → **Create API** → **REST API** (Build).
2. **API name:** e.g. `db-discovery-api` → **Create API**.
3. Create resources and methods (all GET, all integrate with Lambda **db-discovery-api**; when asked, allow API Gateway to invoke the Lambda):
   - **/health:** Select **/** (root) → **Create Resource** → Name: `health` → **Create Resource** → with **/health** selected → **Create Method** → **GET** → Integration: Lambda **db-discovery-api** → **Save** → **OK**.
   - **/accounts:** Select **/** → **Create Resource** → Name: `accounts` → **Create Resource** → with **/accounts** selected → **Create Method** → **GET** → Lambda **db-discovery-api** → **Save** → **OK**.
   - **/databases:** Select **/** → **Create Resource** → Name: `databases` → **Create Resource** → with **/databases** selected → **Create Method** → **GET** → Lambda **db-discovery-api** → **Save** → **OK**.
   - **/accounts/{accountId}/instances:** Select **/accounts** in the tree → **Create Resource** → Name: `{accountId}` (type exactly, with curly braces) → **Create Resource** → select **/{accountId}** → **Create Resource** → Name: `instances` → **Create Resource** → with **/instances** selected → **Create Method** → **GET** → Lambda **db-discovery-api** → **Save** → **OK**.
4. **Actions** → **Deploy API** → **Stage:** New → **Stage name:** `prod` → **Deploy**.
5. Note the **Invoke URL** (e.g. `https://xxxx.execute-api.REGION.amazonaws.com/prod`).

**You’ll use:** Invoke URL for Step 12 and for DEMO_SCRIPT.

---

## Step 12 — Test the API (Account: **Management**)

1. Open in browser or use curl (replace with your API ID, REGION, and SPOKE_ACCOUNT_ID):

- `https://YOUR_API_ID.execute-api.REGION.amazonaws.com/prod/health`
- `https://YOUR_API_ID.execute-api.REGION.amazonaws.com/prod/accounts`
- `https://YOUR_API_ID.execute-api.REGION.amazonaws.com/prod/accounts/SPOKE_ACCOUNT_ID/instances`

2. You should see JSON with `status`, `accounts`, or `instances` (with `instance_type` and `tags`).

---

# Chapter 6 — Order summary

## Dependency chain

| Chapter | Step | What | Account |
|---------|------|------|---------|
| 2 | 1 | S3 bucket + upload script | Management |
| 2 | 2 | DynamoDB table | Management |
| 3 | 3 | DBDiscoverySpokeRole (trust + policy) | Spoke |
| 3 | 4 | EC2-SSM-Discovery-Role + attach to instance | Spoke |
| 3 | 5 | SSM document DBDiscovery | Spoke |
| 3 | 6 | Check instance Online in Fleet Manager | Spoke |
| 4 | 7 | DBDiscoveryLambdaRole + policy | Management |
| 4 | 8 | Lambda db-discovery (code + env vars) | Management |
| 4 | 9 | Run discovery + check DynamoDB | Management |
| 5 | 10 | DBDiscoveryApiRole + Lambda db-discovery-api | Management |
| 5 | 11 | API Gateway (resources + deploy prod) | Management |
| 5 | 12 | Test API | Management |

**If you already did some steps:** Find your place in the table above. Complete any earlier step you skipped (e.g. S3, spoke roles, SSM document), then continue from the next step. Use the “You’ll use” lines in each step to connect chapters.
