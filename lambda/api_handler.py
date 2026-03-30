import json
import logging
import os
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
S3_BUCKET = os.environ.get("S3_BUCKET", "")
RESULTS_S3_BUCKET = os.environ.get("RESULTS_S3_BUCKET", "") or S3_BUCKET
RESULTS_S3_KEY = os.environ.get("RESULTS_S3_KEY", "discovery/inventory.json")


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
        "total_records": len(items),
        "store": "s3",
        "endpoints": ["/health", "/regions", "/accounts", "/databases", "/accounts/{accountId}/instances"],
    }
    return {"statusCode": 200, "body": json.dumps(body)}


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

    try:
        if "/health" in path or path_stripped.endswith("/health") or path_segments == ["health"]:
            items = load_all_records()
            return {"statusCode": 200, "body": json.dumps({"status": "ok", "total_records": len(items), "store": "s3"})}

        # Bare invoke URL is often /{stage} only (e.g. /prod) — API Gateway sends one path segment.
        if _should_serve_api_root(path_segments):
            return _api_root_response()

        is_list_accounts = (
            path_segments
            and path_segments[-1].lower() == "accounts"
            and not path_params.get("accountId")
            and "instances" not in path.lower()
        )
        if is_list_accounts:
            items = load_all_records()
            accounts = list(set(i.get("account_id", "unknown") for i in items if isinstance(i, dict) and i.get("account_id")))
            return {"statusCode": 200, "body": json.dumps({"accounts": to_json_serializable(accounts)})}

        if path_segments and path_segments[-1].lower() == "regions" and "accounts" not in path.lower():
            items = load_all_records()
            regions = sorted(set(i.get("region") for i in items if isinstance(i, dict) and i.get("region")))
            return {"statusCode": 200, "body": json.dumps({"regions": to_json_serializable(regions)})}

        if "regions" in path_segments and path_segments[-1].lower() == "accounts":
            try:
                idx = path_segments.index("regions")
                region = path_segments[idx + 1]
            except (ValueError, IndexError):
                return {"statusCode": 400, "body": json.dumps({"error": "Invalid region path"})}
            items = load_all_records()
            accounts = sorted(set(
                i.get("account_id")
                for i in items
                if isinstance(i, dict) and i.get("account_id") and i.get("region") == region
            ))
            return {"statusCode": 200, "body": json.dumps({"region": region, "accounts": to_json_serializable(accounts)})}

        qs = event.get("queryStringParameters") or {}
        if not isinstance(qs, dict):
            qs = {}
        region_filter = (qs.get("region") or "").strip()

        account_id = path_params.get("accountId")
        if account_id:
            items = query_by_account(account_id)
            if region_filter:
                items = [i for i in items if isinstance(i, dict) and i.get("region") == region_filter]
            if "/instances" in path or path.endswith(account_id):
                grouped = group_by_instance(items)
                return {"statusCode": 200, "body": json.dumps(to_json_serializable({"account_id": account_id, "instances": grouped}))}
            return {"statusCode": 200, "body": json.dumps(to_json_serializable({"account_id": account_id, "records": items}))}

        if path.endswith("/databases") or "/databases" in path:
            items = load_all_records()
            engine = qs.get("engine")
            acc = qs.get("account_id")
            if engine:
                items = [i for i in items if isinstance(i, dict) and i.get("engine") == engine]
            if acc:
                items = [i for i in items if isinstance(i, dict) and i.get("account_id") == acc]
            return {"statusCode": 200, "body": json.dumps(to_json_serializable({"databases": items}))}

        return {"statusCode": 404, "body": json.dumps({"error": "Not found"})}

    except ClientError as e:
        logger.error("AWS error: %s", e)
        return {"statusCode": 500, "body": json.dumps({"error": "Internal error"})}
    except Exception as e:
        logger.exception(str(e))
        return {"statusCode": 500, "body": json.dumps({"error": "Internal error"})}
