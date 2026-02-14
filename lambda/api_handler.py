import json
import logging
import os
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "db-discovery-results")
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)


def to_json_serializable(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, dict):
        return {k: to_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_json_serializable(v) for v in obj]
    return obj


def scan_all():
    # Create resource and table inside function to avoid module-level issues in Lambda
    _dynamo = boto3.resource("dynamodb", region_name=AWS_REGION)
    table = _dynamo.Table(TABLE_NAME)
    items = []
    try:
        response = table.scan()
        items = response.get("Items", [])
        while "LastEvaluatedKey" in response:
            response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            items.extend(response.get("Items", []))
    except Exception as e:
        logger.exception("scan_all failed: %s", e)
        raise
    return items


def query_by_account(account_id):
    table = dynamodb.Table(TABLE_NAME)
    resp = table.query(KeyConditionExpression="account_id = :aid", ExpressionAttributeValues={":aid": account_id})
    return resp.get("Items", [])


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


def lambda_handler(event, context):
    if not isinstance(event, dict):
        event = {}
    path = str(event.get("path") or "")
    path_params = event.get("pathParameters")
    if not isinstance(path_params, dict):
        path_params = {}

    try:
        if path.endswith("/health") or "/health" in path:
            items = scan_all()
            return {"statusCode": 200, "body": json.dumps({"status": "ok", "total_records": len(items)})}

        if path.endswith("/accounts") and not path_params.get("accountId"):
            items = scan_all()
            accounts = list(set(i.get("account_id", "unknown") for i in items if isinstance(i, dict) and i.get("account_id")))
            return {"statusCode": 200, "body": json.dumps({"accounts": to_json_serializable(accounts)})}

        account_id = path_params.get("accountId")
        if account_id:
            items = query_by_account(account_id)
            if "/instances" in path or path.endswith(account_id):
                grouped = group_by_instance(items)
                return {"statusCode": 200, "body": json.dumps(to_json_serializable({"account_id": account_id, "instances": grouped}))}
            return {"statusCode": 200, "body": json.dumps(to_json_serializable({"account_id": account_id, "records": items}))}

        if path.endswith("/databases") or "/databases" in path:
            items = scan_all()
            qs = event.get("queryStringParameters") or {}
            if not isinstance(qs, dict):
                qs = {}
            engine = qs.get("engine")
            acc = qs.get("account_id")
            if engine:
                items = [i for i in items if isinstance(i, dict) and i.get("engine") == engine]
            if acc:
                items = [i for i in items if isinstance(i, dict) and i.get("account_id") == acc]
            return {"statusCode": 200, "body": json.dumps(to_json_serializable({"databases": items}))}

        return {"statusCode": 404, "body": json.dumps({"error": "Not found"})}

    except ClientError as e:
        logger.error(f"DynamoDB error: {e}")
        return {"statusCode": 500, "body": json.dumps({"error": "Internal error"})}
    except Exception as e:
        logger.exception(str(e))
        return {"statusCode": 500, "body": json.dumps({"error": "Internal error"})}
