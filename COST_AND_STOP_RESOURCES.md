# Cost & How to Stop Resources When Not in Use

Use this list to know what can bill you and how to stop or remove it when you're done.

---

## When not using the project — do this

Follow these steps whenever you’re taking a break or not actively testing so you don’t get charged more than needed.

### Must do (stops most cost)

**1. Stop the EC2 instance (spoke account)**

- Switch to the **spoke** account.
- **Services** → **EC2** → **Instances**.
- Select your instance (checkbox).
- **Actions** → **Instance state** → **Stop instance**.
- Wait until **Instance state** shows **Stopped**.

That’s the only resource that runs 24/7 and costs by the hour. Stopping it removes almost all cost.

---

### Optional (if you want to avoid any other charges)

**2. Don’t schedule discovery (management account)**

- **Lambda** → **db-discovery** → **Configuration** → **Triggers**.
- If you see **EventBridge** (or any trigger), remove it so the function doesn’t run on a schedule.  
  (If there are no triggers, you’re fine — it only runs when you click Test.)

**3. Pause or remove data (management account)**

- **DynamoDB** → **Tables** → **db-discovery-results**.  
  - To keep data but avoid writes: just leave it (on-demand cost is tiny if you’re not calling the API or running discovery).  
  - To remove cost: **Delete table** (you can recreate it later from FULL_SETUP_IN_ORDER.md Step 2).

**4. S3 and API**

- **S3** and **API Gateway** only cost when you use them (storage/requests). You can leave the bucket and API as-is.  
- If you want zero S3 cost: **S3** → **my-db-discovery-bucket** → empty all objects → **Delete** bucket (re-create and re-upload the script when you use the project again).

---

### When you want to use the project again

- **Spoke account** → **EC2** → **Instances** → select the instance → **Actions** → **Instance state** → **Start instance**.
- Wait until it’s **Running** and (after a few minutes) **Online** in **Systems Manager** → **Fleet Manager**.
- Then run discovery from the management account (Lambda → db-discovery → Test) as usual.

---

## Resources that can incur cost

| Resource | Where | What it costs | How to stop / avoid cost |
|----------|--------|----------------|---------------------------|
| **EC2 instance** | Spoke account | Instance hours (e.g. t2.micro ~$0.01/hr) | **Stop** or **Terminate** when not using. EC2 → Instances → Select → **Instance state** → **Stop instance** (or **Terminate** to delete). |
| **S3 bucket** (my-db-discovery-bucket) | Management account | Storage + requests (tiny for one script) | **Empty** bucket then **Delete** bucket when done. Or leave; cost is minimal for one small file. |
| **DynamoDB table** (db-discovery-results) | Management account | On-demand: pay per read/write | **Delete table** when done. DynamoDB → Tables → db-discovery-results → **Delete**. |
| **Lambda** (db-discovery, db-discovery-api) | Management account | Invocations + compute time (free tier usually covers light use) | No "stop"; they only run when invoked. Remove triggers (e.g. EventBridge) so they don’t run on a schedule. To remove: delete the functions. |
| **API Gateway** (db-discovery-api) | Management account | Requests (free tier often covers demo use) | No "stop"; you only pay when someone calls the API. To remove: delete the API. |

---

## Resources that do NOT cost money

- **IAM** roles and policies (free)
- **SSM** documents (free)
- **SSM Run Command** (included; no extra charge for normal use)

---

## Quick “stop everything” checklist (when not using)

**Spoke account**

1. **EC2** → **Instances** → Select instance → **Instance state** → **Stop instance**  
   - Stops instance charges. Start again when you need to run discovery.

**Management account**

2. **(Optional)** **Lambda** → Remove any **EventBridge** (or other) trigger from **db-discovery** so it doesn’t run on a schedule.  
   - You can leave the Lambdas; they only run when you click Test or call the API.

3. **(Optional)** **DynamoDB** → **db-discovery-results** → **Delete table** if you don’t need the data.  
   - Stops any read/write cost. You can recreate the table later.

4. **(Optional)** **S3** → **my-db-discovery-bucket** → Empty bucket → Delete bucket.  
   - Only if you want zero S3 cost; re-create and re-upload the script when you use discovery again.

5. **(Optional)** **API Gateway** → Your API → **Actions** → **Delete API** if you don’t need the API.  
   - Stops API request charges.

---

## Full teardown (delete everything, no ongoing cost)

If you want to remove the whole setup:

**Spoke account**

- **EC2**: Terminate the instance (or at least Stop it).
- **IAM**: Delete roles **EC2-SSM-Discovery-Role** and **DBDiscoverySpokeRole** (remove policies first if needed).
- **SSM**: Delete document **DBDiscovery** (optional; documents don’t cost).

**Management account**

- **Lambda**: Delete functions **db-discovery** and **db-discovery-api**.
- **API Gateway**: Delete the **db-discovery-api** API.
- **DynamoDB**: Delete table **db-discovery-results**.
- **S3**: Empty and delete bucket **my-db-discovery-bucket**.
- **IAM**: Delete roles **DBDiscoveryLambdaRole** and **DBDiscoveryApiRole** (and their policies).

---

## Summary

- **Main cost:** EC2 instance (spoke). **Stop** or **Terminate** when not in use.
- **Small / free-tier:** S3, DynamoDB, Lambda, API Gateway for light use.
- **Free:** IAM, SSM documents.

Keeping only the **EC2 instance stopped** when you’re not testing will cut most of the cost; the rest is usually negligible until you scale up.
