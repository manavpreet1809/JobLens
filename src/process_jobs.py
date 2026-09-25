"""Pure transformations from raw JSearch records to schema-shaped DataFrames.

Jobs without usable salaries are retained. A lone bound supplies the midpoint
but is not copied into the missing bound. Salaries retain their original units
and currency: these values are not annualized or converted between currencies.
No files, S3 objects, or database connections are accessed here.
"""

import math
import json
import re

import pandas as pd


JOB_COLUMNS = [
    "job_id", "title", "company", "location", "salary_min", "salary_max",
    "avg_salary", "date_posted", "salary_currency", "salary_period", "qualifications",
]
SKILL_COLUMNS = ["job_id", "skill"]

# Small, auditable vocabulary. No inference beyond explicit qualification text.
SKILL_PATTERNS = {
    "python": r"\bpython\b", "sql": r"\bsql\b", "postgresql": r"\bpostgres(?:ql)?\b",
    "pandas": r"\bpandas\b", "numpy": r"\bnumpy\b", "docker": r"\bdocker\b",
    "kubernetes": r"\b(?:kubernetes|k8s)\b", "aws": r"\b(?:aws|amazon web services)\b",
    "azure": r"\bazure\b", "gcp": r"\b(?:gcp|google cloud)\b",
    "javascript": r"\bjavascript\b", "typescript": r"\btypescript\b",
    "java": r"\bjava\b", "c++": r"(?<!\w)c\+\+(?!\w)", "c#": r"(?<!\w)c#(?!\w)",
    "scikit-learn": r"\b(?:scikit-learn|sklearn)\b",
    "machine learning": r"\bmachine\s+learning\b", "spark": r"\b(?:apache\s+)?spark\b",
}


def extract_skills(qualifications):
    text = "\n".join(qualifications)
    return sorted(skill for skill, pattern in SKILL_PATTERNS.items()
                  if re.search(pattern, text, flags=re.IGNORECASE))


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

    Missing/blank IDs are excluded. Reversed salary bounds become null.
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
    reversed_bounds = low.notna() & high.notna() & (low > high)
    low, high = low.mask(reversed_bounds), high.mask(reversed_bounds)
    jobs["salary_min"], jobs["salary_max"] = low, high
    jobs["avg_salary"] = low.fillna(high) / 2 + high.fillna(low) / 2
    jobs["salary_currency"] = column("job_salary_currency").map(
        lambda value: value.strip().upper() if isinstance(value, str)
        and re.fullmatch(r"[A-Za-z]{3}", value.strip()) else None)
    jobs["salary_period"] = column("job_salary_period").map(
        lambda value: value.strip().upper() if isinstance(value, str)
        and value.strip().upper() in {"HOUR", "DAY", "WEEK", "MONTH", "YEAR"} else None)
    qualifications = column("job_highlights.Qualifications").map(_skills)
    jobs["qualifications"] = qualifications.map(lambda entries: json.dumps(entries, ensure_ascii=False))
    jobs["date_posted"] = column("job_posted_at_datetime_utc").map(
        lambda value: pd.to_datetime(value, errors="coerce", utc=True).date()
        if isinstance(value, str) else pd.NaT
    )
    jobs = jobs.loc[
        jobs["job_id"].notna()
    ].drop_duplicates("job_id", keep="first")

    skills = [
        {"job_id": row["job_id"], "skill": skill}
        for index, row in jobs.iterrows()
        for skill in extract_skills(qualifications.loc[index])
    ]
    return jobs[JOB_COLUMNS].reset_index(drop=True), pd.DataFrame(skills, columns=SKILL_COLUMNS)
