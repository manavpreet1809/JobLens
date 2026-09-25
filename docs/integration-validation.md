# Integration validation

The default suite makes no real API, AWS, or PostgreSQL calls. Its SQLite tests
remain useful but do not substitute for PostgreSQL behavior.

## Isolated PostgreSQL 16 tests

Use a disposable database and set `RUN_POSTGRES_TESTS=1` explicitly. The suite
creates unique `talentscope_test_<uuid>` schemas and removes only those schemas.
It requires permission to create schemas. It never drops public tables.

```sh
docker compose up --build -d --wait
docker compose run --rm -e RUN_POSTGRES_TESTS=1 dashboard python -B -m unittest discover -s tests
```

Checks include transactional rollback, concurrent duplicate ingestion, SQL nulls,
currency/period grouping, repeatable legacy migration, and a full pipeline from
mocked HTTP/S3 through real PostgreSQL to the Streamlit test runner.

## Live external-service smoke run

This is a separate check, not part of automated tests. Configure `RAPIDAPI_KEY`,
`S3_BUCKET_NAME`, normal AWS credential/region settings, and `DB_*` locally. Use a
dedicated test bucket and database with the current schema. Do not paste secrets
into tracked files. Bucket and database/schema creation are not automated here.

```sh
python -m scripts.live_smoke --query "data engineer in Edmonton" --confirm-live
```

The command checks bucket access and schema before requesting one page. It stores
that page under a unique raw prefix and processes it into the configured database.
It can incur API/AWS charges. If processing fails after storage, the raw object
remains available; there is no automatic cloud deletion or retry. Inspect the
dashboard separately after a successful run. Empty API results do not demonstrate
successful record persistence.

## Recorded outcome

Local Docker build, dependency consistency, and service health have been checked.
All 71 tests passed in the Python 3.12 image with PostgreSQL 16 integration enabled,
including five real-PostgreSQL tests. No production database was accessed.
The live JSearch/S3 run is **pending**: no API key and authorized bucket were
configured for this task. Do not describe external-service integration as verified
until that run succeeds. Test credentials and fixtures are synthetic.
