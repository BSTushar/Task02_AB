# Demo runbook — Friday (cost, flow, Q&A)

Use this before/after the demo and as speaker notes. Pair with [COST_AND_STOP_RESOURCES.md](COST_AND_STOP_RESOURCES.md) and [FULL_SETUP_IN_ORDER.md](FULL_SETUP_IN_ORDER.md).

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

## 8. Related files

| Doc / path | Use |
|------------|-----|
| [COST_AND_STOP_RESOURCES.md](COST_AND_STOP_RESOURCES.md) | Idle vs teardown |
| [FULL_SETUP_IN_ORDER.md](FULL_SETUP_IN_ORDER.md) | Full setup |
| [automation/STACKSET_AUTOMATION.md](automation/STACKSET_AUTOMATION.md) | New accounts / OU |
| [README.md](README.md) | Architecture + API overview |
| `inventory_ui.html` | Demo UI (`BASE_URL`) |
