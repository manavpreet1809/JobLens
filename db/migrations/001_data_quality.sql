-- Upgrade an existing pre-Stage-11 PostgreSQL schema without deleting data.
BEGIN;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS salary_currency TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS salary_period TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS qualifications TEXT;
-- Old skill rows were qualification phrases, not extracted skills.
ALTER TABLE job_skills ADD COLUMN IF NOT EXISTS skill_kind TEXT NOT NULL DEFAULT 'qualification';
ALTER TABLE job_skills ALTER COLUMN skill_kind SET DEFAULT 'skill';
COMMIT;
