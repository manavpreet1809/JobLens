# TalentScope

TalentScope turns job postings into a searchable view of hiring activity, salary ranges, and demand for technical skills. It brings API ingestion, data processing, and a PostgreSQL-backed dashboard into one pipeline.

## Data pipeline

JSearch → S3 raw JSON → pandas → PostgreSQL → Streamlit.

Filters narrow results by role, employer, and date. Salary comparisons keep currencies and pay periods separate. Skill counts come from a defined technology vocabulary. Raw pages can be reprocessed without duplicating jobs.

## Run

Requires Docker. Set a local database password, then start the services:

```sh
export DB_PASSWORD="$(openssl rand -hex 24)"
docker compose up --build -d --wait
```

Open [localhost:8501](http://localhost:8501). Keep the same password when reusing the database. A new database starts empty.

See [local setup](docs/local-setup.md) for loading data and configuration. [Integration checks](docs/integration-validation.md) describe testing; live API/AWS validation is still pending.
