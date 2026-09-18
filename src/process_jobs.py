"""Pure transformations from raw JSearch records to schema-shaped DataFrames.

Like the reference pipeline, records without either usable salary bound are
excluded. A lone bound fills both bounds. Salaries retain their original units
and currency: these values are not annualized or converted between currencies.
No files, S3 objects, or database connections are accessed here.
"""

import math

import pandas as pd


JOB_COLUMNS = [
    "job_id", "title", "company", "location", "salary_min", "salary_max",
    "avg_salary", "date_posted",
]
SKILL_COLUMNS = ["job_id", "skill"]


def _text(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def _salary(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _skills(value):
    """Normalize qualification entries, retaining hyphens within skill names.

    A string is one entry; a list supplies multiple entries. Qualification
    phrases are preserved rather than inferred to be individual technologies.
    """
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return sorted({" ".join(item.split()).lower() for item in value
                   if isinstance(item, str) and item.strip()})


def transform_jobs(records: list) -> tuple:
    """Return (jobs, job_skills) without modifying the input records.

    Missing/blank IDs and unusable or reversed salary ranges are excluded.
    Duplicate IDs keep the first valid record in input order. Missing text
    and invalid dates become null. Dates are interpreted in UTC. Skills are
    unique per retained job and omitted when qualifications are absent.
    """
    if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
        raise ValueError("records must be a list of job dictionaries")
    if not records:
        return pd.DataFrame(columns=JOB_COLUMNS), pd.DataFrame(columns=SKILL_COLUMNS)

    raw = pd.json_normalize(records)

    def column(name):
        return raw[name] if name in raw else pd.Series(None, index=raw.index, dtype=object)

    jobs = pd.DataFrame(index=raw.index)
    for target, source in (
        ("job_id", "job_id"), ("title", "job_title"),
        ("company", "employer_name"), ("location", "job_location"),
    ):
        jobs[target] = column(source).map(_text)
    low = column("job_min_salary").map(_salary).astype(float)
    high = column("job_max_salary").map(_salary).astype(float)
    jobs["salary_min"] = low.fillna(high)
    jobs["salary_max"] = high.fillna(low)
    jobs["avg_salary"] = jobs["salary_min"] / 2 + jobs["salary_max"] / 2
    jobs["date_posted"] = column("job_posted_at_datetime_utc").map(
        lambda value: pd.to_datetime(value, errors="coerce", utc=True).date()
        if isinstance(value, str) else pd.NaT
    )
    jobs = jobs.loc[
        jobs["job_id"].notna() & jobs["salary_min"].notna()
        & (jobs["salary_min"] <= jobs["salary_max"])
    ].drop_duplicates("job_id", keep="first")

    qualifications = column("job_highlights.Qualifications")
    skills = [
        {"job_id": row["job_id"], "skill": skill}
        for index, row in jobs.iterrows()
        for skill in _skills(qualifications.loc[index])
    ]
    return jobs[JOB_COLUMNS].reset_index(drop=True), pd.DataFrame(skills, columns=SKILL_COLUMNS)
