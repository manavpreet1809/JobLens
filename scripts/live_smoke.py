"""Explicitly authorized one-page JSearch -> S3 -> PostgreSQL smoke run.

Run from the repository root: python -m scripts.live_smoke --query "..." --confirm-live
Requires configured environment, AWS permissions, and the current DB schema.
"""

import argparse
import json

from sqlalchemy import text

from src.config import get_db_engine, get_jsearch_headers, get_s3_bucket_name, get_s3_client
from src.ingest_jobs import ingest_jobs
from src.process_s3 import process_s3_object


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True)
    parser.add_argument("--confirm-live", action="store_true",
                        help="Authorize one paid API request, S3 storage and database writes")
    args = parser.parse_args()
    if not args.confirm_live:
        parser.error("--confirm-live is required; this run can incur charges and writes data")
    try:
        get_jsearch_headers()
        bucket = get_s3_bucket_name()
        get_s3_client().head_bucket(Bucket=bucket)
        with get_db_engine().connect() as connection:
            connection.execute(text("SELECT salary_currency, salary_period, qualifications FROM jobs LIMIT 0"))
            connection.execute(text("SELECT skill_kind FROM job_skills LIMIT 0"))
        keys = ingest_jobs(args.query, max_pages=1)
        # Print only generated object keys and row counts, never headers or records.
        print(json.dumps({"objects": keys, "results": [process_s3_object(key) for key in keys]}))
    except Exception as error:
        # SDK/DB exceptions may carry connection strings or request information.
        raise SystemExit(f"Live validation failed ({type(error).__name__}); check configuration and permissions locally.") from None


if __name__ == "__main__":
    main()
