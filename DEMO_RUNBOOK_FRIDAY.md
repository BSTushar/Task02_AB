# Demo runbook — Friday (cost, flow, Q&A)

Use this before/after the demo and as speaker notes. Pair with [COST_AND_STOP_RESOURCES.md](COST_AND_STOP_RESOURCES.md) and [FULL_SETUP_IN_ORDER.md](FULL_SETUP_IN_ORDER.md).

---

## Plain English — read this first (so you can explain it)

**What problem does this solve?**  
Teams run databases on **EC2** in **many accounts and regions**. This POC builds a **read-only inventory** (MySQL, PostgreSQL, MongoDB on **Linux**) **without SSH** and without you RDP-ing into every box.

**The two “sides”**

- **Management account (hub)** — Where the **discovery** and **API** Lambdas run, and where results land in **S3** (one JSON file, like a **single shared export** everyone reads).
- **Spoke accounts** — Where the **workload EC2** machines live. The hub **temporarily acts** in a spoke using **IAM AssumeRole** (think: *short-lived permission swap*, not a shared password).

**What happens in one discovery run? (simple chain)**

1. **Discovery** starts (you **invoke** it or a **schedule** runs it).
2. In each spoke + region it finds **Linux EC2 that are Online in SSM** (the AWS Systems Manager agent — **no SSH**).
3. It **pushes a small script** to each machine (**Run Command**). The script **only inspects** what’s there and prints **JSON** (engines, versions, sizes, tags — **read-only**).
4. Everything is **merged** into **one** object in **S3** (`inventory.json`). That’s the **source of truth** until the next run.

**What does the API Lambda do?**  
It **reads that S3 file** and answers **HTTP GET** requests: *which regions, which accounts, which instances, which DBs*. Most of the time that’s the **last scan**. Optionally it **asks EC2** “running or stopped?” so the **UI** can show **red/green** after you click **Reload** (that part needs extra **IAM** on the API side).

**What does `inventory_ui.html` do?**  
It’s only a **browser dashboard**: call the API, pick **region + account**, see **KPIs**, **table**, **topology**. **Click a row** = “focus the diagram on **this** server.”

**“Snapshot” in one sentence**  
It’s **not a live video feed** of your estate — it’s the **last successful scan** written to S3. **Run discovery again** or **Reload** = refresh from that file (and optional live EC2 state).

**STARS in kid-friendly words**

1. **Turn servers on** in the spoke.  
2. **Check** they show **Online** in SSM.  
3. **Run discovery** once.  
4. **Check** the S3 file updated.  
5. **Open the web page** and walk the story.

**If they ask “will new org accounts appear automatically?”**  
**Partly in this POC:** if the account gets the **same bootstrap** (e.g. StackSet on an OU) and **discovery** is set to **see** org accounts (`DISCOVER_ALL_ORG_ACCOUNTS`) or you **list** them, the **next scan** can include them. **Full enterprise** flow = account vending + approvals + events — see **§12** and the Tier 3 doc — that’s **roadmap**, not every feature coded here.

---

## 0. Memory cheat sheet — what to do & say

### The night before (idle / save money)

Remember **“Stop + Switch off schedule”**:

1. **Stop** spoke **EC2** (every region you used).  
2. **Switch off** the **EventBridge** rule that calls **`db-discovery`** (management account).

### Demo morning — do these in order (**“STARS”**)

| Letter | Do this |
|--------|--------|
| **S** | **Start** EC2 in the spoke(s) you will show. |
| **T** | **Test** SSM: instances **Online** (Fleet Manager or SSM console). |
| **A** | **Invoke** discovery: `aws lambda invoke --function-name db-discovery --payload "{}" response.json` (management profile; add `--cli-binary-format raw-in-base64-out` if your CLI asks). **Or** turn the EventBridge rule **on** and wait for the schedule. |
| **R** | **Refresh** proof: S3 **`discovery/inventory.json`** has a new timestamp / expected rows. |
| **S** | **Show** the story: hit `/health` → open **`inventory_ui.html`** → set **`BASE_URL`** → **Reload from API** → pick the same **region + account** as your instances. |

If the table is empty: wrong **region**, discovery didn’t finish, or instance not **SSM Online**.

### One sentence pitch (say this early)

> *“Management account **assumes** into each spoke, uses **SSM Run Command** to run a **read-only** script on **Linux** instances with no SSH, merges everything into **one S3 snapshot**, and the **API** and **HTML UI** read that snapshot.”*

### One line if they ask “is it real-time?”

> *“It’s a **snapshot**—last successful discovery write to **S3**; we **reload** the API or run Lambda again to refresh.”*

### One line for the UI (if you show red/green EC2)

> *“**Stopped** instances can show **red** after **Reload** when the API enriches live **EC2 state** from the spoke (needs **STS** on the API role).”*

---

## 1. Before Friday — turn **OFF** to save money

| Action | Where | Why |
|--------|--------|-----|
| **Stop EC2** | Each **spoke** → EC2 → instance → **Stop instance** | Largest cost; Stopped EBS still bills a little but much cheaper than running 24/7. |
| **Disable EventBridge rule** | **Management** → EventBridge → Rules → rule invoking **`db-discovery`** | Stops scheduled Lambda → fewer invocations, no cross-account SSM noise. |
| **Leave as-is (cheap)** | S3 (`inventory.json`, `ssm/discovery_python.py`), API Gateway, idle Lambdas | Demo-scale cost is usually tiny when nothing is polling and no schedule fires. |

**Optional (only if tearing down hard):** delete Lambdas / API / bucket / IAM — only if you accept redoing setup before demo.

**Quick checklist (idle mode):**  
(1) Spoke EC2 **Stopped** → (2) EventBridge rule **disabled**.

---

## 2. Demo day — turn **ON** and run (order matters)

| Step | Action |
|------|--------|
| 1 | **Start EC2** in spoke(s) you will show (Mumbai / Ireland, etc.). Wait until instances pass checks and **SSM** shows **Online** (Fleet Manager or `describe-instance-information`). |
| 2 | **Enable** the EventBridge rule that triggers **`db-discovery`**, *or* skip schedule and run discovery **manually once** (step 3). |
| 3 | **Run discovery** (management account profile): `aws lambda invoke --function-name db-discovery --payload '{}' response.json` then inspect `response.json` / CloudWatch logs. |
| 4 | Confirm **S3** object **`discovery/inventory.json`** (or your `RESULTS_S3_KEY`) updated (timestamp / record count). |
| 5 | **API smoke test:** `GET /health`, `GET /regions`, `GET /accounts?region=<region>`, `GET /accounts/<id>/instances?region=<region>`. |
| 6 | Open **`inventory_ui.html`** in a browser; set **`BASE_URL`** to your API stage URL if not already. Click **Reload from API**; pick region + spoke; walk table + topology + KPIs. |

If something is empty: wrong **region** filter, discovery didn’t finish, or instance not **SSM Online** / not Linux.

---

## 3. Architecture story (from the start — what to say)

1. **Problem:** Database footprint on EC2 is scattered across accounts and regions; you want a **read-only inventory** without SSH.
2. **Pattern:** **Hub (management)** assumes into **spoke** roles (**STS**), uses **SSM Run Command** with a **document** that runs **`discovery_python.py`** on each **managed** Linux instance.
3. **Output:** One **S3 snapshot** (`inventory.json`) — FinOps-friendly vs per-row databases at POC scale.
4. **Consumption:** **API Lambda** reads S3; **optional HTML UI** calls the API for region/account/instance views.
5. **Trigger:** **EventBridge** schedule (or manual invoke) on **`db-discovery`**.

Draw the box diagram from [README.md](README.md): Management (EventBridge → Discovery Lambda → S3 ← API) ↔ Spokes (EC2 + SSM + Run Command).

---

## 4. “How automated is this?” (honest % and scope)

There is no single official percentage; use this framing:

| Area | What’s automated | What’s usually manual / one-time |
|------|------------------|----------------------------------|
| **Spoke bootstrap** | **StackSet** can deploy role, instance profile, SSM document to **many accounts/regions** (see [automation/STACKSET_AUTOMATION.md](automation/STACKSET_AUTOMATION.md)). | First-time org trusted access, choosing OU vs account list, bucket policy, **Lambda env** updates. |
| **Discovery run** | **Fully automated** once triggered (schedule or invoke): discovers **SSM-managed Linux** instances in configured accounts + regions, merges into **S3**. | Setting **`SPOKE_ACCOUNTS`** / org flags, **`DISCOVERY_REGIONS`**, document name. |
| **API + UI** deploy | Can be scripted; often **console + zip** in a POC. | API routes, CORS, stage URL in HTML. |

**Talking line:** *“Roughly **high automation** on the repeatable part — bootstrap via StackSet and discovery via Lambda — with **governance checkpoints** (org, OU, env vars) that we keep intentional.”*

---

## 5. Q&A — new **account** onboarded

**Q: A new AWS account joined the org — how do we onboard it?**

**A (typical paths):**

1. **StackSet already targets an OU** → moving the account into that OU (or auto-deployment enabled) can **create stacks** automatically; verify IAM + SSM document in the new account/region.
2. **Account list / StackSet by ID** → add account to deployment targets (`create-stack-instances` / update ops) for the regions where EC2 runs.
3. **Discovery Lambda** must **know** the account: either add the ID to **`SPOKE_ACCOUNTS`** **or** enable **`DISCOVER_ALL_ORG_ACCOUNTS=true`** (management account) with excludes if needed — see `resolve_accounts_to_scan()` in `lambda/discovery_handler.py`.
4. **S3 bucket policy** if discovery script or results bucket restricts by role ARN — add the new spoke **`EC2-SSM-Discovery-Role`** / relevant principals if your policy is per-ARN.
5. Run **discovery** again; **inventory.json** and **API** will reflect the new account after a successful run.

**Q: Can onboarding be 100% automated?**

**A:** *“**Mostly**, if you standardize on **OU-based StackSet**, **org-wide account discovery** in Lambda, and **Infrastructure-as-Code** for management resources. You still need guardrails: what’s in scope, which **regions**, and **change approval** for org moves. Not everything should be silent auto-run in production without those.”*

---

## 6. Q&A — new **EC2** in an **existing** account

**Q: If they add a new EC2 in an account we already scan, will we see it?**

**A: Yes, on the next successful discovery run, if:**

- The instance is **Linux** and reports **Online** in **SSM** (`describe_instance_information` filters the inventory),
- It uses the **correct IAM instance profile** / role so SSM can run commands (same pattern as existing demo instances),
- The instance is in a **region** included in **`DISCOVERY_REGIONS`** on **`db-discovery`**,

then **`SendCommand`** runs on that instance too and the new host appears in **`inventory.json`** and the **API/UI**.

**If it doesn’t show up:** instance stopped, **Windows** (not in Linux path), SSM **Offline**, wrong region, missing profile, or command/document failure — check **SSM** command history and Lambda logs for that account/region.

---

## 7. One-page demo checklist (print-friendly)

**Night before:** EC2 stopped? EventBridge off?  
**Morning of:** Start EC2 → SSM Online → enable rule or **invoke** `db-discovery` → verify S3 → verify API → open UI → rehearse 3-minute story (architecture + one region + one spoke with DB + one “empty” host).  

**Closing line:** *“This is a **snapshot**: last write to S3 wins; **Reload** / new invoke refreshes the truth.”*

---

## 8. UI walkthrough — what to click (30 seconds)

| What | How |
|------|-----|
| Fresh data | **Reload from API**, then choose **region** and **account** that match your spoke. |
| Wrong empty screen | Almost always **region** or **account** mismatch — or discovery hasn’t run since hosts were **SSM Online**. |
| **Topology** vs table | **Topology** follows the **selected table row** (highlighted). Default row = first instance **with** detected DBs, else first row. Click another row to show an **empty** host (no DB nodes). |
| Name column | **Name tag** is shown under the **instance id**; other tags stay in **Tags** (tooltip has full set). |
| Red / green EC2 | **Reload** after stop/start; needs **API** live enrich (**STS AssumeRole** + `ec2:DescribeInstances` on spoke) — see §0. |

---

## 9. If live EC2 state (red/green) doesn’t work

1. **Management:** API Lambda role must allow **`sts:AssumeRole`** into the spoke **`DBDiscoverySpokeRole`** (or **`SPOKE_ROLE_NAME`** env on API).  
2. **Spoke:** That role’s **trust policy** must allow the API Lambda role (or hub) to assume it; role needs **`ec2:DescribeInstances`** in the demo **region**.  
3. **Disable enrich** (S3-only `ec2_state`): set API env **`API_ENRICH_EC2_STATE=false`** — UI falls back to snapshot / discovery fields only.

---

## 10. Discovery vs “stopped” (talking point)

- **Discovery** runs **SSM Run Command** on instances that are **managed and online** in that scan. A **stopped** instance often **won’t be rescanned** on the next run the same way as a running one.  
- Rows **already** in **`inventory.json`** can still show **current stop/start** in the UI **after Reload** when **API enrich** is working, because the API calls **`DescribeInstances`** for IDs in the snapshot.

---

## 11. Related files

| Doc / path | Use |
|------------|-----|
| [COST_AND_STOP_RESOURCES.md](COST_AND_STOP_RESOURCES.md) | Idle vs teardown |
| [FULL_SETUP_IN_ORDER.md](FULL_SETUP_IN_ORDER.md) | Full setup |
| [automation/STACKSET_AUTOMATION.md](automation/STACKSET_AUTOMATION.md) | New accounts / OU |
| [automation/TIER3_RESEARCH_SHEET.md](automation/TIER3_RESEARCH_SHEET.md) | Deeper org / automation / Tier-3 ideas |
| [README.md](README.md) | Architecture + API overview |
| `inventory_ui.html` | Demo UI (`BASE_URL`) |

---

## 12. E2E automation — “recognize” new org accounts & their workloads

**Already in this POC (see §5):**

| Layer | What it does |
|--------|----------------|
| **StackSet on an OU** | New account **moved into** that OU can get **spoke IAM + SSM document** automatically (stack instances deploy). |
| **`DISCOVER_ALL_ORG_ACCOUNTS=true`** (management) | **Discovery** can **enumerate org member accounts** (minus excludes) instead of only a manual **`SPOKE_ACCOUNTS`** list. |
| **EventBridge schedule** | **Periodic** discovery refreshes **inventory.json** so **new** EC2 (SSM online, right region) appears on a **later** run. |

**What “full end-to-end” usually adds** (enterprise / Tier 3 — not all in this repo):

| Layer | Purpose |
|--------|--------|
| **Account vending** | **Control Tower** / Account Factory: new account lands in the **right OU** with a **standard baseline** (VPC, logging, etc.). |
| **Org lifecycle events** | **EventBridge** on account create / move → **Lambda / Step Functions** to update **allowlists**, trigger **StackSet** ops, or **invoke discovery** once bootstrap finished. |
| **Guardrails** | **SCPs**, **Config**, mandatory tags — “recognize” **policy compliance**, not only **inventory**. |
| **Workflow** | Ticket/approval before an account is **in scope** for discovery (audit, GDPR, etc.). |

**Honest boundary:** This solution **discovers** **SSM-managed Linux EC2** and **DB signals** in configured **regions**. It does **not** by itself **create** instances or **infer** every AWS resource type; new members still need **standardized EC2 + instance profile** in regions you scan.

**Sound bite if they push on E2E:**

> *“We automate the **repeatable** parts: **OU-targeted** bootstrap and **org-wide account discovery** in Lambda, plus a **schedule** to refresh inventory. **Full** onboarding pipelines layer **account vending**, **org events**, and **governance** on top so every new member is **standardized first**, then **discovered** automatically—see our **Tier 3** notes for that roadmap.”*

---

## 13. Code map — what each part does (brief)

Use this when someone asks *“what does this file do?”* during or after the demo.

### Lambdas (management account)

| File | Role |
|------|------|
| **`lambda/api_handler.py`** | **API Lambda** (`db-discovery-api`). Handles **GET** routes from API Gateway: **`/health`**, **`/regions`**, **`/accounts`**, **`/accounts/{id}/instances`**, etc. Reads the **S3 snapshot** (`RESULTS_S3_BUCKET` / `RESULTS_S3_KEY`), filters by query params, **groups** flat rows by `instance_id` for the UI. Optionally **assumes** the spoke role and calls **`ec2:DescribeInstances`** to attach **live `ec2_state`** for red/green UI (`API_ENRICH_EC2_STATE`, `SPOKE_ROLE_NAME`). Returns **JSON + CORS** headers for `inventory_ui.html`. |
| **`lambda/discovery_handler.py`** | **Discovery Lambda** (`db-discovery`). Resolves which **spoke accounts** to scan (manual list and/or **`DISCOVER_ALL_ORG_ACCOUNTS`** via Organizations). For each account/region: **STS AssumeRole** → **SSM** lists **Linux + Online** instances → **EC2 DescribeInstances** for **type, tags, `ec2_state`** → **SendCommand** to run **`discovery_python.py`** → parses JSON stdout into **flat inventory records** (including **`ec2_state`**) → merges all accounts and **writes one JSON object** to **S3** (FinOps snapshot). |
| **`lambda/lambda_function.py`** | **Zip entry shim**: re-exports **`lambda_handler`** from **`discovery_handler`** so the console handler can be set to **`lambda_function.lambda_handler`** while keeping logic in **`discovery_handler.py`**. |

### On the EC2 instance (SSM Run Command)

| File | Role |
|------|------|
| **`ssm/discovery_python.py`** | Runs **on the spoke EC2** (no SSH — SSM pulls/downloads it). **Read-only** checks for **MySQL / PostgreSQL / MongoDB** (processes, ports, simple metadata), plus **RAM/CPU** hints, returns **one JSON** object (`databases[]`, `discovery_status`) to stdout. |

### Spoke bootstrap & IAM (Infra-as-code / reference)

| Path | Role |
|------|------|
| **`automation/spoke-bootstrap-stackset.yaml`** | **CloudFormation StackSet** template: deploys **spoke role**, **EC2 instance profile**, **SSM document** association across **OUs or accounts** so instances can be **managed** and **discovered**. |
| **`ssm/ssm-document.json`** | Defines the **SSM document** that runs the **shell/bootstrap** to execute **`discovery_python.py`** (align with **`SSM_DOCUMENT`** env on the discovery Lambda). |
| **`iam/*.json`** | **Example policies**: discovery Lambda (S3, STS, SSM, org read), **API** Lambda (S3 read + **STS** for enrich), **spoke role** trust + permissions, **EC2** SSM instance profile. Adjust ARNs and bucket names for your accounts. |

### UI & schema

| Path | Role |
|------|------|
| **`inventory_ui.html`** | Static **dashboard**: calls the **API** (`BASE_URL`), **region/account** filters, **KPI** cards, **topology** (row-focused), **EC2 state** styling, theme morph. No build step — open in browser or host on S3/CloudFront. |
| **`schema/example-record.json`** | **Example** shape of one inventory row (documentation / tests). |
