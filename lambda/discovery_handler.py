import json
import logging
import os
import time
from datetime import datetime

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SPOKE_ACCOUNTS = os.environ.get("SPOKE_ACCOUNTS", "").split(",")
DISCOVERY_REGIONS = [r.strip() for r in os.environ.get("DISCOVERY_REGIONS", "").split(",") if r.strip()]
SPOKE_ROLE_NAME = os.environ.get("SPOKE_ROLE_NAME", "DBDiscoverySpokeRole")
SSM_DOCUMENT = os.environ.get("SSM_DOCUMENT", "DBDiscovery")
S3_BUCKET = os.environ.get("S3_BUCKET", "")
# Inventory snapshot written here (FinOps: one object per run vs many DynamoDB items).
RESULTS_S3_BUCKET = os.environ.get("RESULTS_S3_BUCKET", "") or S3_BUCKET
RESULTS_S3_KEY = os.environ.get("RESULTS_S3_KEY", "discovery/inventory.json")
COMMAND_TIMEOUT = int(os.environ.get("COMMAND_TIMEOUT", "60"))
# Set DISCOVER_ALL_ORG_ACCOUNTS=true when Lambda runs in the Org management account (or delegated admin)
# to scan every ACTIVE member; optional ORG_EXCLUDE_ACCOUNT_IDS=comma list; ORG_SKIP_MANAGEMENT_ACCOUNT=true
DISCOVER_ALL_ORG_ACCOUNTS = os.environ.get("DISCOVER_ALL_ORG_ACCOUNTS", "").lower() in ("1", "true", "yes")
ORG_SKIP_MANAGEMENT_ACCOUNT = os.environ.get("ORG_SKIP_MANAGEMENT_ACCOUNT", "").lower() in ("1", "true", "yes")


def list_active_org_account_ids():
    org = boto3.client("organizations")
    ids = []
    paginator = org.get_paginator("list_accounts")
    for page in paginator.paginate():
        for a in page.get("Accounts", []):
            if a.get("Status") == "ACTIVE" and a.get("Id"):
                ids.append(a["Id"])
    if ORG_SKIP_MANAGEMENT_ACCOUNT:
        try:
            master = org.describe_organization()["Organization"]["MasterAccountId"]
            ids = [i for i in ids if i != master]
            logger.info("Excluded management account %s from scan list", master)
        except Exception as e:
            logger.warning("Could not exclude management account: %s", e)
    return ids


def resolve_accounts_to_scan():
    manual = [a.strip() for a in SPOKE_ACCOUNTS if a.strip()]
    exclude = {x.strip() for x in os.environ.get("ORG_EXCLUDE_ACCOUNT_IDS", "").split(",") if x.strip()}

    if DISCOVER_ALL_ORG_ACCOUNTS:
        try:
            org_ids = [a for a in list_active_org_account_ids() if a not in exclude]
        except Exception as e:
            logger.error("Organization list_accounts failed (is this the management account?): %s", e)
            org_ids = []
        merged = list(dict.fromkeys(org_ids + manual))
        logger.info("Account list (org auto): %s accounts", len(merged))
        return merged

    out = [a for a in manual if a not in exclude]
    return out


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


def parse_discovery_output(output_str, instance_id, account_id, region, instance_details=None):
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
            "region": region,
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
            "region": region,
            "instance_type": instance_type,
            "tags": tags,
            "discovery_timestamp": datetime.utcnow().isoformat() + "Z",
            "discovery_status": "success",
        })

    return records


def store_results_s3(records):
    if not RESULTS_S3_BUCKET:
        raise ValueError("RESULTS_S3_BUCKET or S3_BUCKET must be set to store inventory")

    payload = {
        "schema_version": 1,
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "record_count": len(records),
        "records": records,
    }
    body = json.dumps(payload, default=str)
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "eu-west-1"))
    s3.put_object(
        Bucket=RESULTS_S3_BUCKET,
        Key=RESULTS_S3_KEY,
        Body=body.encode("utf-8"),
        ContentType="application/json",
    )
    logger.info("Wrote %s records to s3://%s/%s", len(records), RESULTS_S3_BUCKET, RESULTS_S3_KEY)


def lambda_handler(event, context):
    accounts_to_scan = resolve_accounts_to_scan()
    logger.info("Starting discovery for accounts: %s", accounts_to_scan)
    if not accounts_to_scan:
        logger.warning(
            "No accounts to scan (set SPOKE_ACCOUNTS and/or DISCOVER_ALL_ORG_ACCOUNTS=true in org management account)"
        )
        try:
            store_results_s3([])
        except Exception as e:
            return {"statusCode": 500, "body": json.dumps({"error": "Storage failed", "detail": str(e)})}
        return {
            "statusCode": 200,
            "body": json.dumps({"discovered": 0, "accounts": [], "note": "no_accounts_configured"}),
        }

    all_records = []

    regions = DISCOVERY_REGIONS or [os.environ.get("AWS_REGION", "eu-west-1")]

    for account_id in accounts_to_scan:
        account_id = account_id.strip()
        if not account_id:
            continue

        for region in regions:
            try:
                ssm = get_spoke_client(account_id, "ssm", region=region)
                ec2 = get_spoke_client(account_id, "ec2", region=region)
            except Exception as e:
                logger.error(f"Assume role failed for {account_id} in {region}: {e}")
                continue

            instances = get_managed_instances(ssm)
            if not instances:
                logger.info(f"No managed instances in account {account_id} region {region}")
                continue

            instance_ids = [i[0] for i in instances]
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
                    records = parse_discovery_output(output, iid, account_id, region, instance_details)
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
                        "region": region,
                        "error": ir.get("error", status),
                    })

    try:
        store_results_s3(all_records)
    except Exception as e:
        logger.error(f"Store results failed: {e}")
        return {"statusCode": 500, "body": json.dumps({"error": "Storage failed", "detail": str(e)})}

    return {"statusCode": 200, "body": json.dumps({"discovered": len(all_records), "accounts": accounts_to_scan})}
