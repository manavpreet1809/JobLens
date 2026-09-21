"""Mocked S3 reads plus an offline end-to-end persistence check."""

import io
import json
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from sqlalchemy import create_engine, text

from src.process_s3 import process_s3_object


KEY = "raw/2026-01-02/example-run/page_1.json"
RECORDS = [{
    "job_id": "example", "job_title": "Développeur", "job_min_salary": 30,
    "job_highlights": {"Qualifications": ["Python", "python"]},
}]


class S3ProcessingTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"S3_BUCKET_NAME": "synthetic-bucket"}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        client = patch("src.process_s3.get_s3_client")
        self.client_factory = client.start()
        self.addCleanup(client.stop)
        self.s3 = self.client_factory.return_value
        writer = patch("src.process_s3.save_jobs")
        self.save = writer.start()
        self.addCleanup(writer.stop)
        self.body = io.BytesIO(json.dumps(RECORDS, ensure_ascii=False).encode("utf-8"))
        self.s3.get_object.return_value = {"Body": self.body}

    def test_reads_transforms_and_saves_without_changing_raw_object(self):
        result = process_s3_object(KEY)
        self.s3.get_object.assert_called_once_with(Bucket="synthetic-bucket", Key=KEY)
        self.save.assert_called_once()
        jobs, skills = self.save.call_args.args
        self.assertEqual(jobs.title.tolist(), ["Développeur"])
        self.assertEqual(jobs.avg_salary.tolist(), [30])
        self.assertEqual(skills.skill.tolist(), ["python"])
        self.assertEqual(result, {"key": KEY, "raw_records": 1,
                                  "jobs_submitted": 1, "skills_submitted": 1})
        self.assertTrue(self.body.closed)
        self.s3.put_object.assert_not_called()
        self.s3.delete_object.assert_not_called()

    def test_invalid_keys_and_missing_bucket_fail_before_s3(self):
        for key in (None, "", "other/page.json", "raw/page.txt"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                process_s3_object(key)
        del os.environ["S3_BUCKET_NAME"]
        with self.assertRaisesRegex(ValueError, "S3_BUCKET_NAME"):
            process_s3_object(KEY)
        self.client_factory.assert_not_called()

    def test_invalid_json_and_payload_shapes_never_write(self):
        for contents in (b"invalid", b"\xff", b"{}", b"[null]", b"[NaN]"):
            with self.subTest(contents=contents):
                body = io.BytesIO(contents)
                self.s3.get_object.return_value = {"Body": body}
                with self.assertRaises(ValueError):
                    process_s3_object(KEY)
                self.assertTrue(body.closed)
        self.save.assert_not_called()

    def test_read_failure_closes_stream_and_never_writes(self):
        body = Mock()
        body.read.side_effect = OSError("synthetic read failure")
        self.s3.get_object.return_value = {"Body": body}
        with self.assertRaises(OSError):
            process_s3_object(KEY)
        body.close.assert_called_once()
        self.save.assert_not_called()

    def test_download_failure_never_writes(self):
        self.s3.get_object.side_effect = RuntimeError("synthetic download failure")
        with self.assertRaises(RuntimeError):
            process_s3_object(KEY)
        self.save.assert_not_called()

    def test_database_failure_propagates(self):
        self.save.side_effect = RuntimeError("synthetic database failure")
        with self.assertRaises(RuntimeError):
            process_s3_object(KEY)
        self.assertTrue(self.body.closed)

    def test_empty_page_reports_zero_rows(self):
        self.s3.get_object.return_value = {"Body": io.BytesIO(b"[]")}
        result = process_s3_object(KEY)
        self.assertEqual(result["jobs_submitted"], 0)
        self.assertEqual(result["skills_submitted"], 0)


class PipelineIntegrationTests(unittest.TestCase):
    def test_reprocessing_same_raw_page_does_not_duplicate_database_rows(self):
        engine = create_engine("sqlite:///:memory:")
        self.addCleanup(engine.dispose)
        schema = (Path(__file__).resolve().parents[1] / "db/schema.sql").read_text()
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys = ON")
            for statement in schema.split(";"):
                if statement.strip():
                    connection.exec_driver_sql(statement)
        with patch.dict(os.environ, {"S3_BUCKET_NAME": "synthetic-bucket"}, clear=True), \
                patch("src.process_s3.get_s3_client") as s3, \
                patch("src.persist_jobs.get_db_engine", return_value=engine):
            s3.return_value.get_object.side_effect = [
                {"Body": io.BytesIO(json.dumps(RECORDS).encode("utf-8"))}
                for _ in range(2)
            ]
            first = process_s3_object(KEY)
            second = process_s3_object(KEY)
        self.assertEqual(first, second)
        with engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT count(*) FROM jobs")).scalar_one(), 1)
            self.assertEqual(connection.execute(text("SELECT count(*) FROM job_skills")).scalar_one(), 1)


if __name__ == "__main__":
    unittest.main()
