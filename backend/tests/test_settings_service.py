import unittest
from unittest.mock import Mock, patch

import test_support  # noqa: F401
from settings_service import DEFAULT_PRICING, get_effective_settings, sanitize_prompt_template


class SettingsServiceTest(unittest.TestCase):
    def test_sanitize_prompt_template_removes_name_placeholder(self):
        tpl = "Recipient name: {name}\nAddress: {address}"
        self.assertEqual(sanitize_prompt_template(tpl), "Address: {address}")

    @patch("settings_service.user_settings_table")
    def test_get_effective_settings_merges_defaults(self, mock_table):
        table = Mock()
        table.get_item.return_value = {
            "Item": {
                "prompt_template": "Split {address}",
                "pricing": {"location_usd_per_request": 0.99},
            }
        }
        mock_table.return_value = table

        out = get_effective_settings(table_name="user-settings", user_sub="user-1")
        self.assertEqual(out["prompt_template"], "Split {address}")
        self.assertEqual(out["pricing"]["location_usd_per_request"], 0.99)
        self.assertEqual(out["pricing"]["bedrock_input_usd_per_million"], DEFAULT_PRICING["bedrock_input_usd_per_million"])
        self.assertFalse(out["is_default"])
