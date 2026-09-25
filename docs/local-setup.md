# Local setup

Use Docker Desktop with Compose v2, or Python 3.12 and an existing PostgreSQL 16
database. Direct Python dependencies are pinned in `requirements.txt`; transitive
packages and container security patches may change on a fresh build.

## Docker

In the repository root, set a local database password in your shell or an ignored
`.env` file. For example, generate one with `openssl rand -hex 24` and store it
locally as `DB_PASSWORD`. Keep it unchanged while reusing the database volume.
Do not paste credentials into Git-tracked files or command output shared publicly.

```sh
docker compose up --build -d
docker compose ps
```

Open http://localhost:8501. A fresh database correctly shows an empty dashboard.
PostgreSQL is available only on localhost:5433 (database/user: talentscope).
Override `DB_LOCAL_PORT` or `DASHBOARD_PORT` locally if either port is occupied.
The dashboard container runs as an unprivileged user and includes no AWS or API
credentials. This setup does not create cloud infrastructure or fetch paid data.

```sh
docker compose run --rm dashboard python -B -m unittest discover -s tests
docker compose down
```

`down` preserves the named database volume. Initial schema loading runs only on
an empty volume. Never use `down -v` on data you want to keep.

For an existing older schema, apply the migration without resetting the volume:

```sh
docker compose exec -T db psql -U talentscope -d talentscope -v ON_ERROR_STOP=1 < db/migrations/001_data_quality.sql
```

See [data quality](data-quality.md) for reprocessing older raw pages.

## Native Python

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
.venv/bin/python -m unittest discover -s tests
.venv/bin/streamlit run streamlit_app.py
```

Export `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, and optionally `DB_PORT`
first. Native application code reads process environment variables; it does not
automatically load `.env`. Compose reads `.env` for its own substitution only.
