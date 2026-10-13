"""TalentScope's read-only analytics dashboard. Run from the repository root."""

import json

import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from src.analytics import load_analytics

ACCENT = "#8A5A12"
PERIODS = {"HOUR": "Per hour", "DAY": "Per day", "WEEK": "Per week", "MONTH": "Per month", "YEAR": "Per year"}
MONEY = st.column_config.NumberColumn(format="localized")


def readable_qualifications(value):
    """Stored qualifications are a JSON list; show them as plain text."""
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        entries = json.loads(value)
    except ValueError:
        return value
    return "; ".join(str(entry) for entry in entries) if isinstance(entries, list) else str(entries)


def readable_period(value):
    return PERIODS.get(value, value) if isinstance(value, str) else value


def main():
    st.set_page_config(page_title="TalentScope", layout="wide")
    # Keep the reading area comfortable on laptop screens; retain native scrolling.
    st.html("""
        <style>
        [data-testid="stMainBlockContainer"] {
            max-width: 1240px;
            padding: 3.5rem 1.5rem 2rem;
        }
        [data-testid="stMain"] h1 {
            font-size: clamp(1.6rem, 2vw, 2rem);
            line-height: 1.2;
            letter-spacing: -0.025em;
            padding-top: 0.25rem;
        }
        [data-testid="stMain"] h3 { font-size: 1.2rem; }
        [data-testid="stSidebarUserContent"] { padding-top: 3rem; }
        [data-testid="stMetric"] {
            background: #FFFFFF;
            border: 1px solid #D6D1C6;
            border-radius: 4px;
            padding: 0.5rem 0.75rem;
        }
        [data-testid="stMetricValue"] { font-size: 1.6rem; }
        [data-testid="stMetricLabel"] { font-size: 0.85rem; }
        [data-testid="stTabs"] { margin-top: 0.75rem; }
        @media (max-width: 1100px) {
            [data-testid="stMainBlockContainer"] { padding-inline: 1.5rem; }
            [data-testid="stMetric"] { padding: 0.75rem; }
            [data-testid="stMetricValue"] { font-size: 1.7rem; }
        }
        @media (max-width: 640px) {
            [data-testid="stMainBlockContainer"] { padding: 4rem 1rem 2rem; }
        }
        </style>
    """)
    st.title("TalentScope")
    st.write("Explore job postings, employers, salaries, and skills.")

    with st.sidebar:
        st.header("Filters")
        with st.form("filters"):
            title = st.text_input("Job title", placeholder="e.g. Data engineer")
            company = st.text_input("Company", placeholder="Any employer")
            start = st.date_input("Posted from", value=None)
            end = st.date_input("Posted through", value=None)
            st.form_submit_button("Apply filters", type="primary", width="stretch")
        st.caption("Leave the dates empty to include postings without a date.")

    if start and end and start > end:
        st.warning("Choose an end date on or after the start date.")
        return
    try:
        with st.spinner("Loading postings…"):
            data = load_analytics(title=title, company=company, start_date=start, end_date=end)
    except (ValueError, SQLAlchemyError):
        st.error("The data is unavailable. Check the database settings and connection, then try again.")
        return

    summary = data["summary"].iloc[0]
    total = int(summary["jobs"])
    columns = st.columns(4)
    for column, label, value in zip(columns,
            ("Stored postings", "Companies", "With salary values", "With posting dates"),
            (total, int(summary["companies"]), int(summary["salary_records"]), int(summary["dated_records"]))):
        with column:
            st.metric(label, f"{value:,}")
    st.caption("Only the postings this project has collected, not every job on the market.")
    if total == 0:
        st.info("No postings match these filters. Try widening them, or load some job data first.")
        return

    overview, qualifications, listings = st.tabs(["Overview", "Skills", "Job listings"])
    with overview:
        left, right = st.columns([3, 2])
        with left:
            st.subheader("Posting activity")
            st.caption("Postings per day (postings without a date are left out)")
            if data["trend"].empty:
                st.info("No posting dates are available for this view.")
            else:
                chart = alt.Chart(data["trend"]).mark_line(point=True, color=ACCENT).encode(
                    x=alt.X("date_posted:T", title="Posted date"),
                    y=alt.Y("jobs:Q", title="Postings", axis=alt.Axis(tickMinStep=1)),
                    tooltip=[alt.Tooltip("date_posted:T", title="Date"), alt.Tooltip("jobs:Q", title="Postings")],
                ).properties(height=220)
                st.altair_chart(chart, use_container_width=True)
        with right:
            st.subheader("Top employers")
            st.caption("The 10 companies with the most postings")
            chart = alt.Chart(data["companies"]).mark_bar(color=ACCENT).encode(
                x=alt.X("jobs:Q", title="Postings", axis=alt.Axis(tickMinStep=1)),
                y=alt.Y("company:N", sort="-x", title=None), tooltip=["company", "jobs"],
            ).properties(height=220)
            st.altair_chart(chart, use_container_width=True)
        st.divider()
        st.subheader("Salaries")
        st.write(f"{int(summary['salary_records']):,} of {total:,} postings list a salary.")
        st.caption("Averages are only taken within the same currency and pay period. Amounts are not converted "
                   "between currencies or from hourly to yearly. Postings with an unknown currency or period are left out.")
        if not data["salaries"].empty:
            salaries = data["salaries"].assign(
                salary_period=data["salaries"]["salary_period"].map(readable_period),
                mean_midpoint=pd.to_numeric(data["salaries"]["mean_midpoint"]).round(2))
            st.dataframe(salaries.rename(columns={"salary_currency": "Currency",
                "salary_period": "Pay period", "jobs": "Postings", "mean_midpoint": "Average salary (midpoint)"}),
                hide_index=True, width="stretch", column_config={"Average salary (midpoint)": MONEY})

    with qualifications:
        st.subheader("Most mentioned skills")
        st.caption("The 15 skills that come up most in the qualifications. Only skills from a fixed list are counted; "
                   "everything else is still shown in the job listings.")
        if data["skills"].empty:
            st.info("No extracted skills are available for this view.")
        else:
            st.dataframe(data["skills"].rename(columns={"skill": "Skill", "jobs": "Postings"}),
                         hide_index=True, width="stretch")

    with listings:
        st.subheader("Job listings")
        st.caption("Up to 200 postings, newest first. Salaries are shown as posted, in their own currency.")
        listings = data["listings"].copy()
        if "salary_period" in listings:
            listings["salary_period"] = listings["salary_period"].map(readable_period)
        if "qualifications" in listings:
            listings["qualifications"] = listings["qualifications"].map(readable_qualifications)
        st.dataframe(listings.rename(columns={
            "job_id": "Job ID", "title": "Title", "company": "Company", "location": "Location",
            "date_posted": "Posted", "salary_min": "Salary low", "salary_max": "Salary high",
            "avg_salary": "Salary midpoint", "salary_currency": "Currency", "salary_period": "Pay period",
            "qualifications": "Qualifications",
        }), hide_index=True, width="stretch",
            column_config={name: MONEY for name in ("Salary low", "Salary high", "Salary midpoint")})


if __name__ == "__main__":
    main()
