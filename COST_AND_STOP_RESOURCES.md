# Cost & How to Stop Resources When Not in Use

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
