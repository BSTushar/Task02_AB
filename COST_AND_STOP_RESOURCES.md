# Cost & How to Stop Resources When Not in Use

## Operational cost — rough **per day** (USD, order of magnitude)

**Not a quote.** AWS bills per second/request/GB with regional variance; use [AWS Pricing Calculator](https://calculator.aws/) with your exact region, instance types, and invocation counts.

### Hub (management account) — **no spoke EC2 running**

Typical POC assumptions: **1× discovery/day** (EventBridge or manual), **API** used lightly for demos/tests (~100 GETs/day), **S3** holds one JSON + scripts (&lt; 1 GB), **two Lambdas**, **API Gateway**.

| Line item | Typical POC assumption | **~ USD / day** (ballpark) |
|-----------|-------------------------|----------------------------|
| **EventBridge** (scheduled rule) | 1 scheduled trigger/day | **&lt; 0.01** |
| **Lambda `db-discovery`** | 1 run/day, a few minutes, 512 MB–1 GB | **0.01 – 0.15** |
| **Lambda `db-discovery-api`** | tens–hundreds of invocations, short | **&lt; 0.01 – 0.05** |
| **API Gateway** | same order as API calls | **&lt; 0.01 – 0.05** |
| **S3** (Standard) | small object + low request rate | **&lt; 0.01** |
| **CloudWatch Logs** | default Lambda logging | **0.01 – 0.10** |
| **Hub total (EC2 stopped, light use)** | | **~ 0.05 – 0.35 / day** |

**Cheaper days:** disable **EventBridge**, stop calling **API**, keep **EC2 stopped** → hub often **under ~$0.10/day** (still not zero: storage + idle Lambda/API minimums are tiny but non‑zero until teardown).

### Spoke — **EC2** (dominant variable)

If **instances are running** 24 h, **EC2 + EBS** usually **dwarfs** the hub line items above.

| Example | **~ USD / day** (very rough) |
|---------|------------------------------|
| **t3.micro** (or similar) 24 h in e.g. **ap-south-1** | **~ 0.25 – 0.60** per instance |
| **t3.small** 24 h | **~ 0.50 – 1.20** per instance |
| **EBS** gp3 20 GB | **~ 0.02 – 0.05** (storage/month prorated ≈ **&lt; 0.01/day**) |

**Rule of thumb for this project:** **Stop spoke EC2** when not demoing; **disable EventBridge** if you do not want daily discovery invocations. See sections below.

---

## When not using the project

### Must do (stops most cost)

**1. Stop EC2 (spoke)**

- **EC2** → instance → **Stop instance**.

### Reduce background automation

**2. EventBridge (management)**

- **EventBridge** → **Rules** → disable or delete the rule that invokes **`db-discovery`** so scans do not run on a schedule.

**3. S3 (management)**

- Inventory file **`discovery/inventory.json`** + script **`ssm/*`** cost almost nothing at demo scale.
- **Empty + delete bucket** only if you want zero S3 billing and will recreate later.

**4. Lambda / API**

- **No “stop.”** Removing **EventBridge** avoids scheduled discovery invocations. **API Gateway** charges per request—negligible if unused.

---

## Resources that can incur cost

| Resource | Where | Notes |
|----------|--------|--------|
| **EC2** | Spoke | Main variable cost — **Stop** when idle. |
| **S3** | Management | Script + one JSON snapshot — usually cents. |
| **Lambda** | Management | **db-discovery** + **db-discovery-api** — free tier often covers demos. |
| **API Gateway** | Management | Per request; tiny for tests. |

**DynamoDB** table **`db-discovery-results`** is **not** used by the current S3-based design; delete it if you still have it from an old setup.

---

## Quick stop checklist

1. Spoke: **Stop EC2**.  
2. Management: remove/disable **EventBridge** rule on **db-discovery**.  
3. Optional: delete **API** / **Lambdas** / **S3 bucket** if tearing down completely.

## Full teardown (management)

- Delete **Lambdas**, **API Gateway**, **EventBridge** rules, **IAM** roles created for this project, **S3** bucket (empty first).

---

## Summary

- **Biggest lever:** **Stopped EC2**.  
- **Automation cost lever:** **EventBridge** schedule on **db-discovery**.  
- **Storage:** **S3** snapshot is FinOps-friendly versus per-item databases for this workload.
