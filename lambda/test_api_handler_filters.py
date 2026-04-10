import json
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import api_handler


def _event(path, query=None, account_id=None):
    return {
        "httpMethod": "GET",
        "path": path,
        "pathParameters": {"accountId": account_id} if account_id else {},
        "queryStringParameters": query or {},
    }


def _resp_body(resp):
    return json.loads(resp["body"])


SAMPLE = [
    {
        "account_id": "111111111111",
        "instance_id": "i-a",
        "region": "ap-south-1",
        "instance_type": "t3.medium",
        "tags": {"Name": "a"},
        "db_id": "pg-5432",
        "engine": "postgres",
        "version": "15",
        "status": "running",
        "port": 5432,
        "data_size_mb": 10,
        "discovery_status": "success",
        "ec2_state": "running",
    },
    {
        "account_id": "222222222222",
        "instance_id": "i-b",
        "region": "eu-west-1",
        "instance_type": "t3.small",
        "tags": {"Name": "b"},
        "db_id": "mysql-3306",
        "engine": "mysql",
        "version": "8.0",
        "status": "running",
        "port": 3306,
        "data_size_mb": 20,
        "discovery_status": "success",
        "ec2_state": "stopped",
    },
]


class ApiFilterTests(unittest.TestCase):
    @patch("api_handler.enrich_instances_ec2_state")
    @patch("api_handler.load_all_records", return_value=SAMPLE)
    def test_databases_multi_filters(self, _load, _enrich):
        event = _event(
            "/prod/databases",
            {
                "region": "ap-south-1",
                "engine": "postgresql",
                "ec2_state": "running",
            },
        )
        resp = api_handler.lambda_handler(event, None)
        body = _resp_body(resp)
        self.assertEqual(resp["statusCode"], 200)
        self.assertEqual(len(body["databases"]), 1)
        self.assertEqual(body["databases"][0]["account_id"], "111111111111")

    @patch("api_handler.enrich_instances_ec2_state")
    @patch("api_handler.load_all_records", return_value=SAMPLE)
    def test_instances_filter_by_engine(self, _load, _enrich):
        event = _event(
            "/prod/accounts/111111111111/instances",
            {"region": "ap-south-1", "engine": "postgresql"},
            account_id="111111111111",
        )
        resp = api_handler.lambda_handler(event, None)
        body = _resp_body(resp)
        self.assertEqual(resp["statusCode"], 200)
        self.assertEqual(body["account_id"], "111111111111")
        self.assertEqual(len(body["instances"]), 1)
        self.assertEqual(len(body["instances"][0]["databases"]), 1)
        self.assertEqual(body["instances"][0]["databases"][0]["engine"], "postgres")

    @patch("api_handler.enrich_instances_ec2_state")
    @patch("api_handler.load_all_records", return_value=SAMPLE)
    def test_regions_filter_by_engine(self, _load, _enrich):
        event = _event("/prod/regions", {"engine": "mysql"})
        resp = api_handler.lambda_handler(event, None)
        body = _resp_body(resp)
        self.assertEqual(resp["statusCode"], 200)
        self.assertEqual(body["regions"], ["eu-west-1"])

    @patch("api_handler.enrich_instances_ec2_state")
    @patch("api_handler.load_all_records", return_value=SAMPLE)
    def test_accounts_filter_by_engine_and_region(self, _load, _enrich):
        event = _event("/prod/accounts", {"region": "eu-west-1", "engine": "mysql"})
        resp = api_handler.lambda_handler(event, None)
        body = _resp_body(resp)
        self.assertEqual(resp["statusCode"], 200)
        self.assertEqual(body["accounts"], ["222222222222"])


if __name__ == "__main__":
    unittest.main()
