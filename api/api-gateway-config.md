# API Gateway Configuration & REST API Reference

**Data source:** API Lambda reads **`discovery/inventory.json`** from S3 (snapshot produced by **`db-discovery`**). No DynamoDB.

## Structure

```
API: db-discovery-api
  /health                           GET  -> api_handler
  /accounts                         GET  -> api_handler
  /regions                          GET  -> api_handler
  /regions/{region}/accounts        GET  -> api_handler
  /accounts/{accountId}             GET  -> api_handler
  /accounts/{accountId}/instances   GET  -> api_handler  (optional qs: ?region=)
  /databases                        GET  -> api_handler
```

## Lambda Integration

- Integration type: **Lambda proxy integration**
- Lambda: **`db-discovery-api`** (`api_handler.lambda_handler`)
- Enable **CORS** for browser / `inventory_ui.html`

---

## REST API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health, `total_records`, **`store`: `"s3"`** |
| GET | `/accounts` | Distinct `account_id` values in current snapshot; optional `?region=` |
| GET | `/regions` | Distinct `region` values in current snapshot |
| GET | `/regions/{region}/accounts` | Accounts that have data in that region |
| GET | `/accounts/{accountId}` | Flat list of records for account; optional `?region=`, `?engine=`, `?instance_id=`, `?discovery_status=`, `?ec2_state=` |
| GET | `/accounts/{accountId}/instances` | Grouped instances + DBs; optional **`?region=`**, `?engine=`, `?instance_id=`, `?discovery_status=`, `?ec2_state=` |
| GET | `/databases` | All records; optional filters: **`?region=`**, **`?account_id=`**, **`?engine=`**, `?instance_id=`, `?discovery_status=`, `?ec2_state=` |

### Response fields (per instance / per record)

| Field | Type | Description |
|-------|------|-------------|
| `instance_id` | string | EC2 instance ID |
| `region` | string | AWS region where discovery ran |
| **`instance_type`** | string | EC2 type (e.g. t3.medium) |
| **`tags`** | object | EC2 tags |
| `discovery_status` | string | `success` \| `failed` |
| `discovery_timestamp` | string | ISO 8601 UTC |
| `system_memory_mb` | number | RAM (MB) |
| `system_cpu_cores` | number | vCPUs |
| `databases` | array | DBs on instance (grouped view) |

### Database object (inside `databases`)

| Field | Type | Description |
|-------|------|-------------|
| `db_id` | string | e.g. mysql-3306 |
| `engine` | string | mysql \| postgresql \| mongodb |
| `version` | string | e.g. 8.0.35 |
| `status` | string | running \| installed |
| `port` | number | Port |
| `data_size_mb` | number | Data dir size (MB) |

---

## Example cURL

```bash
export BASE="https://YOUR_API_ID.execute-api.REGION.amazonaws.com/prod"

curl -s "$BASE/health"
curl -s "$BASE/regions"
curl -s "$BASE/regions/eu-west-1/accounts"
curl -s "$BASE/accounts"
curl -s "$BASE/accounts/123456789012/instances?region=eu-west-1"
curl -s "$BASE/databases?engine=mysql"
curl -s "$BASE/databases?region=ap-south-1&engine=postgresql"
curl -s "$BASE/accounts/123456789012/instances?region=ap-south-1&engine=postgresql"
```

---

## Example JSON

### GET /health

```json
{"status": "ok", "total_records": 42, "store": "s3"}
```

### GET /regions

```json
{"regions": ["ap-south-1", "eu-west-1"]}
```

### GET /accounts/{accountId}/instances

Same shape as before: `account_id`, `instances[]` with `instance_type`, `tags`, `databases[]`.
