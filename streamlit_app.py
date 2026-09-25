"""TalentScope's read-only analytics dashboard. Run from the repository root."""

import altair as alt
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from src.analytics import load_analytics


def main():
    st.set_page_config(page_title="TalentScope | Job market analytics", page_icon="◈", layout="wide")
    # Keep the reading area comfortable on laptop screens; retain native scrolling.
    st.html("""
        <style>
        [data-testid="stMainBlockContainer"] {
            max-width: 1240px;
            padding: 5rem 2.5rem 3rem;
        }
        [data-testid="stMain"] h1 {
            font-size: clamp(1.8rem, 2.5vw, 2.5rem);
            line-height: 1.2;
            letter-spacing: -0.025em;
            padding-top: 0.25rem;
        }
        [data-testid="stSidebarUserContent"] { padding-top: 3rem; }
        [data-testid="stMetric"] {
            background: #1C2721;
            border: 1px solid #34483B;
            border-radius: 12px;
            padding: 1rem 1.1rem;
        }
        [data-testid="stMetricValue"] { font-size: 2rem; }
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
    st.caption("TALENTSCOPE / MARKET INTELLIGENCE")
    st.title("A clearer view of the job market.")
    st.write("Explore hiring activity, employers, and the qualifications appearing in stored job postings.")

    with st.sidebar:
        st.title("TalentScope")
        st.caption("Focus your view")
        with st.form("filters"):
            title = st.text_input("Job title", placeholder="e.g. Data engineer")
            company = st.text_input("Company", placeholder="Any employer")
            start = st.date_input("Posted from", value=None)
            end = st.date_input("Posted through", value=None)
            st.form_submit_button("Apply filters", type="primary", width="stretch")
        st.caption("Leave dates blank to include undated postings. Apply filters again to refresh.")

    if start and end and start > end:
        st.warning("Choose an end date on or after the start date.")
        return
    try:
        with st.spinner("Loading market data…"):
            data = load_analytics(title=title, company=company, start_date=start, end_date=end)
    except (ValueError, SQLAlchemyError):
        st.error("Market data is unavailable. Check the database configuration and connection, then try again.")
        return

    summary = data["summary"].iloc[0]
    total = int(summary["jobs"])
    columns = st.columns(4)
    for column, label, value in zip(columns,
            ("Stored postings", "Companies", "With salary values", "With posting dates"),
            (total, int(summary["companies"]), int(summary["salary_records"]), int(summary["dated_records"]))):
        with column:
            st.metric(label, f"{value:,}")
    st.caption("This dataset includes only postings retained by the ingestion pipeline; it is not a complete market census.")
    if total == 0:
        st.info("No postings match this view. Broaden the filters, or load job data to get started.")
        return

    overview, qualifications, listings = st.tabs(["Market overview", "Skills", "Job listings"])
    with overview:
        left, right = st.columns([3, 2])
        with left:
            st.subheader("Posting activity")
            st.caption("Stored postings by date · undated records excluded")
            if data["trend"].empty:
                st.info("No posting dates are available for this view.")
            else:
                chart = alt.Chart(data["trend"]).mark_line(point=True, color="#80BC92").encode(
                    x=alt.X("date_posted:T", title="Posted date"),
                    y=alt.Y("jobs:Q", title="Postings", axis=alt.Axis(tickMinStep=1)),
                    tooltip=[alt.Tooltip("date_posted:T", title="Date"), alt.Tooltip("jobs:Q", title="Postings")],
                ).properties(height=300)
                st.altair_chart(chart, use_container_width=True)
        with right:
            st.subheader("Leading employers")
            st.caption("Top 10 by stored postings")
            chart = alt.Chart(data["companies"]).mark_bar(color="#80BC92", cornerRadiusEnd=3).encode(
                x=alt.X("jobs:Q", title="Postings", axis=alt.Axis(tickMinStep=1)),
                y=alt.Y("company:N", sort="-x", title=None), tooltip=["company", "jobs"],
            ).properties(height=300)
            st.altair_chart(chart, use_container_width=True)
        st.divider()
        st.subheader("Salary coverage")
        st.write(f"{int(summary['salary_records']):,} of {total:,} postings have a stored salary value.")
        st.caption("Amounts are compared only within the same currency and pay period. No currency conversion or annualization is applied. Unknown units are excluded from this summary.")
        if not data["salaries"].empty:
            st.dataframe(data["salaries"].rename(columns={"salary_currency": "Currency",
                "salary_period": "Period", "jobs": "Postings", "mean_midpoint": "Mean reported midpoint"}),
                hide_index=True, width="stretch")

    with qualifications:
        st.subheader("Frequently mentioned skills")
        st.caption("Top 15 skills explicitly matched in qualification text using a limited vocabulary. Unmatched qualifications remain in the listings.")
        if data["skills"].empty:
            st.info("No extracted skills are available for this view.")
        else:
            st.dataframe(data["skills"].rename(columns={"skill": "Skill", "jobs": "Postings"}),
                         hide_index=True, width="stretch")

    with listings:
        st.subheader("Explore the postings")
        st.caption("Up to 200 matches, newest dated postings first. Salary amounts are unconverted source values.")
        st.dataframe(data["listings"].rename(columns={
            "job_id": "Job ID", "title": "Title", "company": "Company", "location": "Location",
            "date_posted": "Posted", "salary_min": "Salary low (raw)",
            "salary_max": "Salary high (raw)", "avg_salary": "Salary midpoint (raw)",
            "salary_currency": "Currency", "salary_period": "Pay period", "qualifications": "Qualifications (JSON)",
        }), hide_index=True, width="stretch")


if __name__ == "__main__":
    main()
