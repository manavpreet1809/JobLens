"""Read-only query checks against an isolated, in-memory database."""

import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, text

from src.analytics import load_analytics


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        self.addCleanup(self.engine.dispose)
        with self.engine.begin() as conn:
            schema = (Path(__file__).resolve().parents[1] / "db/schema.sql").read_text()
            for statement in schema.split(";"):
                if statement.strip():
                    conn.exec_driver_sql(statement)
        with self.engine.begin() as conn:
            conn.execute(text("""INSERT INTO jobs (job_id,title,company,date_posted,avg_salary)
                VALUES (:id,:title,:company,:date,:salary)"""), [
                dict(id="a", title="Python Developer", company="Acme", date="2026-01-01", salary=30),
                dict(id="b", title="Data Engineer", company="Acme", date="2026-01-02", salary=90000),
                dict(id="c", title="100%_Engineer", company=None, date=None, salary=None),
            ])
            conn.execute(text("INSERT INTO job_skills (job_id,skill) VALUES (:id,:skill)"), [
                dict(id="a", skill="python"), dict(id="a", skill="sql"),
                dict(id="b", skill="python"),
            ])

    def test_summary_does_not_multiply_jobs_by_skills(self):
        data = load_analytics(engine=self.engine)
        self.assertEqual(data["summary"].iloc[0].to_dict(),
                         dict(jobs=3, companies=1, salary_records=2, dated_records=2))
        self.assertEqual(data["skills"].jobs.tolist(), [2, 1])
        self.assertEqual(data["trend"].jobs.tolist(), [1, 1])
        self.assertEqual(data["companies"].jobs.tolist(), [2, 1])
        self.assertEqual(data["listings"].job_id.tolist(), ["b", "a", "c"])

    def test_filters_apply_to_all_queries(self):
        data = load_analytics(title="PYTHON", company="acm", start_date=date(2026,1,1),
                              end_date=date(2026,1,1), engine=self.engine)
        self.assertEqual(data["summary"].iloc[0].jobs, 1)
        self.assertEqual(data["listings"].job_id.tolist(), ["a"])
        self.assertEqual(data["skills"].jobs.tolist(), [1, 1])

    def test_text_filters_treat_wildcards_and_sql_as_literals(self):
        self.assertEqual(load_analytics(title="%_", engine=self.engine)["listings"].job_id.tolist(), ["c"])
        data = load_analytics(title="' OR 1=1 --", engine=self.engine)
        self.assertEqual(data["summary"].iloc[0].jobs, 0)
        self.assertTrue(data["skills"].empty)

    def test_invalid_date_range_does_not_connect(self):
        with patch("src.analytics.get_db_engine") as factory:
            with self.assertRaises(ValueError):
                load_analytics(start_date=date(2026,2,1), end_date=date(2026,1,1))
            factory.assert_not_called()

    def test_salary_groups_and_legacy_qualifications_are_separate(self):
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE jobs SET salary_currency='CAD', salary_period='HOUR' WHERE job_id='a'"))
            conn.execute(text("UPDATE jobs SET salary_currency='USD', salary_period='YEAR' WHERE job_id='b'"))
            conn.execute(text("INSERT INTO job_skills VALUES ('a','excellent communication','qualification')"))
        data = load_analytics(engine=self.engine)
        self.assertEqual(data["salaries"].jobs.tolist(), [1, 1])
        self.assertEqual(data["salaries"].mean_midpoint.tolist(), [30, 90000])
        self.assertNotIn("excellent communication", data["skills"].skill.tolist())

    def test_empty_database(self):
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM job_skills"))
            conn.execute(text("DELETE FROM jobs"))
        data = load_analytics(engine=self.engine)
        self.assertEqual(data["summary"].iloc[0].jobs, 0)
        for key in ("trend", "companies", "skills", "listings"):
            self.assertTrue(data[key].empty)


if __name__ == "__main__":
    unittest.main()
