# Demo runbook — 5-minute script & viva (Q&A)

**Setup, idle cost, StackSet:** [FULL_SETUP_IN_ORDER.md](FULL_SETUP_IN_ORDER.md), [COST_AND_STOP_RESOURCES.md](COST_AND_STOP_RESOURCES.md), [automation/STACKSET_AUTOMATION.md](automation/STACKSET_AUTOMATION.md). **Architecture / API:** [README.md](README.md). **Deeper roadmap:** [automation/TIER3_RESEARCH_SHEET.md](automation/TIER3_RESEARCH_SHEET.md).

---

## 5-minute presentation script

Speak in this order; stay under **5 minutes** total.

### Problem (20 seconds)

We need a **read-only inventory** of databases on **Linux EC2** across **many accounts and regions**—**without SSH**. This POC uses **SSM Run Command** from a **hub** account.

### Architecture (45 seconds)

- **Hub (management account):** **EventBridge** (optional schedule) or **manual invoke** → **`db-discovery`** Lambda → writes **one JSON file** to **S3**. **`db-discovery-api`** Lambda → **reads S3** → **API Gateway** → browser or tools.
- **Spokes (workload accounts):** **EC2** with **SSM agent** + instance profile. Hub uses **IAM AssumeRole** into **`DBDiscoverySpokeRole`**, then **SSM** runs a script on each **Online** Linux instance.

*Optional:* Point at the diagram in [README.md](README.md): hub box (EventBridge → discovery → S3 ← API) ↔ spoke (EC2 + SSM).

### Discovery Lambda — `db-discovery` — what & how (90 seconds)

**What:** One **scan** that merges **all** spoke accounts and regions you configured into **one snapshot**.

**How (flow):**

1. **Resolve accounts** — from **`SPOKE_ACCOUNTS`** and/or **`DISCOVER_ALL_ORG_ACCOUNTS`** (Organizations list).
2. **Per account + region:** **STS AssumeRole** into the spoke → **SSM** lists instances that are **managed and Online** (Linux) → **EC2 DescribeInstances** for **tags**, **type**, **`ec2_state`** (running/stopped).
3. **SSM SendCommand** runs **`discovery_python.py`** on each target (via your **SSM document**); stdout is **JSON**.
4. **Parse** stdout into **flat rows**, merge everything, **`PutObject`** to **`discovery/inventory.json`** (or your **`RESULTS_S3_KEY`**).

**One line:** *Hub assumes into spoke, runs a read-only script over SSM, merges rows into one S3 file.*

### API Lambda — `db-discovery-api` — what & how (45 seconds)

**What:** **HTTP GET** only — serves the **last S3 snapshot** as JSON (regions, accounts, instances, DBs).

**How:** Reads the same **S3 object**, **groups** rows by instance for the UI. Optionally **AssumeRole** + **`ec2:DescribeInstances`** for **live** running/stopped (**red/green**) when **`API_ENRICH_EC2_STATE`** is on.

**One line:** *API is a read layer on the snapshot; optional live EC2 state for the UI.*

### On the EC2 instance (20 seconds)

**`ssm/discovery_python.py`** runs **inside** the instance (SSM, not SSH). It **only inspects** processes/paths for **MySQL / PostgreSQL / MongoDB**, plus light **CPU/RAM** hints, and prints **one JSON** (`databases[]`).

### Output (30 seconds)

| Layer | What they see |
|--------|----------------|
| **S3** | Single **`inventory.json`** — source of truth for the **last successful** scan. |
| **API** | JSON: `/health`, `/regions`, `/accounts`, `/accounts/{id}/instances?region=…` |
| **UI** | `inventory_ui.html` — KPIs, table, topology; **Reload** pulls latest API data. |

**Closing line:** *It is a **snapshot**, not a live stream—**run discovery again** (or wait for the schedule) to refresh; **Reload** the UI after.*

---

## Viva / Q&A

### Sound bites (one-liners)

| If they ask… | Say… |
|--------------|------|
| **Pitch in one sentence** | *Management **assumes** into each spoke, **SSM Run Command** runs a **read-only** script on **Linux** with no SSH, merges into **one S3 snapshot**; **API** + **UI** read that snapshot.* |
| **Is it real-time?** | *It’s a **snapshot**—last successful write to **S3**; **reload** the API or **invoke** discovery again to refresh.* |
| **Red / green EC2** | *After **Reload**, stopped can show **red** when the API **enriches** live state via **STS** + **`ec2:DescribeInstances`** on the spoke (needs IAM on the API role).* |

---

### Cost and alternatives

**Q: Is this the cheapest architecture? Any other options?**

**Do not** say “cheapest possible.” Say **low cost at POC scale** and **FinOps-friendly**, with **trade-offs**.

**Why this layout is cheap / sensible (demo scale):**

- **No always-on hub servers:** Lambda + S3 + API Gateway.
- **One S3 snapshot** vs a dedicated DB updating every row continuously.
- **Schedule optional** — disable **EventBridge** → less idle churn.
- **Read-only over SSM** — no bastion fleet for this inventory pattern.

**If pressed on “absolute cheapest”:**

> *“For POC scale we aimed at **low run cost**: serverless hub, single snapshot in S3. **Absolute cheapest** depends on volume and features—we’d size that in production.”*

**Alternatives (name them honestly):**

| Idea | Trade-off |
|------|-----------|
| **Longer schedule / manual-only** | Fewer invocations; **staler** data |
| **AWS-native inventory** (Config, SSM Inventory aggregation, …) | Good for **AWS assets**; **not** the same as **DB-on-instance** script signals |
| **Agent + central DB** (CMDB, OpenSearch, DynamoDB, …) | Usually **more cost and ops** |
| **Step Functions** orchestration | Clear workflows; **extra** service vs one Lambda loop |

**Sound bite:**

> *“We optimized **low idle cost** and **simple ops**: Lambda + S3 + API, **no SSH**. Continuous query/history would mean a **data store**—that trades **cost/complexity** for **features**.”*

---

### How automated is this?

**Q: How automated?**

There is no single “percentage.” Use:

| Area | Automated | Usually manual / one-time |
|------|-----------|---------------------------|
| **Spoke bootstrap** | **StackSet** can push role, instance profile, SSM document to **many accounts/regions**. | Org trusted access, OU vs ID list, bucket policy, Lambda **env** updates. |
| **Discovery** | **Fully** once triggered: **SSM-managed Linux** in configured accounts/regions → **S3**. | **`SPOKE_ACCOUNTS`** / org flags, **`DISCOVERY_REGIONS`**, document name. |
| **API + UI** | Can be scripted. | Routes, CORS, **`BASE_URL`** in HTML. |

**Line:** *“**High** automation on the repeatable path—StackSet + scheduled/manual discovery—with **governance** (org, OU, env) on purpose.”*

---

### New AWS account onboarded

**Q: A new account joined the org — how do we onboard it?**

1. **StackSet on an OU** → account in that OU can get stacks automatically; verify IAM + SSM document in account/region.
2. **StackSet by account ID** → add **`create-stack-instances`** / targets for regions where EC2 runs.
3. **Discovery must know the account:** **`SPOKE_ACCOUNTS`** and/or **`DISCOVER_ALL_ORG_ACCOUNTS=true`** (see `resolve_accounts_to_scan()` in `lambda/discovery_handler.py`).
4. **S3 bucket policy** — if ARN-scoped, add new spoke principals as needed.
5. **Run discovery** again → **`inventory.json`** and API update.

**Q: 100% automated onboarding?**

**A:** *“**Mostly**, with **OU StackSet**, **org-wide discovery** in Lambda, and IaC on the hub—but you still want guardrails: **scope**, **regions**, **approvals**. Silent full auto in prod without that is risky.”*

---

### New EC2 in an existing account

**Q: New EC2 in an account we already scan — will we see it?**

**A: Yes on the next successful run if:** Linux, **SSM Online**, correct **instance profile**, and **region** in **`DISCOVERY_REGIONS`** on **`db-discovery`** → **`SendCommand`** runs → row in **`inventory.json`** and UI.

**If missing:** Stopped instance, **Windows**, SSM **Offline**, wrong **region**, missing profile, or command failure — check **SSM command history** and **CloudWatch** for **`db-discovery`**.

---

### Org-wide / “will new accounts appear automatically?”

**Q: Will new org accounts show up automatically?**

**Partly in this POC:** Same **bootstrap** (e.g. StackSet on OU) + discovery configured to **see** org accounts (`DISCOVER_ALL_ORG_ACCOUNTS`) or **listed** in **`SPOKE_ACCOUNTS`** → **next scan** can include them.

**Already in this POC:**

| Piece | Role |
|--------|------|
| **StackSet on OU** | New member can get spoke IAM + SSM document when stack instances deploy. |
| **`DISCOVER_ALL_ORG_ACCOUNTS`** | Enumerate org members (minus excludes) vs manual list only. |
| **EventBridge schedule** | Periodic refresh so new **online** EC2 in a scanned region appears on a **later** run. |

**Full enterprise** (roadmap, not all in repo): **account vending** (e.g. Control Tower), **org lifecycle** EventBridge → Lambda/Step Functions, **SCPs/Config/tags**, ticketing. **Boundary:** this discovers **SSM-managed Linux EC2** and **DB signals** in configured regions; it does **not** create instances or cover every AWS resource type.

**If they push E2E:**

> *“We automate **repeatable** bootstrap and **org-wide discovery** plus a **schedule**. **Full** onboarding adds **vending**, **org events**, and **governance**—see **Tier 3** notes.”*

---

### UI

| Situation | What to say / do |
|-----------|------------------|
| **Fresh data** | **Reload from API**; pick **region** + **account** that match the spoke. |
| **Empty table** | Almost always wrong **region/account**, or discovery not run since **SSM Online**. |
| **Topology** | Follows **selected table row**. Click another row to focus that instance. |
| **Name column** | **Name** tag under instance id; other tags in **Tags** / tooltip. |

---

### Live EC2 state (red/green) does not work

1. **API Lambda role:** **`sts:AssumeRole`** into spoke **`DBDiscoverySpokeRole`** (or **`SPOKE_ROLE_NAME`**).
2. **Spoke role:** **trust** allows API/hub; **policy** includes **`ec2:DescribeInstances`** in that region.
3. **Fallback:** set **`API_ENRICH_EC2_STATE=false`** → UI uses snapshot / discovery fields only.

---

### Discovery vs stopped instances

- **Discovery** runs **SSM Run Command** on instances **managed and online** in that run; **stopped** targets typically **don’t** get a fresh script run like running ones.
- Rows **already** in the snapshot can still show **current** stop/start **after Reload** if **API enrich** works (**DescribeInstances** on IDs from the snapshot).

---

### What does each key file do?

**Lambdas (management)**

| File | Role |
|------|------|
| **`lambda/api_handler.py`** | **`db-discovery-api`**: GET **`/health`**, **`/regions`**, **`/accounts`**, **`/accounts/{id}/instances`**, …; read S3 snapshot; optional **AssumeRole** + **`DescribeInstances`** for live **`ec2_state`**; **CORS** for the browser UI. |
| **`lambda/discovery_handler.py`** | **`db-discovery`**: resolve accounts → **AssumeRole** → SSM list (Linux, Online) → **DescribeInstances** → **SendCommand** (`discovery_python.py`) → parse JSON → **PutObject** S3. |
| **`lambda/lambda_function.py`** | Shim: **`lambda_handler`** → **`discovery_handler`** for zip/console handler naming. |

**On EC2 (via SSM)**

| File | Role |
|------|------|
| **`ssm/discovery_python.py`** | Read-only: **MySQL / PostgreSQL / MongoDB** signals + light CPU/RAM → **JSON** stdout. |

**IaC / IAM**

| Path | Role |
|------|------|
| **`automation/spoke-bootstrap-stackset.yaml`** | StackSet: spoke role, EC2 SSM profile, SSM document across OUs/accounts. |
| **`ssm/ssm-document.json`** | SSM document shell to run **`discovery_python.py`** (matches **`SSM_DOCUMENT`** env). |
| **`iam/*.json`** | Reference policies: discovery, API, spoke trust, EC2 instance profile. |

**UI**

| Path | Role |
|------|------|
| **`inventory_ui.html`** | Static dashboard: **`BASE_URL`**, filters, KPIs, table, topology, EC2 state styling. |
