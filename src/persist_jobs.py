"""Transactional persistence for the DataFrames returned by transform_jobs."""

import pandas as pd
from sqlalchemy import text

from src.config import get_db_engine
from src.process_jobs import JOB_COLUMNS, SKILL_COLUMNS


INSERT_JOBS = text("""
    INSERT INTO jobs
        (job_id, title, company, location, salary_min, salary_max, avg_salary, date_posted)
    VALUES
        (:job_id, :title, :company, :location, :salary_min, :salary_max, :avg_salary, :date_posted)
    ON CONFLICT (job_id) DO NOTHING
""")
INSERT_SKILLS = text("""
    INSERT INTO job_skills (job_id, skill) VALUES (:job_id, :skill)
    ON CONFLICT (job_id, skill) DO NOTHING
""")


def _records(frame, columns):
    if not isinstance(frame, pd.DataFrame) or not set(columns).issubset(frame.columns):
        raise ValueError("Expected a DataFrame with columns: " + ", ".join(columns))
    selected = frame[columns].astype(object)
    return selected.where(pd.notna(selected), None).to_dict("records")


def save_jobs(jobs: pd.DataFrame, skills: pd.DataFrame, *, engine=None) -> None:
    """Save jobs then skills in one transaction against the existing schema.

    Repeated batches are safe: existing jobs remain unchanged and duplicate
    skill pairs are ignored. New skills may be added to existing jobs. All
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
        if skill_rows:
            connection.execute(INSERT_SKILLS, skill_rows)
