# TalentScope

A dashboard for exploring job postings, employers, salaries, and skills.

**Built with:** Python, pandas, PostgreSQL, AWS S3, Streamlit, and Docker.

![Dashboard with fictional demo data](docs/images/dashboard.png)

## Run locally

With Docker installed, set a local database password and start the app:

```sh
export DB_PASSWORD="$(openssl rand -hex 24)"
docker compose up --build -d --wait
```

Open [localhost:8501](http://localhost:8501). Keep the same password when reusing
the database. A fresh database starts with an empty dashboard.

The local pipeline has been tested; live API/AWS validation is pending.
See [setup](docs/local-setup.md) and [testing](docs/integration-validation.md) for details.
