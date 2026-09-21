"""Streamlit interaction checks with synthetic query results."""

import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from sqlalchemy.exc import SQLAlchemyError
from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / "streamlit_app.py"


def sample():
    return {
        "summary": pd.DataFrame([dict(jobs=2, companies=1, salary_records=2, dated_records=2)]),
        "trend": pd.DataFrame([dict(date_posted="2026-01-01", jobs=2)]),
        "companies": pd.DataFrame([dict(company="Example", jobs=2)]),
        "skills": pd.DataFrame([dict(skill="python", jobs=2)]),
        "listings": pd.DataFrame([dict(job_id="example", title="Developer", company="Example",
            location="Edmonton", date_posted="2026-01-01", salary_min=30, salary_max=40, avg_salary=35)]),
    }


class DashboardTests(unittest.TestCase):
    def test_populated_view_and_form_filters(self):
        with patch("src.analytics.load_analytics", return_value=sample()) as load:
            app = AppTest.from_file(APP, default_timeout=20).run()
            self.assertFalse(app.exception)
            self.assertEqual([m.value for m in app.metric], ["2", "1", "2", "2"])
            self.assertEqual(len(app.tabs), 3)
            app.text_input[0].set_value("Data")
            app.button[0].click().run()
            self.assertEqual(load.call_args.kwargs["title"], "Data")
            self.assertFalse(app.exception)

    def test_empty_view(self):
        data = sample()
        data["summary"].loc[0, "jobs"] = 0
        with patch("src.analytics.load_analytics", return_value=data):
            app = AppTest.from_file(APP).run()
        self.assertFalse(app.exception)
        self.assertIn("No postings", app.info[0].value)

    def test_errors_do_not_reveal_connection_details(self):
        with patch("src.analytics.load_analytics", side_effect=SQLAlchemyError("synthetic-private-value")):
            app = AppTest.from_file(APP).run()
        self.assertFalse(app.exception)
        self.assertNotIn("synthetic-private-value", app.error[0].value)
        self.assertIn("unavailable", app.error[0].value)

    def test_reversed_dates_do_not_query(self):
        with patch("src.analytics.load_analytics", return_value=sample()) as load:
            app = AppTest.from_file(APP).run()
            load.reset_mock()
            app.date_input[0].set_value(date(2026,2,1))
            app.date_input[1].set_value(date(2026,1,1))
            app.button[0].click().run()
            load.assert_not_called()
            self.assertTrue(app.warning)


if __name__ == "__main__":
    unittest.main()
