# Research sheet: Current architecture vs Tier 3 automation

**PDF:** Open [`TIER3_RESEARCH_SHEET.html`](TIER3_RESEARCH_SHEET.html) in a browser → **Ctrl+P** → **Save as PDF** / **Microsoft Print to PDF**.

**Purpose:** Decide what “Tier 3” would change, cost/levers, and architecture impact vs what you have today.

**Audience:** Team / mentor — not a commercial quote. Dollars are **order-of-magnitude patterns**, not your invoice.

---

## 1. What the current architecture does (Task_02)

| Layer | What it does |
|--------|----------------|
| **Hub (management account)** | `db-discovery` Lambda assumes into spokes, runs SSM, merges results, writes **`discovery/inventory.json`** to S3. Optional EventBridge schedule. |
| **API** | `db-discovery-api` reads S3; REST paths for health, regions, accounts, instances, databases. |
| **UI** | `inventory_ui.html` — region + account dropdowns, instance table, engine chart. |
| **Spoke** | `DBDiscoverySpokeRole` (hub can assume), EC2 role/profile (SSM + S3 read for script), SSM document `DBDiscovery`, script from hub bucket. |
| **Discovery method** | **No SSH** — SSM Run Command + `discovery_python.py` (MySQL / PostgreSQL / MongoDB on **EC2 only**). |
| **Multi-account** | Explicit **`SPOKE_ACCOUNTS`** and/or **`DISCOVER_ALL_ORG_ACCOUNTS`** (org management). |
| **Multi-region** | **`DISCOVERY_REGIONS`** + per-region SSM document where stacks deploy. |

### Why Tier 1 is worth defending (talking points)

Tier 1 here means: **cross-account discovery that works** (SSM, no SSH), **repeatable spoke prerequisites** (StackSet IAM + SSM document), **scheduled or on-demand runs**, and optional **org-wide account discovery** — without running a full landing-zone program.

| Argument | Why it holds |
|----------|----------------|
| **Outcome-first** | Delivers the business question (“what DBs sit on EC2, where?”) across accounts and regions with an API/UI — not just a one-off script in one account. |
| **Automates the brittle part** | The pieces that are easy to get wrong at scale — **per-spoke IAM and the SSM document** — are **Infrastructure-as-Code** and **pushed by StackSet** to an OU. That is real platform behaviour, not a manual checklist. |
| **Controlled blast radius** | Fewer org-wide services (Config, org GuardDuty, dense SCP sets) means **lower cost**, **faster delivery**, and **easier rollback** for a PoC or pilot. |
| **Honest scope** | Tier 1 does not pretend EC2 or databases appear by magic; it separates **inventory** from **workload provisioning** — the same separation most enterprises use. |
| **Composable** | The discovery pipeline (Lambda → S3 → API) is **unchanged** when you add Tier 3; Tier 3 **wraps** operations (trail, Config, SCPs), so Tier 1 is not throwaway work. |

**One sentence for a slide:** *Tier 1 proves automated cross-account DB visibility with minimal org dependencies; Tier 3 adds enterprise controls around the same mechanism.*

### How to improve from Tier 1 toward Tier 3 (practical phases)

Treat Tier 3 as **layers you turn on when the org asks for evidence, guardrails, or scale** — not a single “big bang.”

| Phase | Focus | What you add | Benefit for *this* project |
|-------|--------|--------------|---------------------------|
| **A — Harden Tier 1** | Close operational gaps | Org-scoped **S3 bucket policy**; **`DISCOVER_ALL_ORG_ACCOUNTS=true`** (or automated list); **StackSet** only on intended OUs; **operational runbook** (failed AssumeRole / SSM). | Fewer manual steps; new accounts in target OU get bootstrap without ad hoc IAM. |
| **B — Audit & telemetry** | Prove *who did what* | **Organization CloudTrail** (trail → central bucket, optional **log archive account**); **alarms** on discovery Lambda errors / empty snapshots. | Defensible for security reviews; easier RCA when a spoke “disappears” from inventory. |
| **C — Compliance visibility** | Continuous posture | **AWS Config** rules that matter to you (e.g. EC2 **instance profile** attached, **SSM** managed-instance compliance, **CloudTrail** enabled) — start with a **small** rule set. | Flags drift Tier 1 would only see at next run; good demo of “beyond snapshot.” |
| **D — Guardrails** | Prevent bad states | **SCPs** (narrow allow/deny: e.g. deny S3 public buckets, require TLS on bucket — patterns your security team defines). | Reduces “someone deleted the spoke role” scenarios; complements StackSet drift (see §2.1). |
| **E — Account lifecycle** | Scale onboarding | **Control Tower** or custom **account factory** (VPC, logging, Config, baseline tags); **EventBridge** on account creation → ticket or pipeline. | New accounts enter the org with the **same baseline** as your StackSet target OU story. |

**Order matters:** **A → B** gives most audit value per effort; **C** adds recurring cost (Config) — agree rule set with stakeholders; **D** needs org policy owners; **E** is a program.

**Relationship to the demo:** You can credibly say *“We shipped Tier 1 for discovery; the roadmap layers Tier 3 controls without redesigning the discovery core.”*

---

## 2. Automation “%” (rough, qualitative)

**Important:** Percentages are **operational toil removed**, not lines of code.

| Area | Today (with StackSet + schedule) | Notes |
|------|-------------------------------------|--------|
| **Spoke IAM + SSM document** | **~80–90%** | StackSet auto-deploy to OU; fixes drift only if you add drift detection. |
| **Per-account bucket policy entries** | **~0–50%** | Often manual per account unless you use **org-scoped bucket policy** (`aws:PrincipalOrgID` + role ARN pattern) or automation Lambda. |
| **Who to scan (account list)** | **~50–100%** | Manual list = low; **`DISCOVER_ALL_ORG_ACCOUNTS=true`** = high (in org management). |
| **Run discovery on a cadence** | **~100%** | EventBridge → Lambda. |
| **EC2 exists with correct profile** | **~0–20%** | StackSet does **not** launch EC2; humans / separate IaC (Terraform, Account Factory, Service Catalog) do. |
| **DB install / app ownership** | **0%** | Always application/ops responsibility; discovery only **observes**. |
| **End-to-end “new account → appears in dashboard”** | **~40–60%** | Needs StackSet auto-deploy + org discovery + org bucket policy + EC2 launched with profile + regions in env — **Tier 1–2** closes most gaps without full Tier 3. |

**Tier 3** mainly raises **governance, audit, detection, and baseline enforcement** — not necessarily “find more databases.”

### 2.1 Scenarios — Tier 1 vs Tier 3 (how the system reacts)

**Tier 1 (here):** StackSet spoke bootstrap + optional **`DISCOVER_ALL_ORG_ACCOUNTS`** + org-scoped S3 bucket policy + EventBridge schedule + `DISCOVERY_REGIONS` — *no full landing zone*.

**Tier 3 (here):** Everything Tier 1 can do **plus** enterprise glue: org trail, Config/SCPs, drift detection, account factory patterns, ticketing on lifecycle events, etc.

#### 1) New member account is added to the org

| What happens | Tier 1 | Tier 3 |
|----------------|--------|--------|
| **StackSet bootstrap** (roles + SSM doc in target regions) | Runs when the account is in the **StackSet target OU** and **Auto-deployment** is on; may take **minutes to tens of minutes**. Same for management vs spoke if root OU is targeted. | **Same** CloudFormation mechanics; often **plus** Control Tower / custom **account factory** stacks (logging, VPC, Config recorder, etc.). |
| **S3 read from EC2** (`ssm/discovery_python.py`) | Works without per-account edits if the **bucket policy** trusts the **org** + your **standard EC2 role** (e.g. `aws:PrincipalOrgID` + `PrincipalArn`/pattern). Otherwise **manual** policy (or Lambda automation) per account. | **Same** policy idea; more often **reviewed**, **versioned**, **KMS/TLS** requirements. |
| **`db-discovery` starts scanning that account** | With **`DISCOVER_ALL_ORG_ACCOUNTS=true`** (management account): next run includes new **ACTIVE** accounts (minus exclusions). With **manual `SPOKE_ACCOUNTS`**: **no** until someone **updates env** (or turns on org-wide mode). | **Same** Lambda behaviour; Tier 3 may add **workflow** (ticket → approved → account moves to OU) so onboarding is controlled, not “surprise accounts.” |
| **Dashboard shows DBs** | Only after **EC2** exists with **`EC2-SSM-Discovery-InstanceProfile`**, **Fleet Manager Online**, region listed in **`DISCOVERY_REGIONS`**, and engines are **MySQL / PostgreSQL / MongoDB on the instance** per script rules. **Neither tier launches EC2.** | **Same** visibility rules; Tier 3 may **enforce** profile / tagging via **Config/SCPs**, so fewer “we forgot the profile” gaps. |

**One-line:** Tier 1 automates **permissions + SSM assets** across accounts; Tier 3 adds **governance and alerts** so mistakes and drift are caught — **DB detection logic is unchanged.**

#### 2) New EC2 in an existing account (no new account)

| | Tier 1 | Tier 3 |
|---|--------|--------|
| Shows up in inventory | Next **`db-discovery`** run (or schedule) if **SSM Online**, **correct instance profile**, **region** in `DISCOVERY_REGIONS`. | Same; optional **Config rules** flag non-compliant instances (e.g. missing profile). |

#### 3) Someone deletes or weakens a spoke role / SSM doc

| | Tier 1 | Tier 3 |
|---|--------|--------|
| Effect | Next run: **AssumeRole** or **SSM** failures for that account/region; snapshot may **skip** or **shrink**. | Same runtime effect; **StackSet drift** + **monitoring** surface the break sooner; **SCPs** may block destructive IAM in some designs. |

---

#### Accuracy (what “correct” means — Tier 1 vs Tier 3)

| Topic | Tier 1 | Tier 3 |
|--------|--------|--------|
| **CMDB truth** | **Point-in-time** after each successful run; not real-time. | Same snapshot model unless you add streaming (out of scope here). |
| **DB detection** | Driven by **`discovery_python.py`** (processes, paths, engines supported). **False negatives** possible (custom paths, other engines, DB only in containers, etc.). Tier 3 does **not** magically improve SQL detection. | Same script accuracy; Tier 3 improves **trust that the probe could run** (baseline + compliance). |
| **Account coverage** | **High** if org-wide discovery + all spokes have roles; **low** if env list stale. | Same; Tier 3 reduces **process** failure (unapproved accounts, untracked drift), not math in the script. |

---

## 3. What “Tier 3” usually means (platform automation)

Typical building blocks (pick what you need; rarely need all on day one):

| Capability | Outcome |
|------------|---------|
| **Org-wide eventing** | EventBridge on account lifecycle / guardrail violations → Lambda → ticket / Slack / pipeline. |
| **SCPs** | Prevent destructive actions, enforce encryption, restrict regions, etc. |
| **AWS Config + conformance packs** | Continuous compliance posture; non-compliant resources flagged. |
| **Drift detection** | CloudFormation StackSets drift on spoke baseline; notify owners. |
| **Central logging** | CloudTrail org trail, S3/KMS, optional SIEM. |
| **Landing zone** | Control Tower / custom “account factory” so new accounts get baseline networking, IAM, logging automatically. |
| **FinOps hooks** | Budgets, anomaly detection, chargeback tags (optional). |

**Tier 3 does *not* replace:** DB discovery logic, S3 snapshot format, or API contract — it **wraps** operations with enterprise controls.

---

## 4. Architecture changes if you adopt Tier 3

### Minimal change to *your* discovery pipeline
- **Same:** Hub Lambda, S3 inventory, API, spoke roles, SSM document, script.
- **Add around it:**
  - **Org trail** + log archive account (pattern)
Optional:
  - **Security / audit account** aggregates findings
  - **Automation account** for pipelines (some orgs split roles)

### Likely new diagrams (conceptual)
```
Organizations
  ├─ Management (discovery + API + inventory bucket)  [may stay]
  ├─ Audit / Log archive                            [new in many Tier 3 designs]
  └─ Spokes (workloads)
       └─ StackSet baseline + (optional) account factory
```

### Integration touchpoints for *this* project
- **Bucket policy:** align with org security standards (KMS, TLS, deny insecure transport).
- **Lambda roles:** tighter boundary policies, separate discovery vs API role (you already split conceptually).
- **Secrets:** avoid long-lived keys; use roles only (you mostly do).

---

## 5. Cost — what drives the bill (not a quote)

### Usually **small** at demo / PoC scale
| Service | Cost driver |
|---------|-------------|
| **Lambda** | Invocations + duration; discovery runs batch, infrequent → often **within free tier** or **$ / month** low. |
| **API Gateway** | Per request; internal demo → **low**. |
| **S3** | One JSON + script → **cents** unless huge history/versioning. |
| **SSM** | Run Command pricing per instance per invocation — scales with **# instances × frequency**. |
| **CloudWatch Logs** | Log volume + retention. |

### Tier 3 **adds** cost (varies wildly)
| Item | Why |
|------|-----|
| **AWS Config** | Per rule × resource × region — **can grow** in large orgs. |
| **CloudTrail org trail** | Storage + optional Insights → **moderate** with retention. |
| **Security Hub / GuardDuty** (if enabled) | Per-account / per-feature pricing — **can be meaningful** at scale. |
| **KMS** | Keys + API requests if everything encrypted with CMKs. |
| **Multi-account networking** (NAT, TGW) | Often **largest** infra line item — **not caused by discovery**, but common beside Tier 3 programs. |

**Barrier isn’t usually “discovery Lambda” — it’s org-wide security/config/logging if you turn everything on.**

### Practical FinOps questions for your team
1. Which **regions** are in scope? (More regions ⇒ more Config/evaluation surface if enabled.)
2. **Discovery frequency** vs SSM bill (`rate(1 day)` vs hourly).
3. **Log retention** (30d vs 1y).
4. **Config rules**: how many are **mandatory** vs nice-to-have.

---

## 6. Should *you* “go Tier 3” for this internship task?

| Goal | Recommendation |
|------|----------------|
| **Prove cross-account EC2 DB discovery + dashboard** | **Tier 1 + StackSet** is enough: org-wide account discovery, org-scoped bucket policy, schedule, maybe Launch Template for EC2. |
| **Demonstrate enterprise readiness story** | Add **one** Tier 3 slice: e.g. **Org CloudTrail** + **one Config rule** + diagram — without building full Control Tower. |
| **Full Airbus production platform** | Tier 3 is a **program**, not a weekend task — needs security, networking, and ops sign-off. |

---

## 7. One-page summary for stakeholders

| Topic | Current (Task_02 + StackSet) | Tier 3 (typical) |
|--------|------------------------------|------------------|
| **Discover DBs on EC2 cross-account** | Yes (with roles, SSM, S3, API/UI) | Same core; Tier 3 adds guardrails around it |
| **Automate spoke prerequisites** | StackSet to OU/regions | + drift detection, SCPs, account factory |
| **Automate “who to scan”** | Manual list or org list env | Org APIs + events; may still exclude accounts via env |
| **Automate EC2 creation** | No (by design in current template) | Account Factory / Terraform / Service Catalog |
| **Cost risk** | Mostly Lambda + SSM frequency | + Config, logging, security services if enabled |
| **Timeline** | Days to stable demo | Weeks–months for real platform |

---

## 8. References in this repo

- Spoke template: `automation/spoke-bootstrap-stackset.yaml`
- Recreate / CLI flow: `automation/recreate-stackset.ps1`, `automation/STACKSET_AUTOMATION.md`
- Setup order: `FULL_SETUP_IN_ORDER.md`
- Cost stop levers: `COST_AND_STOP_RESOURCES.md`

---

*Confidentiality: align redistribution with your organization’s AIRBUS rules; this sheet is technical planning only.*
