import io
import unittest
from unittest.mock import patch

import test_support  # noqa: F401
from batch_handler import _process_one_object


class BatchHandlerTest(unittest.TestCase):
    @patch("batch_handler.update_batch_job")
    @patch("batch_handler.create_batch_job")
    @patch("batch_handler.process_batch_csv_text")
    @patch("batch_handler.s3")
    def test_process_one_object_creates_and_updates_job_record(self, mock_s3, mock_process, mock_create, mock_update):
        mock_s3.get_object.return_value = {
            "Body": io.BytesIO(b"raw_address\nx\n"),
            "Metadata": {"job-id": "job-1", "user-sub": "user-1"},
        }
        mock_process.return_value = ("raw_address,resolved_pipeline\nx,bedrock_geonames\n", {"rows_processed": 1, "rows_failed": 0})

        with patch("batch_handler.os.getenv") as getenv:
            getenv.side_effect = lambda key, default=None: {
                "BATCH_JOBS_TABLE": "batch-jobs",
                "RESULTS_RETENTION_DAYS": "30",
                "BATCH_DEFAULT_MODEL_ID": "",
                "BATCH_PIPELINES": "bedrock_geonames",
                "BATCH_DEFAULT_COUNTRY_CODE": "",
                "BATCH_OUTPUT_PREFIX": "batch-output",
            }.get(key, default)
            manifest = _process_one_object(bucket="bucket", key="input/addresses.csv")

        self.assertEqual(manifest["job_id"], "job-1")
        mock_create.assert_called_once()
        mock_update.assert_called_once()
        self.assertEqual(mock_s3.put_object.call_count, 2)
