"""Process one explicitly selected raw S3 page into the existing database."""

import json

from src.config import get_s3_bucket_name, get_s3_client
from src.persist_jobs import save_jobs
from src.process_jobs import transform_jobs


def _reject_nonfinite(value):
    raise ValueError("Raw JSON must not contain non-finite numbers")


def process_s3_object(key: str) -> dict:
    """Read, transform, and save a raw JSON page from S3_BUCKET_NAME.

    The original S3 object is left untouched. Read, validation, and database
    errors propagate to the caller; success is returned only after saving.
    Reprocessing is safe under save_jobs' insert-only conflict policy.
    Counts describe transformed rows submitted, not newly inserted rows.
    No object listing, scheduling, bucket creation, or API fetching occurs.
    """
    if not isinstance(key, str) or not key.startswith("raw/") or not key.endswith(".json"):
        raise ValueError("key must identify a .json object under raw/")
    bucket = get_s3_bucket_name()
    response = get_s3_client().get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    try:
        contents = body.read()
    finally:
        body.close()
    try:
        records = json.loads(contents.decode("utf-8"), parse_constant=_reject_nonfinite)
    except (UnicodeDecodeError, ValueError):
        raise ValueError("S3 object must contain valid UTF-8 JSON") from None

    jobs, skills = transform_jobs(records)
    save_jobs(jobs, skills)
    return {
        "key": key,
        "raw_records": len(records),
        "jobs_submitted": len(jobs),
        "skills_submitted": len(skills),
    }
