# TalentScope

A job market analytics platform for exploring hiring trends and understanding demand for roles and skills.

Planned technologies: Python, JSearch through RapidAPI, pandas, AWS S3, AWS Secrets Manager, AWS Lambda, PostgreSQL, SQLAlchemy, Streamlit, Altair, and Docker.

Development is in progress.

Run the read-only dashboard from the repository root with `streamlit run streamlit_app.py`
after installing `requirements.txt` and configuring `DB_HOST`, `DB_NAME`, `DB_USER`,
and `DB_PASSWORD` in your environment (`DB_PORT` defaults to `5432`). The database
must already contain the tables in `db/schema.sql`; the dashboard does not ingest data.
