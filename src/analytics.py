"""Read-only analytics over stored postings; no cross-currency salary averages."""

from datetime import date

import pandas as pd
from sqlalchemy import text

from src.config import get_db_engine


def load_analytics(*, title="", company="", start_date=None, end_date=None, engine=None):
    """Return metrics, daily counts, company/qualification rankings and 200 jobs.

    Text filters are literal, case-insensitive substrings. Date filters exclude
    undated postings. Rankings are capped at 10 and 15 rows respectively. Salary
    summaries report coverage only: original currencies and pay periods are
    unavailable, so aggregating their amounts would be misleading.
    """
    clauses, params = [], {}
    for name, value in (("title", title), ("company", company)):
        if not isinstance(value, str):
            raise ValueError(f"{name} must be text")
        if value.strip():
            literal = value.strip().lower().replace("!", "!!").replace("%", "!%").replace("_", "!_")
            clauses.append(f"LOWER(j.{name}) LIKE :{name} ESCAPE '!'")
            params[name] = "%" + literal + "%"
    for name, value, operator in (("start_date", start_date, ">="), ("end_date", end_date, "<=")):
        if value is not None:
            if type(value) is not date:
                raise ValueError(f"{name} must be a date")
            clauses.append(f"j.date_posted {operator} :{name}")
            params[name] = value
    if start_date and end_date and start_date > end_date:
        raise ValueError("Start date must not follow end date")
    where = " AND ".join(clauses) or "1=1"
    queries = {
        "summary": f"""SELECT COUNT(*) AS jobs,
            COUNT(DISTINCT NULLIF(TRIM(j.company), '')) AS companies,
            COUNT(j.avg_salary) AS salary_records,
            COUNT(j.date_posted) AS dated_records
            FROM jobs j WHERE {where}""",
        "trend": f"""SELECT j.date_posted, COUNT(*) AS jobs FROM jobs j
            WHERE {where} AND j.date_posted IS NOT NULL
            GROUP BY j.date_posted ORDER BY j.date_posted""",
        "companies": f"""SELECT COALESCE(NULLIF(TRIM(j.company), ''), 'Unknown') AS company,
            COUNT(*) AS jobs FROM jobs j WHERE {where}
            GROUP BY COALESCE(NULLIF(TRIM(j.company), ''), 'Unknown')
            ORDER BY jobs DESC, company LIMIT 10""",
        "skills": f"""SELECT js.skill, COUNT(DISTINCT j.job_id) AS jobs
            FROM jobs j JOIN job_skills js ON js.job_id = j.job_id
            WHERE {where} GROUP BY js.skill ORDER BY jobs DESC, js.skill LIMIT 15""",
        "listings": f"""SELECT j.job_id, j.title, j.company, j.location,
            j.date_posted, j.salary_min, j.salary_max, j.avg_salary
            FROM jobs j WHERE {where}
            ORDER BY j.date_posted DESC NULLS LAST, j.job_id LIMIT 200""",
    }
    target = engine if engine is not None else get_db_engine()
    with target.connect() as connection:
        return {name: pd.read_sql_query(text(sql), connection, params=params)
                for name, sql in queries.items()}
