"""Offline persistence checks using SQLite's compatible ON CONFLICT syntax.

These exercise real transactions and constraints, not a live PostgreSQL server.
"""

import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from src.persist_jobs import save_jobs
from src.process_jobs import transform_jobs


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        self.addCleanup(self.engine.dispose)
        schema = (Path(__file__).resolve().parents[1] / "db/schema.sql").read_text()
        with self.engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys = ON")
            for statement in schema.split(";"):
                if statement.strip():
                    connection.exec_driver_sql(statement)
        self.jobs, self.skills = transform_jobs([{
            "job_id": "example", "job_title": "Developer", "job_min_salary": 20,
            "job_highlights": {"Qualifications": ["Python", "SQL"]},
        }])

    def rows(self, query):
        with self.engine.connect() as connection:
            return connection.execute(text(query)).all()

    def test_saves_jobs_skills_and_sql_nulls(self):
        save_jobs(self.jobs, self.skills, engine=self.engine)
        self.assertEqual(self.rows("SELECT job_id, title, date_posted, company FROM jobs"),
                         [("example", "Developer", None, None)])
        self.assertEqual(self.rows("SELECT skill FROM job_skills ORDER BY skill"),
                         [("python",), ("sql",)])

    def test_replay_is_idempotent_and_existing_jobs_are_preserved(self):
        save_jobs(self.jobs, self.skills, engine=self.engine)
        self.jobs.loc[0, "title"] = "Changed"
        save_jobs(self.jobs, self.skills, engine=self.engine)
        self.assertEqual(self.rows("SELECT title FROM jobs"), [("Developer",)])
        self.assertEqual(self.rows("SELECT count(*) FROM job_skills"), [(2,)])

    def test_values_are_bound_not_interpolated(self):
        title = "'); DROP TABLE jobs; --"
        self.jobs.loc[0, "title"] = title
        save_jobs(self.jobs, self.skills, engine=self.engine)
        self.assertEqual(self.rows("SELECT title FROM jobs"), [(title,)])

    def test_skill_failure_rolls_back_job_insert(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql("""
                CREATE TRIGGER reject_skill BEFORE INSERT ON job_skills
                BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END
            """)
        with self.assertRaises(IntegrityError):
            save_jobs(self.jobs, self.skills, engine=self.engine)
        self.assertEqual(self.rows("SELECT count(*) FROM jobs"), [(0,)])

    def test_empty_batch_does_not_create_engine(self):
        jobs, skills = transform_jobs([])
        with patch("src.persist_jobs.get_db_engine") as factory:
            save_jobs(jobs, skills)
            factory.assert_not_called()

    def test_invalid_batch_fails_before_engine_creation(self):
        with patch("src.persist_jobs.get_db_engine") as factory:
            with self.assertRaises(ValueError):
                save_jobs(self.jobs.drop(columns="title"), self.skills)
            self.skills.loc[0, "job_id"] = "unknown"
            with self.assertRaises(ValueError):
                save_jobs(self.jobs, self.skills)
            factory.assert_not_called()

    def test_job_without_skills_is_saved(self):
        save_jobs(self.jobs, self.skills.iloc[:0], engine=self.engine)
        self.assertEqual(self.rows("SELECT count(*) FROM jobs"), [(1,)])
        self.assertEqual(self.rows("SELECT count(*) FROM job_skills"), [(0,)])

    def test_reprocessing_refreshes_metadata_and_extracted_skills(self):
        save_jobs(self.jobs, self.skills, engine=self.engine)
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO job_skills VALUES ('example','communication','qualification')"))
        jobs, skills = transform_jobs([{
            "job_id": "example", "job_min_salary": 50, "job_salary_currency": "CAD",
            "job_salary_period": "HOUR", "job_highlights": {"Qualifications": ["Docker"]},
        }])
        save_jobs(jobs, skills, engine=self.engine)
        self.assertEqual(self.rows("SELECT salary_currency, salary_period, avg_salary FROM jobs"),
                         [("CAD", "HOUR", 50)])
        self.assertEqual(self.rows("SELECT skill FROM job_skills WHERE skill_kind='skill'"), [("docker",)])
        self.assertEqual(self.rows("SELECT skill FROM job_skills WHERE skill_kind='qualification'"), [("communication",)])


if __name__ == "__main__":
    unittest.main()
