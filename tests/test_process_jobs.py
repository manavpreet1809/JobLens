"""Synthetic transformation tests with no external services."""

import copy
import unittest
from datetime import date

import pandas as pd

from src.process_jobs import JOB_COLUMNS, SKILL_COLUMNS, transform_jobs


def record(job_id="example", **changes):
    row = {
        "job_id": job_id, "job_title": " Developer ", "employer_name": "Example",
        "job_location": "Edmonton", "job_min_salary": 80000,
        "job_max_salary": 100000, "job_posted_at_datetime_utc": "2026-01-02T01:00:00Z",
        "job_highlights": {"Qualifications": ["Python", " SQL ", "python"]},
    }
    row.update(changes)
    return row


class TransformationTests(unittest.TestCase):
    def test_schema_values_and_input_are_preserved(self):
        records = [record()]
        original = copy.deepcopy(records)
        jobs, skills = transform_jobs(records)
        self.assertEqual(list(jobs.columns), JOB_COLUMNS)
        self.assertEqual(list(skills.columns), SKILL_COLUMNS)
        self.assertEqual(jobs.iloc[0].to_dict(), {
            "job_id": "example", "title": "Developer", "company": "Example",
            "location": "Edmonton", "salary_min": 80000, "salary_max": 100000,
            "avg_salary": 90000, "date_posted": date(2026, 1, 2),
        })
        self.assertEqual(skills.to_dict("records"), [
            {"job_id": "example", "skill": "python"},
            {"job_id": "example", "skill": "sql"},
        ])
        self.assertEqual(records, original)

    def test_single_salary_bound_and_numeric_strings(self):
        jobs, _ = transform_jobs([
            record("low", job_min_salary="12.5", job_max_salary=None),
            record("high", job_min_salary=None, job_max_salary="20"),
            record("zero", job_min_salary=0, job_max_salary=None),
        ])
        self.assertEqual(jobs.salary_min.tolist(), [12.5, 20, 0])
        self.assertEqual(jobs.salary_max.tolist(), [12.5, 20, 0])
        self.assertEqual(jobs.avg_salary.tolist(), [12.5, 20, 0])

    def test_unusable_salaries_are_excluded(self):
        for value in (None, "unknown", float("nan"), float("inf"), -5, True, [], {}):
            with self.subTest(value=value):
                jobs, skills = transform_jobs([record(job_min_salary=value, job_max_salary=None)])
                self.assertTrue(jobs.empty)
                self.assertTrue(skills.empty)
        jobs, _ = transform_jobs([record(job_min_salary=100, job_max_salary=10)])
        self.assertTrue(jobs.empty)

    def test_missing_fields_and_empty_input(self):
        for records in ([], [{}], [{"job_id": "no-salary"}]):
            jobs, skills = transform_jobs(records)
            self.assertTrue(jobs.empty)
            self.assertTrue(skills.empty)
            self.assertEqual(list(jobs.columns), JOB_COLUMNS)
            self.assertEqual(list(skills.columns), SKILL_COLUMNS)
        jobs, skills = transform_jobs([{"job_id": "minimal", "job_min_salary": 25}])
        self.assertIsNone(jobs.iloc[0].title)
        self.assertTrue(pd.isna(jobs.iloc[0].date_posted))
        self.assertTrue(skills.empty)

    def test_ids_are_required_and_duplicates_keep_first_valid_record(self):
        jobs, skills = transform_jobs([
            record(None), record(" "), record(1),
            record("same", job_min_salary=None, job_max_salary=None),
            record(" same ", job_title="First valid"),
            record("same", job_title="Later", job_highlights={"Qualifications": ["Rust"]}),
        ])
        self.assertEqual(jobs.job_id.tolist(), ["same"])
        self.assertEqual(jobs.title.tolist(), ["First valid"])
        self.assertEqual(skills.skill.tolist(), ["python", "sql"])
        self.assertTrue(set(skills.job_id).issubset(set(jobs.job_id)))

    def test_dates_are_utc_and_invalid_dates_are_null(self):
        jobs, _ = transform_jobs([
            record("offset", job_posted_at_datetime_utc="2026-01-01T23:30:00-07:00"),
            record("invalid", job_posted_at_datetime_utc="not-a-date"),
            record("missing", job_posted_at_datetime_utc=None),
        ])
        self.assertEqual(jobs.iloc[0].date_posted, date(2026, 1, 2))
        self.assertTrue(pd.isna(jobs.iloc[1].date_posted))
        self.assertTrue(pd.isna(jobs.iloc[2].date_posted))

    def test_skills_handle_missing_strings_and_hyphens(self):
        records = [
            record("string", job_highlights={"Qualifications": " Scikit-learn "}),
            record("list", job_highlights={"Qualifications": [None, 7, "", "  ", "Machine  Learning", "machine learning"]}),
            record("missing", job_highlights={}),
        ]
        _, skills = transform_jobs(records)
        self.assertEqual(skills.to_dict("records"), [
            {"job_id": "string", "skill": "scikit-learn"},
            {"job_id": "list", "skill": "machine learning"},
        ])

    def test_invalid_input_is_rejected(self):
        for value in (None, {}, "jobs", [None], ["job"]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                transform_jobs(value)


if __name__ == "__main__":
    unittest.main()
