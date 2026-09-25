# Data quality

Postings with a nonempty ID are retained even when salary data is missing or
invalid. Invalid, negative, non-finite, or reversed salary values become null.
Missing bounds remain missing; a single usable bound supplies the midpoint.
Duplicate IDs within one input page keep the first record.

Currency codes are retained as uppercase three-letter source values. Supported
periods are HOUR, DAY, WEEK, MONTH, and YEAR. Unknown periods become null.
Analytics groups reported salary midpoints by currency and period; it performs
no exchange-rate conversion or annualization. Source values are not independently
verified. Counts describe the collected dataset, not the entire job market.

Normalized qualification phrases are kept as JSON text on the job. A small,
explicit regex vocabulary extracts technology/skill mentions from those phrases.
It does not infer proficiency, interpret negation, or recognize every skill.
See `SKILL_PATTERNS` in `src/process_jobs.py` for the auditable vocabulary.

## Existing databases

Before using Stage 11 code with a pre-Stage-11 PostgreSQL database, apply
`db/migrations/001_data_quality.sql` with `psql -v ON_ERROR_STOP=1`.
The migration is repeatable and does not delete old rows. It labels old
`job_skills` rows as `qualification`; those rows no longer enter skill rankings.
Fresh installations use `db/schema.sql` directly.

Reprocess the original raw S3 pages to populate new metadata, recover previously
discarded salary-less postings, and extract skills. Existing job identity fields
stay unchanged, while salary/qualification fields and extracted skills refresh
transactionally. Without the original raw records, unknown units remain unknown.
Do not guess missing currencies or relabel all legacy phrases as skills.
