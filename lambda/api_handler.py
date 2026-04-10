import json
import logging
import os
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Browser UI (inventory_ui.html) needs CORS; API Gateway "Enable CORS" is optional if Lambda returns these.
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "GET,OPTIONS",
}

AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
S3_BUCKET = os.environ.get("S3_BUCKET", "")
RESULTS_S3_BUCKET = os.environ.get("RESULTS_S3_BUCKET", "") or S3_BUCKET
RESULTS_S3_KEY = os.environ.get("RESULTS_S3_KEY", "discovery/inventory.json")
SPOKE_ROLE_NAME = os.environ.get("SPOKE_ROLE_NAME", "DBDiscoverySpokeRole")
# Live EC2 state for /instances (red/green UI). Requires API Lambda IAM: sts:AssumeRole on spoke role.
API_ENRICH_EC2_STATE = os.environ.get("API_ENRICH_EC2_STATE", "true").lower() in ("1", "true", "yes")
API_VERSION = "2.3"


def http_response(status_code, body, is_json=True):
    headers = dict(CORS_HEADERS)
    if is_json:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(body) if not isinstance(body, str) else body
    else:
        payload = body if body is not None else ""
    return {"statusCode": status_code, "headers": headers, "body": payload}


def to_json_serializable(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, dict):
        return {k: to_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_json_serializable(v) for v in obj]
    return obj


def load_all_records():
    if not RESULTS_S3_BUCKET:
        logger.error("RESULTS_S3_BUCKET or S3_BUCKET is not set")
        return []

    s3 = boto3.client("s3", region_name=AWS_REGION)
    try:
        resp = s3.get_object(Bucket=RESULTS_S3_BUCKET, Key=RESULTS_S3_KEY)
        raw = resp["Body"].read().decode("utf-8")
        data = json.loads(raw)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("NoSuchKey", "404", "NotFound"):
            return []
        logger.exception("S3 get_object failed: %s", e)
        raise
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in inventory object: %s", e)
        return []

    if isinstance(data, list):
        return [i for i in data if isinstance(i, dict)]
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        return [i for i in data["records"] if isinstance(i, dict)]
    return []


def query_by_account(account_id):
    return [i for i in load_all_records() if isinstance(i, dict) and i.get("account_id") == account_id]


def _norm_text(v):
    return str(v).strip() if v is not None else ""


def canonical_engine_name(v):
    """Normalize engine aliases to a stable value for filtering."""
    e = _norm_text(v).lower()
    if e == "postgres":
        return "postgresql"
    return e


def _to_bool(v, default=None):
    if v is None:
        return default
    s = _norm_text(v).lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    return default


def apply_record_filters(items, qs):
    """Filter flat inventory records by common query parameters."""
    if not isinstance(qs, dict):
        qs = {}
    region_q = _norm_text(qs.get("region"))
    account_q = _norm_text(qs.get("account_id"))
    instance_q = _norm_text(qs.get("instance_id"))
    discovery_q = _norm_text(qs.get("discovery_status")).lower()
    ec2_q = _norm_text(qs.get("ec2_state")).lower()
    engine_q = canonical_engine_name(qs.get("engine"))
    db_status_q = _norm_text(qs.get("db_status")).lower()
    include_empty = _to_bool(qs.get("include_empty"), default=True)

    out = []
    for i in items:
        if not isinstance(i, dict):
            continue
        if region_q and i.get("region") != region_q:
            continue
        if account_q and i.get("account_id") != account_q:
            continue
        if instance_q and i.get("instance_id") != instance_q:
            continue
        if discovery_q and _norm_text(i.get("discovery_status")).lower() != discovery_q:
            continue
        if ec2_q and _norm_text(i.get("ec2_state")).lower() != ec2_q:
            continue
        if engine_q and canonical_engine_name(i.get("engine")) != engine_q:
            continue
        if db_status_q and _norm_text(i.get("status")).lower() != db_status_q:
            continue
        if not include_empty and _norm_text(i.get("db_id")).lower() in ("", "none", "discovery_failed"):
            continue
        out.append(i)
    return out


def group_by_instance(items):
    by_instance = {}
    for i in items:
        if not isinstance(i, dict):
            continue
        inst = i.get("instance_id", "unknown")
        tags = i.get("tags")
        if not isinstance(tags, dict):
            tags = {}
        if inst not in by_instance:
            by_instance[inst] = {
                "instance_id": inst,
                "instance_type": i.get("instance_type", "unknown"),
                "tags": tags,
                "databases": [],
                "system_memory_mb": 0,
                "system_cpu_cores": 0,
            }
        if i.get("ec2_state"):
            by_instance[inst]["ec2_state"] = i["ec2_state"]
        if i.get("db_id") and i["db_id"] not in ("none", "discovery_failed"):
            by_instance[inst]["databases"].append({
                "db_id": i.get("db_id"),
                "engine": i.get("engine"),
                "version": i.get("version"),
                "status": i.get("status"),
                "port": i.get("port", 0),
                "data_size_mb": i.get("data_size_mb", 0),
            })
        by_instance[inst]["system_memory_mb"] = i.get("system_memory_mb", 0)
        by_instance[inst]["system_cpu_cores"] = i.get("system_cpu_cores", 0)
        by_instance[inst]["instance_type"] = i.get("instance_type", "unknown")
        by_instance[inst]["tags"] = tags
        by_instance[inst]["discovery_timestamp"] = i.get("discovery_timestamp")
        by_instance[inst]["discovery_status"] = i.get("discovery_status")
    return list(by_instance.values())


def _get_spoke_ec2_client(account_id, region):
    sts = boto3.client("sts")
    role_arn = f"arn:aws:iam::{account_id}:role/{SPOKE_ROLE_NAME}"
    assumed = sts.assume_role(RoleArn=role_arn, RoleSessionName="dbdiscoveryApiEc2Enrich")
    c = assumed["Credentials"]
    return boto3.client(
        "ec2",
        region_name=region,
        aws_access_key_id=c["AccessKeyId"],
        aws_secret_access_key=c["SecretAccessKey"],
        aws_session_token=c["SessionToken"],
    )


def enrich_instances_ec2_state(instances, account_id, region):
    """Attach current EC2 state (running/stopped/...) for each instance row."""
    if not API_ENRICH_EC2_STATE or not instances or not account_id or not region:
        return
    ids = []
    for row in instances:
        iid = row.get("instance_id")
        if iid and isinstance(iid, str) and iid.startswith("i-"):
            ids.append(iid)
    if not ids:
        return
    ids = list(dict.fromkeys(ids))
    try:
        ec2 = _get_spoke_ec2_client(account_id, region)
        state_by_id = {}
        for start in range(0, len(ids), 100):
            chunk = ids[start : start + 100]
            resp = ec2.describe_instances(InstanceIds=chunk)
            for res in resp.get("Reservations", []):
                for inst in res.get("Instances", []):
                    iid = inst.get("InstanceId")
                    if iid:
                        state_by_id[iid] = (inst.get("State") or {}).get("Name") or "unknown"
        for row in instances:
            iid = row.get("instance_id")
            if iid in state_by_id:
                row["ec2_state"] = state_by_id[iid]
    except ClientError as e:
        logger.warning("EC2 state enrich failed (IAM?): %s", e)
    except Exception as e:
        logger.warning("EC2 state enrich failed: %s", e)


def _request_path(event):
    """API Gateway REST (path) vs HTTP API v2 (rawPath); greedy {proxy+} leaves path in pathParameters."""
    if not isinstance(event, dict):
        return ""
    p = event.get("rawPath") or event.get("path")
    if p:
        return str(p).rstrip("/") or "/"
    rc = event.get("requestContext") or {}
    if isinstance(rc, dict):
        http = rc.get("http")
        if isinstance(http, dict) and http.get("path"):
            return str(http["path"]).rstrip("/") or "/"
        if rc.get("path"):
            return str(rc["path"]).rstrip("/") or "/"
    pp = event.get("pathParameters") or {}
    if isinstance(pp, dict) and pp.get("proxy") is not None:
        return "/" + str(pp["proxy"]).lstrip("/")
    return ""


def _normalize_api_path(path):
    p = (path or "").strip()
    if not p:
        return ""
    if not p.startswith("/"):
        p = "/" + p
    return p.rstrip("/") or "/"


def _api_root_response():
    items = load_all_records()
    body = {
        "service": "db-discovery-api",
        "api_version": API_VERSION,
        "total_records": len(items),
        "store": "s3",
        "endpoints": [
            "/health",
            "/regions",
            "/accounts",
            "/databases",
            "/accounts/{accountId}/instances",
        ],
    }
    return http_response(200, body)


# One-segment paths that are real resources (not the stage name prefix in /prod alone)
_SINGLE_RESOURCE_SEGMENTS = frozenset({"health", "accounts", "regions", "databases"})


def _should_serve_api_root(path_segments):
    """True for '' or /{stage} alone; false for real one-segment APIs and mistaken /{accountId}."""
    if not path_segments:
        return True
    if len(path_segments) != 1:
        return False
    seg = path_segments[0]
    if seg.lower() in _SINGLE_RESOURCE_SEGMENTS:
        return False
    if seg.isdigit() and len(seg) == 12:
        return False
    return True


def _path_account_id(path_segments, path_params):
    """Resolve account id from either API Gateway path params or proxy path segments."""
    account_id = (path_params or {}).get("accountId")
    if account_id:
        return str(account_id)
    if "accounts" in path_segments:
        idx = path_segments.index("accounts")
        if idx + 1 < len(path_segments):
            candidate = path_segments[idx + 1]
            if candidate and candidate.lower() != "instances":
                return candidate
    return ""


def lambda_handler(event, context):
    if not isinstance(event, dict):
        event = {}
    path = _normalize_api_path(_request_path(event))
    path_params = event.get("pathParameters")
    if not isinstance(path_params, dict):
        path_params = {}

    path_stripped = path.rstrip("/") if path else ""
    path_segments = [p for p in path_stripped.split("/") if p]
    logger.info("path=%s path_stripped=%s path_params=%s", path, path_stripped, path_params)

    method = (event.get("httpMethod") or "").upper()
    if not method:
        rc = event.get("requestContext") or {}
        if isinstance(rc, dict):
            m = (rc.get("http") or {}).get("method") if isinstance(rc.get("http"), dict) else None
            method = (m or "").upper()
    if method == "OPTIONS":
        return http_response(200, "", is_json=False)
    qs = event.get("queryStringParameters") or {}
    if not isinstance(qs, dict):
        qs = {}

    try:
        if "/health" in path or path_stripped.endswith("/health") or path_segments == ["health"]:
            items = load_all_records()
            return http_response(
                200,
                {
                    "status": "ok",
                    "api_version": API_VERSION,
                    "total_records": len(items),
                    "store": "s3",
                },
            )

        # Bare invoke URL is often /{stage} only (e.g. /prod) — API Gateway sends one path segment.
        if _should_serve_api_root(path_segments):
            return _api_root_response()

        if path_segments and path_segments[-1].lower() == "regions" and "accounts" not in path.lower():
            items = apply_record_filters(load_all_records(), qs)
            regions = sorted(set(i.get("region") for i in items if isinstance(i, dict) and i.get("region")))
            return http_response(200, {"regions": to_json_serializable(regions)})

        # Must run before GET /accounts: /regions/{region}/accounts also ends with "accounts".
        if "regions" in path_segments and path_segments[-1].lower() == "accounts":
            try:
                idx = path_segments.index("regions")
                region = path_segments[idx + 1]
            except (ValueError, IndexError):
                return http_response(400, {"error": "Invalid region path"})
            scoped_qs = dict(qs)
            scoped_qs["region"] = region
            items = apply_record_filters(load_all_records(), scoped_qs)
            accounts = sorted(set(
                i.get("account_id")
                for i in items
                if isinstance(i, dict) and i.get("account_id")
            ))
            return http_response(200, {"region": region, "accounts": to_json_serializable(accounts)})

        is_list_accounts = (
            path_segments
            and path_segments[-1].lower() == "accounts"
            and "regions" not in path_segments
            and not path_params.get("accountId")
            and "instances" not in path.lower()
        )
        if is_list_accounts:
            items = apply_record_filters(load_all_records(), qs)
            region_q = _norm_text(qs.get("region"))
            if region_q:
                accounts = sorted(set(i.get("account_id") for i in items if isinstance(i, dict) and i.get("account_id")))
                return http_response(200, {"region": region_q, "accounts": to_json_serializable(accounts)})
            accounts = list(set(i.get("account_id", "unknown") for i in items if isinstance(i, dict) and i.get("account_id")))
            return http_response(200, {"accounts": to_json_serializable(accounts)})

        region_filter = _norm_text(qs.get("region"))
        account_id = _path_account_id(path_segments, path_params)
        if account_id:
            items = query_by_account(account_id)
            items = apply_record_filters(items, qs)
            is_instances_view = bool(path_segments and path_segments[-1].lower() == "instances")
            if is_instances_view:
                grouped = group_by_instance(items)
                enrich_instances_ec2_state(grouped, account_id, region_filter)
                return http_response(200, to_json_serializable({"account_id": account_id, "instances": grouped}))
            return http_response(200, to_json_serializable({"account_id": account_id, "records": items}))

        if path.endswith("/databases") or "/databases" in path:
            items = apply_record_filters(load_all_records(), qs)
            return http_response(200, to_json_serializable({"count": len(items), "databases": items}))

        return http_response(404, {"error": "Not found"})

    except ClientError as e:
        logger.error("AWS error: %s", e)
        return http_response(500, {"error": "Internal error"})
    except Exception as e:
        logger.exception(str(e))
        return http_response(500, {"error": "Internal error"})
