import unittest
from unittest.mock import patch

import test_support  # noqa: F401
from batch_processor import process_batch_csv_text


class BatchProcessorTest(unittest.TestCase):
    @patch("batch_processor.resolve_address")
    def test_process_batch_csv_appends_resolved_columns(self, mock_resolve):
        mock_resolve.return_value = {
            "bedrock_geonames": {
                "address_line1": "Rue du Rhone 10",
                "address_line2": "",
                "postcode": "1204",
                "city": "Geneve",
                "state_region": "",
                "country_code": "CH",
                "latitude": "46.2",
                "longitude": "6.1",
                "confidence": 0.91,
                "warnings": [],
            }
        }
        csv_text, summary = process_batch_csv_text(
            csv_text="record_id,raw_address,country_code\n1,\"Rue du Rhone 10, Geneve\",CH\n",
            model_id="model",
            pipelines=["bedrock_geonames"],
            prompt_template="Split {address}",
            pricing={},
            runtime_cfg={},
        )
        self.assertIn("resolved_pipeline", csv_text)
        self.assertIn("Rue du Rhone 10", csv_text)
        self.assertEqual(summary["rows_processed"], 1)
        self.assertEqual(summary["rows_failed"], 0)

    def test_process_batch_csv_requires_raw_address_column(self):
        with self.assertRaisesRegex(ValueError, "batch_input_missing_columns:raw_address"):
            process_batch_csv_text(
                csv_text="record_id,address\n1,test\n",
                model_id="",
                pipelines=[],
                prompt_template="Split {address}",
                pricing={},
                runtime_cfg={},
            )
