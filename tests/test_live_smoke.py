"""The live runner must require opt-in and avoid leaking exception details."""

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from scripts.live_smoke import main


class LiveRunnerTests(unittest.TestCase):
    def test_requires_confirmation_before_any_service_access(self):
        with patch("sys.argv", ["live_smoke", "--query", "developer"]), \
             patch("scripts.live_smoke.get_jsearch_headers") as headers, \
             redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                main()
            self.assertEqual(caught.exception.code, 2)
            headers.assert_not_called()

    def test_exception_details_are_not_exposed(self):
        with patch("sys.argv", ["live_smoke", "--query", "developer", "--confirm-live"]), \
             patch("scripts.live_smoke.get_jsearch_headers", side_effect=ValueError("synthetic-private-value")):
            with self.assertRaises(SystemExit) as caught:
                main()
            self.assertNotIn("synthetic-private-value", str(caught.exception))

    def test_authorized_run_is_limited_to_one_page(self):
        with patch("sys.argv", ["live_smoke", "--query", "developer", "--confirm-live"]), \
             patch("scripts.live_smoke.get_jsearch_headers"), \
             patch("scripts.live_smoke.get_s3_bucket_name", return_value="synthetic-bucket"), \
             patch("scripts.live_smoke.get_s3_client"), \
             patch("scripts.live_smoke.get_db_engine"), \
             patch("scripts.live_smoke.ingest_jobs", return_value=[]) as ingest, \
             redirect_stdout(io.StringIO()):
            main()
            ingest.assert_called_once_with("developer", max_pages=1)


if __name__ == "__main__":
    unittest.main()
