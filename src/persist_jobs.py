"""Transactional persistence for the DataFrames returned by transform_jobs."""

import pandas as pd
from sqlalchemy import text

from src.config import get_db_engine
from src.process_jobs import JOB_COLUMNS, SKILL_COLUMNS


INSERT_JOBS = text("""
    INSERT INTO jobs
        (job_id, title, company, location, salary_min, salary_max, avg_salary, date_posted,
         salary_currency, salary_period, qualifications)
    VALUES
        (:job_id, :title, :company, :location, :salary_min, :salary_max, :avg_salary, :date_posted,
         :salary_currency, :salary_period, :qualifications)
    ON CONFLICT (job_id) DO UPDATE SET
        salary_min = excluded.salary_min, salary_max = excluded.salary_max,
        avg_salary = excluded.avg_salary, salary_currency = excluded.salary_currency,
        salary_period = excluded.salary_period, qualifications = excluded.qualifications
""")
INSERT_SKILLS = text("""
    INSERT INTO job_skills (job_id, skill, skill_kind) VALUES (:job_id, :skill, 'skill')
    ON CONFLICT (job_id, skill) DO UPDATE SET skill_kind = 'skill'
""")


def _records(frame, columns):
    if not isinstance(frame, pd.DataFrame) or not set(columns).issubset(frame.columns):
        raise ValueError("Expected a DataFrame with columns: " + ", ".join(columns))
    selected = frame[columns].astype(object)
    return selected.where(pd.notna(selected), None).to_dict("records")


def save_jobs(jobs: pd.DataFrame, skills: pd.DataFrame, *, engine=None) -> None:
    """Save jobs then skills in one transaction against the existing schema.

    Repeated batches are safe: salary metadata and qualifications are refreshed,
    other existing job fields are preserved, and extracted skills are replaced
    for the batch. Legacy qualification rows remain separately labeled. All
    skills must refer to a job in this batch. Database errors propagate after
    rollback. This function never creates tables or commits partial batches.
    """
    job_rows = _records(jobs, JOB_COLUMNS)
    skill_rows = _records(skills, SKILL_COLUMNS)
    for row in job_rows + skill_rows:
        if not isinstance(row["job_id"], str) or not row["job_id"].strip():
            raise ValueError("job_id must be a nonempty string")
    ids = {row["job_id"] for row in job_rows}
    for row in skill_rows:
        if row["job_id"] not in ids:
            raise ValueError("Each skill must refer to a job in the batch")
        if not isinstance(row["skill"], str) or not row["skill"].strip():
            raise ValueError("skill must be a nonempty string")
    if not job_rows:
        return

    target = engine if engine is not None else get_db_engine()
    with target.begin() as connection:
        connection.execute(INSERT_JOBS, job_rows)
        connection.execute(text("DELETE FROM job_skills WHERE job_id = :job_id AND skill_kind = 'skill'"),
                           [{"job_id": job_id} for job_id in ids])
        if skill_rows:
            connection.execute(INSERT_SKILLS, skill_rows)
