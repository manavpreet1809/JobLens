"""Opt-in PostgreSQL tests in unique schemas that are removed after each test.

Run only against a disposable test database with RUN_POSTGRES_TESTS=1.
The normal test suite skips these tests and makes no PostgreSQL connections.
"""

import io
import os
import re
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from streamlit.testing.v1 import AppTest

from src.analytics import load_analytics
from src.config import get_database_url
from src.ingest_jobs import ingest_jobs
from src.persist_jobs import save_jobs
from src.process_jobs import transform_jobs
from src.process_s3 import process_s3_object


ROOT = Path(__file__).resolve().parents[1]
RAW = [
    {"job_id": "paid", "job_title": "Python Developer", "employer_name": "Example",
     "job_min_salary": 40, "job_max_salary": 60, "job_salary_currency": "CAD",
     "job_salary_period": "HOUR", "job_posted_at_datetime_utc": "2026-01-01T12:00:00Z",
     "job_highlights": {"Qualifications": ["Python and SQL experience"]}},
    {"job_id": "unpaid-info", "job_title": "Engineer", "employer_name": "Example",
     "job_highlights": {"Qualifications": ["Docker experience"]}},
]


class MemoryS3:
    """A test-only storage double; no AWS credentials or requests."""
    def __init__(self):
        self.objects = {}

    def put_object(self, *, Bucket, Key, Body, ContentType):
        self.objects[Bucket, Key] = Body

    def get_object(self, *, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[Bucket, Key])}


@unittest.skipUnless(os.environ.get("RUN_POSTGRES_TESTS") == "1", "Opt-in PostgreSQL tests")
class PostgresIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.schema = "talentscope_test_" + uuid4().hex
        self.admin = create_engine(get_database_url(), hide_parameters=True)
        self.addCleanup(self.admin.dispose)
        with self.admin.begin() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{self.schema}"')
        self.addCleanup(self.drop_schema)
        self.engine = create_engine(get_database_url(), hide_parameters=True,
            connect_args={"options": f"-csearch_path={self.schema}"})
        self.addCleanup(self.engine.dispose)

    def drop_schema(self):
        # The identifier is generated above, never supplied by users.
        with self.admin.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{self.schema}" CASCADE')

    def apply(self, sql):
        with self.engine.begin() as connection:
            for statement in re.sub(r"(?m)^\s*--.*$", "", sql).split(";"):
                if statement.strip().upper() not in ("", "BEGIN", "COMMIT"):
                    connection.exec_driver_sql(statement)

    def fresh(self):
        self.apply((ROOT / "db/schema.sql").read_text())

    def scalar(self, sql):
        with self.engine.connect() as connection:
            return connection.execute(text(sql)).scalar_one()

    def test_postgres_roundtrip_nulls_and_replay(self):
        self.fresh()
        jobs, skills = transform_jobs(RAW)
        save_jobs(jobs, skills, engine=self.engine)
        save_jobs(jobs, skills, engine=self.engine)
        self.assertEqual(self.scalar("SELECT count(*) FROM jobs"), 2)
        self.assertEqual(self.scalar("SELECT count(*) FROM job_skills"), 3)
        self.assertIsNone(self.scalar("SELECT avg_salary FROM jobs WHERE job_id='unpaid-info'"))
        data = load_analytics(engine=self.engine)
        self.assertEqual(data["summary"].iloc[0].jobs, 2)
        self.assertEqual(data["salaries"].iloc[0].mean_midpoint, 50)

    def test_postgres_rolls_back_entire_batch(self):
        self.fresh()
        self.apply("ALTER TABLE job_skills ADD CONSTRAINT reject_sql CHECK (skill <> 'sql')")
        jobs, skills = transform_jobs(RAW)
        with self.assertRaises(IntegrityError):
            save_jobs(jobs, skills, engine=self.engine)
        self.assertEqual(self.scalar("SELECT count(*) FROM jobs"), 0)
        self.assertEqual(self.scalar("SELECT count(*) FROM job_skills"), 0)

    def test_concurrent_replays_do_not_duplicate_rows(self):
        self.fresh()
        jobs, skills = transform_jobs(RAW[:1])
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(save_jobs, jobs, skills, engine=self.engine) for _ in range(2)]
            for future in futures:
                future.result(timeout=20)
        self.assertEqual(self.scalar("SELECT count(*) FROM jobs"), 1)
        self.assertEqual(self.scalar("SELECT count(*) FROM job_skills"), 2)

    def test_legacy_migration_is_repeatable_and_preserves_data(self):
        self.apply("""CREATE TABLE jobs (job_id TEXT PRIMARY KEY, title TEXT, company TEXT,
            location TEXT, salary_min NUMERIC, salary_max NUMERIC, avg_salary NUMERIC, date_posted DATE);
            CREATE TABLE job_skills (job_id TEXT REFERENCES jobs(job_id), skill TEXT,
                PRIMARY KEY(job_id,skill));
            INSERT INTO jobs(job_id,title) VALUES ('paid','Original');
            INSERT INTO job_skills VALUES ('paid','communication');""")
        migration = (ROOT / "db/migrations/001_data_quality.sql").read_text()
        self.apply(migration)
        self.apply(migration)
        self.assertEqual(self.scalar("SELECT skill_kind FROM job_skills"), "qualification")
        self.assertTrue(load_analytics(engine=self.engine)["skills"].empty)
        save_jobs(*transform_jobs(RAW[:1]), engine=self.engine)
        self.assertEqual(self.scalar("SELECT title FROM jobs"), "Original")
        self.assertEqual(self.scalar("SELECT salary_currency FROM jobs"), "CAD")
        self.assertEqual(self.scalar("SELECT count(*) FROM job_skills WHERE skill_kind='skill'"), 2)

    def test_ingestion_to_dashboard_with_real_postgres_and_fake_external_services(self):
        self.fresh()
        storage = MemoryS3()
        page = Mock(status_code=200)
        page.json.return_value = {"status": "OK", "data": RAW}
        empty = Mock(status_code=200)
        empty.json.return_value = {"status": "OK", "data": []}
        with patch.dict(os.environ, {"RAPIDAPI_KEY": "synthetic-test-key", "S3_BUCKET_NAME": "test-bucket"}), \
             patch("src.fetch_jobs.requests.get", side_effect=[page, empty]) as request, \
             patch("src.ingest_jobs.get_s3_client", return_value=storage), \
             patch("src.process_s3.get_s3_client", return_value=storage), \
             patch("src.persist_jobs.get_db_engine", return_value=self.engine):
            keys = ingest_jobs("developer", max_pages=2)
            self.assertEqual(len(keys), 1)
            self.assertEqual(request.call_count, 2)
            result = process_s3_object(keys[0])
            self.assertEqual(result["jobs_submitted"], 2)
            process_s3_object(keys[0])
        with patch("src.analytics.get_db_engine", return_value=self.engine):
            app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=20).run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertEqual(app.metric[0].value, "2")


if __name__ == "__main__":
    unittest.main()
