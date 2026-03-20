import json
import unittest
from unittest.mock import patch

import test_support  # noqa: F401
import index


class IndexHandlerTest(unittest.TestCase):
    def test_health_route_returns_ok(self):
        resp = index.handler({"requestContext": {"http": {"method": "GET"}, "routeKey": "GET /health"}}, None)
        self.assertEqual(resp["statusCode"], 200)
        self.assertTrue(json.loads(resp["body"])["ok"])

    def test_missing_jwt_returns_unauthorized(self):
        resp = index.handler({"requestContext": {"http": {"method": "GET"}, "routeKey": "GET /recent"}}, None)
        self.assertEqual(resp["statusCode"], 401)

    @patch("index.handle_get_models")
    def test_models_route_delegates(self, mock_handle):
        mock_handle.return_value = {"statusCode": 200, "headers": {}, "body": "{}"}
        event = {
            "requestContext": {
                "http": {"method": "GET"},
                "routeKey": "GET /models",
                "authorizer": {"jwt": {"claims": {"sub": "user-1"}}},
            }
        }
        resp = index.handler(event, None)
        self.assertEqual(resp["statusCode"], 200)
        mock_handle.assert_called_once()
