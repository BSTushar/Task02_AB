# API Gateway Configuration & REST API Reference

## Structure

```
API: db-discovery-api
  /health          GET  -> api_handler (Lambda)
  /accounts        GET  -> api_handler
  /accounts/{accountId}         GET  -> api_handler
  /accounts/{accountId}/instances  GET  -> api_handler (same Lambda, path-based routing)
  /databases       GET  -> api_handler
```

## Lambda Integration

- Integration type: Lambda proxy integration
- Lambda: api_handler
- Enable CORS if needed for browser consumers

---

## REST API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check; returns status and total record count |
| GET | `/accounts` | List all account IDs with discovery data |
| GET | `/accounts/{accountId}` | Raw discovery records for an account |
| GET | `/accounts/{accountId}/instances` | Instances with databases, **instance_type (t-shirt size)**, and **tags** |
| GET | `/databases` | All databases; optional query params: `?engine=`, `?account_id=` |

### Response fields (per instance / per record)

| Field | Type | Description |
|-------|------|-------------|
| `instance_id` | string | EC2 instance ID |
| **`instance_type`** | string | **EC2 instance type (t-shirt size), e.g. t3.medium, m5.large** |
| **`tags`** | object | **EC2 instance tags (key-value map), e.g. `{"Name":"db-01","Env":"prod"}`** |
| `discovery_status` | string | `success` \| `failed` |
| `discovery_timestamp` | string | ISO 8601 UTC |
| `system_memory_mb` | number | Instance RAM (MB) |
| `system_cpu_cores` | number | Instance vCPUs |
| `databases` | array | List of DBs on this instance (see below) |

### Database object (inside `databases`)

| Field | Type | Description |
|-------|------|-------------|
| `db_id` | string | e.g. mysql-3306 |
| `engine` | string | mysql \| postgresql \| mongodb |
| `version` | string | e.g. 8.0.35 |
| `status` | string | running \| installed |
| `port` | number | Listening port |
| `data_size_mb` | number | Data directory size (MB) |

---

## Example cURL Requests

```bash
# Health check
curl -X GET "https://YOUR_API_ID.execute-api.eu-west-1.amazonaws.com/prod/health"

# List accounts
curl -X GET "https://YOUR_API_ID.execute-api.eu-west-1.amazonaws.com/prod/accounts"

# Get instances for account (includes instance_type and tags)
curl -X GET "https://YOUR_API_ID.execute-api.eu-west-1.amazonaws.com/prod/accounts/123456789012/instances"

# Get all databases
curl -X GET "https://YOUR_API_ID.execute-api.eu-west-1.amazonaws.com/prod/databases"

# Filter by engine
curl -X GET "https://YOUR_API_ID.execute-api.eu-west-1.amazonaws.com/prod/databases?engine=mysql"

# Filter by account
curl -X GET "https://YOUR_API_ID.execute-api.eu-west-1.amazonaws.com/prod/databases?account_id=123456789012"
```

---

## Example JSON Responses

### GET /health
```json
{"status": "ok", "total_records": 42}
```

### GET /accounts
```json
{"accounts": ["123456789012", "987654321098"]}
```

### GET /accounts/123456789012/instances
```json
{
  "account_id": "123456789012",
  "instances": [
    {
      "instance_id": "i-0abc123def456",
      "instance_type": "t3.medium",
      "tags": {
        "Name": "db-server-01",
        "Environment": "production",
        "Project": "db-discovery"
      },
      "discovery_timestamp": "2025-02-04T10:00:00Z",
      "discovery_status": "success",
      "system_memory_mb": 4096,
      "system_cpu_cores": 2,
      "databases": [
        {
          "db_id": "mysql-3306",
          "engine": "mysql",
          "version": "8.0.35",
          "status": "running",
          "port": 3306,
          "data_size_mb": 2048
        }
      ]
    }
  ]
}
```

### GET /databases
```json
{
  "databases": [
    {
      "account_id": "123456789012",
      "instance_id": "i-0abc123def456",
      "instance_type": "t3.medium",
      "tags": {
        "Name": "db-server-01",
        "Environment": "production"
      },
      "db_id": "mysql-3306",
      "engine": "mysql",
      "version": "8.0.35",
      "status": "running",
      "port": 3306,
      "data_size_mb": 2048,
      "system_memory_mb": 4096,
      "system_cpu_cores": 2,
      "discovery_timestamp": "2025-02-04T10:00:00Z"
    }
  ]
}
```
