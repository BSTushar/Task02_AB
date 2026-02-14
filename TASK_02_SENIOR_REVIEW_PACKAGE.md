# Task_02: Senior Review Package — Database Discovery POC

**Confidentiality Notice:** This document is confidential and proprietary to AIRBUS. Unauthorized distribution, disclosure, or use is strictly prohibited.

**Document type:** Proof-of-concept with senior review readiness  
**Status:** POC — not production  
**Authors:** Intern team (2 members)

---

## 1. WORKING IMPLEMENTATION (MANDATORY)

### Implementation Artifacts

| Component | Location | Status |
|-----------|----------|--------|
| IAM policies | `iam/*.json` | Real JSON, deployable |
| SSM discovery script | `ssm/discovery_python.py` | Real Python, runnable |
| SSM document | `ssm/ssm-document.json` | Real SSM document definition |
| Discovery Lambda | `lambda/discovery_handler.py` | Real Python, runnable |
| API Lambda | `lambda/api_handler.py` | Real Python, runnable |
| DynamoDB schema | `schema/dynamodb-table.json` | Real table definition |
| Example record | `schema/example-record.json` | Real attribute structure |
| API config | `api/api-gateway-config.md` | Real endpoints and curl |
| Execution guide | `EXECUTION_GUIDE.md` | Real CLI commands |

### What Each File Does

| File | What it does | Owner |
|------|--------------|-------|
| `iam/spoke-account-trust-policy.json` | Lets management account assume the spoke role. Trust boundary. | Intern B |
| `iam/spoke-account-role-policy.json` | Permissions for spoke role: EC2 describe, SSM send/get command. | Intern B |
| `iam/management-discovery-lambda-policy.json` | Permissions for Discovery Lambda: assume spoke role, DynamoDB write, logs. | Intern B |
| `iam/ec2-instance-ssm-policy.json` | Permissions for EC2: SSM agent, S3 GetObject to fetch discovery script. | Intern B |
| `iam/api-lambda-policy.json` | Permissions for API Lambda: DynamoDB read only, logs. | Intern B |
| `ssm/discovery_python.py` | Runs on EC2. Detects MySQL/PostgreSQL/MongoDB, gets version/size, outputs JSON. | Intern A |
| `ssm/ssm-document.json` | SSM document definition. Fetches script from S3 and runs it on instance. | Intern A |
| `lambda/discovery_handler.py` | Orchestrator. Assumes spoke role, lists instances, sends SSM command, parses output, writes DynamoDB. | Intern A |
| `lambda/api_handler.py` | API handler. Reads DynamoDB, returns JSON for /health, /accounts, /databases. | Intern B |
| `schema/dynamodb-table.json` | DynamoDB table definition: PK account_id, SK instance_db_id. | Intern A (schema), Intern B (consumes) |
| `schema/example-record.json` | Example of one stored item. Shared reference for both interns. | Both |
| `api/api-gateway-config.md` | API routes, curl examples, response format. | Intern B |
| `EXECUTION_GUIDE.md` | Step-by-step setup: where to click, what to type. | Intern B |

### Example API Calls and JSON Output

**Health:**
```bash
curl -X GET "https://API_ID.execute-api.eu-west-1.amazonaws.com/prod/health"
```
```json
{"status": "ok", "total_records": 42}
```

**Accounts:**
```bash
curl -X GET "https://API_ID.execute-api.eu-west-1.amazonaws.com/prod/accounts"
```
```json
{"accounts": ["123456789012", "987654321098"]}
```

**Instances for account:**
```bash
curl -X GET "https://API_ID.execute-api.eu-west-1.amazonaws.com/prod/accounts/123456789012/instances"
```
```json
{
  "account_id": "123456789012",
  "instances": [
    {
      "instance_id": "i-0abc123def456",
      "discovery_timestamp": "2025-02-04T10:00:00Z",
      "discovery_status": "success",
      "system_memory_mb": 4096,
      "system_cpu_cores": 2,
      "databases": [
        {"db_id": "mysql-3306", "engine": "mysql", "version": "8.0.35", "status": "running", "port": 3306, "data_size_mb": 2048}
      ]
    }
  ]
}
```

**Databases (filtered):**
```bash
curl -X GET "https://API_ID.execute-api.eu-west-1.amazonaws.com/prod/databases?engine=mysql&account_id=123456789012"
```
```json
{"databases": [{"account_id": "123456789012", "instance_id": "i-0abc123", "db_id": "mysql-3306", "engine": "mysql", "version": "8.0.35", "status": "running", "port": 3306, "data_size_mb": 2048}]}
```

---

## 2. EDGE CASE MATRIX (MANDATORY)

| Scenario | What happens | How it is detected | How it is handled | What is returned via API | Why this is safe |
|----------|--------------|--------------------|-------------------|---------------------------|------------------|
| EC2 without SSM agent | Instance never appears in discovery | `DescribeInstanceInformation` excludes it | Skipped; not sent command; logged | Not in results; does not appear in `/accounts/{id}/instances` | No access attempted; no credentials used |
| EC2 with SSM but agent offline | Instance may appear with `PingStatus != Online` | Filter: `PingStatus == "Online"` only | Excluded from target list | Not in results | No command sent; no impact on instance |
| SSM permission denied | `SendCommand` or `GetCommandInvocation` fails | Exception caught; status from SSM | Per-instance: record with `discovery_status: "failed"`, `error` field | API returns record with `discovery_status: "failed"` | Failure isolated; other instances still processed |
| Database installed but service stopped | Binary present, process not running | Script checks `pgrep` vs `command -v` | `status: "installed"` stored; `data_size_mb: 0` | API returns `status: "installed"` | Read-only; no start/stop attempted |
| Multiple databases on one instance | Multiple engines/ports on same host | Script enumerates by port and engine | Each DB gets separate record with unique `db_id` | API returns multiple DBs per instance | No conflict; each stored separately |
| Database in non-standard directory | Default paths not found | Script checks known dirs only | `data_size_mb: 0`; engine/version still detected if process running | Partial data; sizing may be 0 | Read-only; no path injection |
| Unsupported/unknown DB engine | Not in detection list (MySQL, PostgreSQL, MongoDB) | Not detected by script | Not returned; instance may show `db_id: "none"` if no known DBs | `databases: []` or `db_id: "none"` | No guessing; explicit scope |
| Legacy OS not fully supported | Missing tools or different `/proc` layout | Script may fail or return partial | SSM command fails; record with `discovery_status: "failed"` | API returns failure record | No modification of OS; failure logged |
| Partial command failure | Some instances succeed, others fail | Per-instance `GetCommandInvocation` status | Success: parsed and stored; failure: stored with `discovery_status: "failed"` | Mix of success and failure records | Partial results preserved |
| Lambda timeout | Lambda exceeds configured timeout | Lambda runtime terminates | In-flight work lost; no DynamoDB write for that run | Previous discovery data remains; API returns last successful state | No partial/corrupt write; idempotent on retry |
| Cross-account assume-role failure | STS `AssumeRole` throws | Exception in `get_spoke_client` | Caught; account skipped; logged | Account not in results; no record for that account | Other accounts still processed |
| API request during incomplete discovery | Discovery run in progress | N/A | API reads current DynamoDB state | May return mix of old and new; no transactional consistency | Read-only; no race corruption |
| Instance termination during scan | Instance disappears mid-run | SSM may return `Failed` or `Terminated` | `GetCommandInvocation` returns failure status | Record with `discovery_status: "failed"` | No impact on other instances; safe to retry |

---

## 3. SECURITY & COMPLIANCE DEEP DIVE

### IAM Trust Boundaries

- **Management account:** Lambda execution role (`DBDiscoveryLambdaRole`). Trusts `lambda.amazonaws.com`. No cross-account trust in management.
- **Spoke account:** Role `DBDiscoverySpokeRole` trusts management account principal. Only management can assume it.
- **Instance:** Instance profile for EC2. Trusts `ec2.amazonaws.com`. Used by SSM agent and for S3 GetObject of discovery script.

Trust flow: Management Lambda → STS AssumeRole → Spoke role → SSM SendCommand. No trust in reverse.

### Minimal Permissions

| Role | Permissions | Rationale |
|------|-------------|-----------|
| Discovery Lambda | `sts:AssumeRole` (spoke), `dynamodb:PutItem`/`BatchWriteItem`/`Query`/`GetItem`/`Scan`, `logs:*` | Assume only; write only to discovery table |
| Spoke role | `ec2:Describe*`, `ssm:DescribeInstanceInformation`, `ssm:SendCommand`, `ssm:GetCommandInvocation`, `ssm:ListCommands` | No EC2 modify; SSM read and execute only |
| Instance profile | `ssm:UpdateInstanceInformation`, `s3:GetObject` (discovery bucket) | SSM agent plus script fetch only |
| API Lambda | `dynamodb:GetItem`/`Query`/`Scan`/`BatchGetItem`, `logs:*` | Read-only |

### No Credentials Exposed

- No long-lived cross-account credentials. STS AssumeRole issues temporary credentials.
- No SSH keys. All access via SSM.
- No hardcoded secrets. S3 bucket name from env.
- Discovery script fetched from S3; no inline secrets.

### CloudTrail Auditability

| Action | CloudTrail event |
|--------|------------------|
| AssumeRole | `AssumeRole` with source identity |
| SendCommand | `SendCommand` with document name, instance IDs |
| DynamoDB write | `PutItem` / `BatchWriteItem` |
| API Gateway | `Invoke` (if using IAM auth) |

All actions are logged. No silent operations.

### SSM Commands Are Non-Intrusive

- Script runs: `pgrep`, `mysql --version`, `psql --version`, `du`, read `/proc`. No DDL, DML, or config writes.
- No connection to databases. No credentials used.
- Execution uses instance IAM role; scope limited to read-only system introspection.

### Production Policy Compliance

- Read-only discovery. No changes to instances or databases.
- No production data accessed. Only metadata (processes, versions, sizes).
- Scope limited to SSM-managed instances. No network scanning or port probing beyond script logic.
- Cross-account access follows least privilege and is auditable.

### Approvals to Scale

- Security review of IAM policies per account.
- Approval for SSM Run Command in production accounts.
- Approval for cross-account assume role per spoke.
- Change control for SSM document and discovery script updates.

### What the System Is NOT Allowed to Do

- Connect to databases (no JDBC, no ODBC).
- Modify configuration files.
- Install or remove software.
- Use SSH or RDP.
- Access application data.
- Modify IAM or security groups.
- Execute commands not defined in the SSM document.

---

## 4. SENIOR-LEVEL REVIEW QUESTIONS (15+)

### Q1: What breaks first at scale?

**Answer:** SSM Run Command rate limits (e.g. 60 commands/second per account). With many instances, we send one command per account; batching helps. At larger scale, we would need to batch instances per command or add throttling/backoff. DynamoDB scan is also O(n); for production we would add a GSI and pagination.

### Q2: What data could be inaccurate?

**Answer:** Data size (`data_size_mb`) if the DB uses non-standard directories. Version if the binary is in an unexpected path. System memory/CPU at discovery time; not continuous. Discovery is point-in-time; data can be stale until next run.

### Q3: How do you prevent stale data?

**Answer:** We do not. This is batch discovery (e.g. daily). Consumers should use `discovery_timestamp` to assess freshness. A TTL or “last seen” field could be added; not implemented in this POC.

### Q4: How would this impact prod during peak hours?

**Answer:** SSM commands add CPU/memory load. We use `du` and read `/proc`; impact is low but not zero. Recommendation: run during low-traffic windows (e.g. 02:00 UTC). No DB connections, so no DB load.

### Q5: What happens if someone misconfigures IAM?

**Answer:** Assume role fails → account skipped, logged. Over-permissive spoke role → same behavior; we do not use extra permissions. Under-permissive → SendCommand or GetCommandInvocation fails → failure record stored. No data corruption; failures are visible.

### Q6: Why didn’t you choose Agentless (e.g. SSM Agentless)?

**Answer:** Agentless requires different setup and may not be available in all accounts. SSM Agent is standard for managed instances. We chose the most common pattern for POC.

### Q7: Why not use SSH with Fleet Manager or a bastion?

**Answer:** SSH requires key management and open ports. SSM is IAM-based, auditable, and avoids keys. Constraint was explicit: no SSH.

### Q8: Why DynamoDB instead of RDS?

**Answer:** Serverless, no connection management, scales with reads. RDS would need schema migrations and connection pooling. For read-heavy, document-style data, DynamoDB fits. Trade-off: no complex queries; we use Query/Scan.

### Q9: Why scan instead of query for /databases?

**Answer:** POC scale; scan is simple. For production we would add a GSI on `engine` or `account_id` and use Query. We acknowledge this does not scale to large tables.

### Q10: What if the discovery script is maliciously modified in S3?

**Answer:** Risk: modified script could run arbitrary commands. Mitigation: S3 bucket access controlled; enable versioning and integrity checks. Instance role has GetObject only on that path. For production: sign scripts, use private bucket, restrict access.

### Q11: Why no RDS/Aurora discovery?

**Answer:** Out of scope. RDS/Aurora are API-managed; no SSM needed. They could be added via DescribeDBInstances. We focused on EC2-installed databases for POC.

### Q12: How do you handle regions?

**Answer:** Discovery uses the Lambda region. Multi-region requires running Lambda (or equivalent) per region or iterating regions in the Lambda. Not implemented.

### Q13: What about containers (Docker/ECS)?

**Answer:** Out of scope. Discovery runs on the host; container processes may not be visible depending on namespace. Would require container-aware logic.

### Q14: Why is there no idempotency key for discovery runs?

**Answer:** Each run overwrites records for the same `account_id` + `instance_db_id`. Last write wins. For true idempotency we would add run IDs and conditional writes; not in POC scope.

### Q15: What happens if DynamoDB is unavailable?

**Answer:** `store_results` throws; Lambda fails; CloudWatch logs the error. No retry in Lambda. For production we would add retries or DLQ.

### Q16: How would you add authentication to the API?

**Answer:** API Gateway supports IAM, API keys, or Cognito. We did not implement auth in POC. For production: IAM for internal services, API key or Cognito for external consumers.

### Q17: Why 60 seconds for command timeout?

**Answer:** Arbitrary default. `du` on large data dirs can be slow. 60s is a balance. Configurable via `COMMAND_TIMEOUT` env var. For very large instances, increase or accept timeout failures.

---

## 5. FAILURE & RISK DISCLOSURE

### Known Limitations

- Only SSM-managed instances; unmanaged instances are invisible.
- Only MySQL, PostgreSQL, MongoDB; other engines not detected.
- Batch only; not real-time.
- Single region per Lambda run.
- No container discovery.
- Scan-based API; does not scale to large tables.
- No API authentication in POC.
- No retry or DLQ for DynamoDB failures.
- No automated onboarding of unreachable instances.

### Known Risks

- **S3 script tampering:** Modified script could run arbitrary commands. Mitigate with access control and versioning.
- **Over-permissive IAM:** Could allow misuse; requires policy review.
- **Stale data:** Consumers may act on outdated inventory; document `discovery_timestamp`.
- **Lambda timeout:** Large fleets may not complete in one run; consider chunking.
- **SSM rate limits:** High instance counts may hit limits; add throttling.

### Assumptions

- SSM agent is installed and managed instances are configured.
- Instance has network path to SSM (VPC endpoints or internet).
- Instance has IAM role with SSM and S3 permissions.
- Python 3 and required CLI tools exist on instances.
- S3 bucket is in the same region or accessible.
- Spoke accounts trust the management account for assume role.
- Linux instances only (platform filter).

### Intentionally NOT Implemented

- RDS/Aurora discovery.
- Container discovery.
- Multi-region discovery.
- API authentication.
- Real-time or event-driven discovery.
- Automated remediation for unreachable instances.
- Idempotency keys or run IDs.
- DynamoDB retries/DLQ.
- Pagination for API responses.
- GSI for efficient querying.

### Why These Decisions Are Acceptable for POC

- POC scope is EC2-installed DBs; RDS/containers are extensions.
- Daily batch is sufficient for asset inventory.
- Single region keeps setup simple.
- No auth reduces setup for demo; production would add it.
- Manual onboarding of unreachable instances is acceptable at small scale.
- Last-write-wins is sufficient for POC; no strong consistency requirement.
- Failures are visible in logs and API; no silent data loss.

---

## 6. LIVE DEMO WALKTHROUGH

### Who Says What (Division)

| Step | Who speaks | What to say |
|------|------------|-------------|
| Pre-Demo | Intern B | Intro and setup |
| Step 1 (Architecture) | Intern A | Architecture flow |
| Step 2 (Trigger Discovery) | Intern A | Discovery Lambda, SSM |
| Step 3 (SSM Command) | Intern A | SSM document, detection logic |
| Step 4 (DynamoDB) | Intern A | Data storage, schema |
| Step 5 (API Call) | Intern B | API endpoints, consumption |
| Step 6 (Failure Demo) | Intern A or B | Edge cases |
| Step 7 (Disclaimers) | Intern B | Limitations |

---

### Pre-Demo (2 min) — Intern B

- Open AWS Console: Lambda, SSM, DynamoDB, API Gateway.
- Ensure Discovery Lambda has run at least once.
- Have Postman or terminal ready for curl.
- **Say:** "This is a proof-of-concept. We will show working discovery, storage, and API. Limitations will be stated explicitly."

### Step 1: Architecture (1 min) — Intern A

- Show architecture diagram.
- **Say:** "Management account runs the Discovery Lambda. It assumes a role in each spoke, runs SSM commands on EC2, parses output, and stores in DynamoDB. The API reads from DynamoDB."

### Step 2: Trigger Discovery (2 min) — Intern A

- Lambda → `db-discovery` → Test → Create test event `{}` → Test.
- Show execution result: `statusCode 200`, `discovered: N`.
- Open CloudWatch Logs: "Assume role, SendCommand, discovered count."
- **Say:** "Discovery assumes the spoke role and sends SSM Run Command. You see the number of records discovered."

### Step 3: SSM Command (1 min) — Intern A

- SSM → Run Command → Command history.
- Show recent command, status Success or Failed.
- **Say:** "The SSM document ran on each instance. It detects MySQL, PostgreSQL, MongoDB—version and sizing. Output is returned to the Lambda."

### Step 4: DynamoDB (1.5 min) — Intern A

- DynamoDB → Tables → `db-discovery-results` → Explore items.
- Show `account_id`, `instance_id`, `engine`, `version`, `data_size_mb`.
- **Say:** "Each instance and database is stored. We have engine, version, data size, system sizing. Note `discovery_status` for success or failure."

### Step 5: API Call (2 min) — Intern B

- Run:
  ```bash
  curl "https://API_ID.execute-api.eu-west-1.amazonaws.com/prod/health"
  curl "https://API_ID.execute-api.eu-west-1.amazonaws.com/prod/accounts"
  curl "https://API_ID.execute-api.eu-west-1.amazonaws.com/prod/accounts/ACCOUNT_ID/instances"
  curl "https://API_ID.execute-api.eu-west-1.amazonaws.com/prod/databases?engine=mysql"
  ```
- Show JSON responses.
- **Say:** "The API exposes data for dashboards or CMDB. Filtering by account and engine works."

### Step 6: Failure Demo (Optional, 1 min) — Intern A or B

- Show an instance with `discovery_status: "failed"` or `db_id: "none"`.
- **Say:** "Failed discoveries are stored with error details. Instances without known DBs show `db_id: none`. No silent drops."

### Step 7: Disclaimers (1 min) — Intern B

- **Say:** "Limitations: only SSM-managed instances; MySQL, PostgreSQL, MongoDB; batch only; no RDS or containers; no API auth in POC; single region. This is not production-ready. We would add auth, retries, GSI, and pagination for production."

### Expected Outputs

| Step | Expected |
|------|----------|
| Trigger | Lambda returns 200, `discovered` > 0 or 0 |
| SSM | Command in history with Success or Failed |
| DynamoDB | Items with `account_id`, `instance_id`, `engine`, etc. |
| API | JSON with `status`, `accounts`, `instances`, or `databases` |

### Safe Failures to Demonstrate

- Invoke Discovery Lambda with invalid SPOKE_ACCOUNTS → assume fails, account skipped.
- Show instance with `discovery_status: "failed"` → demonstrates failure handling.

---

## 7. OWNERSHIP & COLLABORATION

### Intern A: Discovery Logic, Lambda, SSM, Data Parsing

| Responsibility | Files | Explains in demo |
|----------------|-------|------------------|
| Discovery Lambda | `lambda/discovery_handler.py` | Steps 1–4 (architecture, trigger, SSM, DynamoDB) |
| SSM document & script | `ssm/discovery_python.py`, `ssm/ssm-document.json` | How detection works |
| DynamoDB schema | `schema/dynamodb-table.json` | Record format |
| Edge case handling | In discovery_handler, discovery_python | Failure demo |

### Intern B: IAM, API Gateway, Validation, Demo

| Responsibility | Files | Explains in demo |
|----------------|-------|------------------|
| IAM policies | `iam/*.json` | Security if asked; setup in pre-demo |
| API Lambda | `lambda/api_handler.py` | Step 5 (API call) |
| API config | `api/api-gateway-config.md` | Endpoints, consumers |
| Execution guide | `EXECUTION_GUIDE.md` | Setup flow |
| Demo orchestration | Runs demo, intro, disclaimers | Pre-demo, Step 5, Step 7 |

### Who Does What (Summary)

| Task | Intern A | Intern B |
|------|----------|----------|
| Speaks architecture & discovery | ✓ | |
| Speaks API & security | | ✓ |
| Speaks limitations | | ✓ |
| Runs demo (clicks, triggers) | Triggers Lambda, shows SSM/DynamoDB | Runs API calls, shows intro/outro |
| Answers discovery questions | ✓ | |
| Answers IAM/API questions | | ✓ |

### Integration

- Schema: Intern A defines DynamoDB keys and attributes; Intern B consumes in API.
- IAM: Intern B defines roles; Intern A depends on assume role and SSM permissions.
- Edge cases: Intern A implements handling; Intern B documents and demos.
- Demo: Intern B runs script; Intern A covers Lambda/SSM steps; both can answer Q&A.

### Review Between Interns

- Schema and attribute names agreed before coding.
- IAM policies reviewed for least privilege.
- Cross-check of failure handling in discovery vs API behavior.
- Joint run-through of demo with "who says what" before review.

### Handling Gaps

- Schema mismatches: resolved via shared `schema/example-record.json`.
- IAM scope: reviewed against AWS docs; trimmed where possible.
- API path handling: aligned with API Gateway resource structure.

---

## 8. FINAL SENIOR REVIEW SELF-CHECK

### What Would a Principal Engineer Push Back On?

- **Scan at scale:** Would request GSI + Query and pagination.
- **No auth:** Would require IAM or API key for any non-internal use.
- **No retries:** Would want DynamoDB retries or DLQ.
- **Single region:** Would question multi-region strategy.
- **S3 script integrity:** Would ask for signing or checksums.
- **Timeout handling:** Would want clearer behavior when Lambda times out mid-run.
- **Stale data:** Would want TTL or explicit "last seen" semantics.

### What Would Need Rework for Production?

- API: add auth, pagination, rate limiting.
- DynamoDB: add GSI, consider TTL for old records.
- Discovery: add retries, chunking for large fleets, multi-region.
- SSM: document versioning, script signing.
- Observability: structured logging, metrics, alarms.
- Security: formal review of IAM, S3 access, and SSM document.

### What Would You Improve With 2 More Weeks?

- GSI on `engine` and `account_id` for API queries.
- API pagination and optional auth (API key).
- RDS/Aurora discovery via API.
- TTL or "last seen" for stale data handling.
- Lambda retries and DLQ for DynamoDB.
- Multi-region discovery loop.
- Unit tests for discovery and API logic.
- Terraform or CloudFormation for full deployment.

---

*Document version: 1.0 | Last updated: 2025-02-04*
