-- TalentScope's initial PostgreSQL schema.
-- Salary values and posting dates are populated by the processing stage.
BEGIN;

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    title TEXT,
    company TEXT,
    location TEXT,
    salary_min NUMERIC,
    salary_max NUMERIC,
    avg_salary NUMERIC,
    date_posted DATE,
    salary_currency TEXT,
    salary_period TEXT,
    qualifications TEXT
);

CREATE TABLE IF NOT EXISTS job_skills (
    job_id TEXT REFERENCES jobs (job_id),
    skill TEXT,
    skill_kind TEXT NOT NULL DEFAULT 'skill',
    PRIMARY KEY (job_id, skill)
);

COMMIT;
