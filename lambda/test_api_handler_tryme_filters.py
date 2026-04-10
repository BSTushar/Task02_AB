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
        "account_id": "111111111111",
        "instance_id": "i-a",
        "region": "ap-south-1",
        "instance_type": "t3.medium",
        "tags": {"Name": "a"},
        "db_id": "none",
        "engine": "none",
        "version": "",
        "status": "",
        "port": 0,
        "data_size_mb": 0,
        "discovery_status": "success",
        "ec2_state": "running",
    },
]


class ApiTryMeFilterTests(unittest.TestCase):
    @patch("api_handler.load_all_records", return_value=SAMPLE)
    def test_databases_include_empty_false(self, _load):
        event = _event(
            "/prod/databases",
            {
                "region": "ap-south-1",
                "account_id": "111111111111",
                "include_empty": "false",
            },
        )
        resp = api_handler.lambda_handler(event, None)
        body = _resp_body(resp)
        self.assertEqual(resp["statusCode"], 200)
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["databases"][0]["db_id"], "pg-5432")

    @patch("api_handler.load_all_records", return_value=SAMPLE)
    def test_root_index_includes_version(self, _load):
        event = _event("/prod")
        resp = api_handler.lambda_handler(event, None)
        body = _resp_body(resp)
        self.assertEqual(resp["statusCode"], 200)
        self.assertEqual(body["api_version"], "2.3")


if __name__ == "__main__":
    unittest.main()
