import json
import logging
import os
import time
from datetime import datetime

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SPOKE_ACCOUNTS = os.environ.get("SPOKE_ACCOUNTS", "").split(",")
SPOKE_ROLE_NAME = os.environ.get("SPOKE_ROLE_NAME", "DBDiscoverySpokeRole")
SSM_DOCUMENT = os.environ.get("SSM_DOCUMENT", "DBDiscovery")
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "db-discovery-results")
S3_BUCKET = os.environ.get("S3_BUCKET", "")
COMMAND_TIMEOUT = int(os.environ.get("COMMAND_TIMEOUT", "60"))


def get_spoke_client(account_id, service, region=None):
    region = region or os.environ.get("AWS_REGION", "eu-west-1")
    sts = boto3.client("sts")
    role_arn = f"arn:aws:iam::{account_id}:role/{SPOKE_ROLE_NAME}"
    assumed = sts.assume_role(RoleArn=role_arn, RoleSessionName="DBDiscoverySession")
    creds = assumed["Credentials"]
    return boto3.client(
        service,
        region_name=region,
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
    )


def get_managed_instances(ssm_client):
    instances = []
    paginator = ssm_client.get_paginator("describe_instance_information")
    for page in paginator.paginate():
        for info in page.get("InstanceInformationList", []):
            if info.get("PingStatus") == "Online":
                platform = info.get("PlatformName", "Unknown")
                if platform and "linux" in platform.lower():
                    instances.append((info["InstanceId"], platform))
    return instances


def get_instance_details(ec2_client, instance_ids):
    """Fetch instance type (t-shirt size) and tags from EC2 for given instance IDs."""
    details = {}
    if not instance_ids:
        return details
    try:
        resp = ec2_client.describe_instances(InstanceIds=instance_ids)
        for reservation in resp.get("Reservations", []):
            for inst in reservation.get("Instances", []):
                iid = inst.get("InstanceId")
                if not iid:
                    continue
                tags = {}
                for t in inst.get("Tags", []):
                    key = t.get("Key")
                    val = t.get("Value")
                    if key is not None:
                        tags[key] = val or ""
                details[iid] = {
                    "instance_type": inst.get("InstanceType") or "unknown",
                    "tags": tags,
                }
    except Exception as e:
        logger.warning(f"DescribeInstances failed: {e}")
    return details


def run_ssm_command(ssm_client, instance_ids, account_id):
    if not instance_ids:
        return {"status": "skipped", "reason": "no_managed_instances", "instances": []}

    params = {"DocumentName": SSM_DOCUMENT, "InstanceIds": instance_ids}
    if S3_BUCKET:
        params["Parameters"] = {"S3Bucket": [S3_BUCKET], "S3Key": ["ssm/discovery_python.py"]}

    try:
        resp = ssm_client.send_command(**params)
        command_id = resp["Command"]["CommandId"]
    except Exception as e:
        logger.error(f"SendCommand failed for account {account_id}: {e}")
        return {"status": "error", "reason": str(e), "instances": []}

    end_time = time.time() + COMMAND_TIMEOUT
    cmd = {"Status": "Unknown"}
    while time.time() < end_time:
        time.sleep(5)
        try:
            status_resp = ssm_client.list_commands(CommandId=command_id)
            if status_resp.get("Commands"):
                cmd = status_resp["Commands"][0]
                if cmd["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
                    break
        except Exception as e:
            logger.warning(f"ListCommands failed: {e}")
            continue

    results = []
    for iid in instance_ids:
        try:
            inv = ssm_client.get_command_invocation(CommandId=command_id, InstanceId=iid)
            status = inv.get("Status", "Unknown")
            output = inv.get("StandardOutputContent", "")
            error = inv.get("StandardErrorContent", "")
            results.append({"instance_id": iid, "status": status, "output": output, "error": error})
        except Exception as e:
            results.append({"instance_id": iid, "status": "error", "output": "", "error": str(e)})

    return {"status": cmd.get("Status", "Unknown"), "command_id": command_id, "instances": results}


def parse_discovery_output(output_str, instance_id, account_id, instance_details=None):
    instance_details = instance_details or {}
    inst_info = instance_details.get(instance_id, {})
    instance_type = inst_info.get("instance_type", "unknown")
    tags = inst_info.get("tags", {})

    records = []
    if not output_str or not output_str.strip():
        return records

    # SSM runCommand concatenates stdout: aws s3 cp progress + script JSON. Take from first "{" (top-level object).
    raw = output_str.strip()
    json_start = raw.find("{")
    if json_start >= 0:
        raw = raw[json_start:]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("JSON parse error for %s: %s", instance_id, e)
        return records

    discovery_status = data.get("discovery_status", "unknown")
    if discovery_status == "error":
        logger.info(f"Discovery error for {instance_id}: {data.get('error', 'unknown')}")
        return records

    databases = data.get("databases", [])
    if not isinstance(databases, list):
        databases = []
    sys_mem = data.get("system_memory_mb", 0)
    sys_cpu = data.get("system_cpu_cores", 0)

    for db in databases:
        db_id = db.get("db_id", "unknown")
        engine = db.get("engine", "unknown")
        version = db.get("version", "unknown")
        status = db.get("status", "unknown")
        port = db.get("port", 0)
        data_size = db.get("data_size_mb", 0)
        record = {
            "account_id": account_id,
            "instance_id": instance_id,
            "db_id": db_id,
            "engine": engine,
            "version": version,
            "status": status,
            "port": port,
            "data_size_mb": data_size,
            "system_memory_mb": db.get("system_memory_mb", sys_mem),
            "system_cpu_cores": db.get("system_cpu_cores", sys_cpu),
            "instance_type": instance_type,
            "tags": tags,
            "discovery_timestamp": datetime.utcnow().isoformat() + "Z",
            "discovery_status": "success",
        }
        records.append(record)

    if not records and discovery_status == "success":
        records.append({
            "account_id": account_id,
            "instance_id": instance_id,
            "db_id": "none",
            "engine": "none",
            "version": "n/a",
            "status": "none",
            "port": 0,
            "data_size_mb": 0,
            "system_memory_mb": sys_mem,
            "system_cpu_cores": sys_cpu,
            "instance_type": instance_type,
            "tags": tags,
            "discovery_timestamp": datetime.utcnow().isoformat() + "Z",
            "discovery_status": "success",
        })

    return records


def store_results(dynamodb, records):
    table = dynamodb.Table(DYNAMODB_TABLE)
    for r in records:
        try:
            item = {
                "account_id": r["account_id"],
                "instance_db_id": f"{r['instance_id']}#{r['db_id']}",
                **r,
            }
            table.put_item(Item=item)
        except Exception as e:
            logger.error(f"Failed to store record for {r.get('instance_id', '?')}: {e}")
            raise


def lambda_handler(event, context):
    logger.info(f"Starting discovery for accounts: {SPOKE_ACCOUNTS}")

    dynamodb = boto3.resource("dynamodb")
    all_records = []

    for account_id in SPOKE_ACCOUNTS:
        account_id = account_id.strip()
        if not account_id:
            continue

        try:
            ssm = get_spoke_client(account_id, "ssm")
        except Exception as e:
            logger.error(f"Assume role failed for {account_id}: {e}")
            continue

        instances = get_managed_instances(ssm)
        if not instances:
            logger.info(f"No managed instances in account {account_id}")
            continue

        instance_ids = [i[0] for i in instances]
        ec2 = get_spoke_client(account_id, "ec2")
        instance_details = get_instance_details(ec2, instance_ids)

        result = run_ssm_command(ssm, instance_ids, account_id)

        for ir in result.get("instances", []):
            iid = ir["instance_id"]
            status = ir["status"]
            output = ir.get("output", "")
            inst_info = instance_details.get(iid, {})
            inst_type = inst_info.get("instance_type", "unknown")
            tags = inst_info.get("tags", {})

            if status == "Success":
                records = parse_discovery_output(output, iid, account_id, instance_details)
                if not records and (output or ir.get("error")):
                    logger.warning("Instance %s: Success but no records", iid)
                all_records.extend(records)
            else:
                all_records.append({
                    "account_id": account_id,
                    "instance_id": iid,
                    "db_id": "discovery_failed",
                    "engine": "n/a",
                    "version": "n/a",
                    "status": "failed",
                    "port": 0,
                    "data_size_mb": 0,
                    "system_memory_mb": 0,
                    "system_cpu_cores": 0,
                    "instance_type": inst_type,
                    "tags": tags,
                    "discovery_timestamp": datetime.utcnow().isoformat() + "Z",
                    "discovery_status": "failed",
                    "error": ir.get("error", status),
                })

    if all_records:
        try:
            store_results(dynamodb, all_records)
        except Exception as e:
            logger.error(f"Store results failed: {e}")
            return {"statusCode": 500, "body": json.dumps({"error": "Storage failed", "detail": str(e)})}

    return {"statusCode": 200, "body": json.dumps({"discovered": len(all_records), "accounts": SPOKE_ACCOUNTS})}
