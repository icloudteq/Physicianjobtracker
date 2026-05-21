"""
Physician Job Tracker — Streamlit App
Run with: streamlit run src/dashboard.py
"""
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml
from streamlit_autorefresh import st_autorefresh

from src.db import Employer, GmailDraft, Job, ScrapeRun, get_session
from src.scheduler import get_next_run_time, is_running, start_scheduler

st.set_page_config(
    page_title="Physician Job Tracker",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Auto-refresh every 60s
st_autorefresh(interval=60_000, key="auto_refresh")


@st.cache_data(ttl=60)
def load_jobs(status_filter=None, state_filter=None, visa_filter=None,
              priority_filter=None, specialty_filter=None,
              salary_min=None, date_from=None):
    session = get_session()
    q = session.query(Job)
    if status_filter and status_filter != "All":
        q = q.filter(Job.status == status_filter)
    if state_filter:
        q = q.filter(Job.state.in_(state_filter))
    if visa_filter == "H1B Confirmed":
        q = q.filter(Job.h1b_status == "confirmed")
    elif visa_filter == "J1 Confirmed":
        q = q.filter(Job.j1_status == "confirmed")
    elif visa_filter == "Any Visa":
        q = q.filter(Job.h1b_status.in_(["confirmed", "possible"]))
    if priority_filter and priority_filter != "All":
        q = q.filter(Job.priority_label == priority_filter)
    if specialty_filter == "Internal Medicine":
        q = q.filter(Job.specialty.ilike("%internal medicine%") | Job.specialty.ilike("%hospitalist%") | Job.specialty.ilike("%nocturnist%"))
    elif specialty_filter == "Family Medicine":
        q = q.filter(Job.specialty.ilike("%family%"))
    if salary_min:
        q = q.filter(Job.salary_min >= salary_min)
    if date_from:
        q = q.filter(Job.posted_date >= date_from)
    jobs = q.order_by(Job.priority_score.desc(), Job.first_seen_at.desc()).limit(500).all()
    session.close()
    return jobs


@st.cache_data(ttl=60)
def load_stats():
    session = get_session()
    total = session.query(Job).count()
    high = session.query(Job).filter_by(priority_label="HIGH").count()
    new_today = session.query(Job).filter(
        Job.first_seen_at >= datetime.utcnow().strftime("%Y-%m-%d")
    ).count()
    h1b = session.query(Job).filter_by(h1b_status="confirmed").count()
    session.close()
    return {"total": total, "high": high, "new_today": new_today, "h1b": h1b}


def jobs_to_df(jobs: list) -> pd.DataFrame:
    rows = []
    for j in jobs:
        salary_display = ""
        if j.salary_min and j.salary_max:
            salary_display = f"${j.salary_min:,} – ${j.salary_max:,}"
        elif j.salary_min:
            salary_display = f"${j.salary_min:,}+"
        elif j.salary_text:
            salary_display = j.salary_text[:40]

        dol_salary = ""
        if j.dol_salary_min:
            dol_salary = f"${j.dol_salary_min:,}–${j.dol_salary_max:,} ({j.dol_salary_year})"

        rows.append({
            "ID": j.id,
            "Title": j.title,
            "Employer": j.employer,
            "City": j.city or "",
            "State": j.state or "",
            "Specialty": j.specialty or "",
            "Salary (Posted)": salary_display,
            "DOL Historical $": dol_salary,
            "Contact": j.contact_name or "",
            "Email": j.contact_email or "",
            "Phone": j.contact_phone or "",
            "H1B": j.h1b_status or "unknown",
            "J1": j.j1_status or "unknown",
            "Posted": str(j.posted_date) if j.posted_date else "",
            "Priority": j.priority_label or "LOW",
            "Score": round(j.priority_score or 0, 1),
            "Status": j.status or "new",
            "Source": j.source_name or "",
            "URL": j.source_url or "",
            "First Seen": j.first_seen_at.strftime("%Y-%m-%d") if j.first_seen_at else "",
        })
    return pd.DataFrame(rows)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🏥 Physician Job Tracker")

    scheduler_status = "🟢 Running" if is_running() else "🔴 Stopped"
    next_run = get_next_run_time()
    st.markdown(f"**Auto-run:** {scheduler_status}")
    if next_run:
        st.markdown(f"**Next run:** {next_run}")
    st.markdown(f"**Last refresh:** {datetime.utcnow().strftime('%H:%M UTC')}")

    if not is_running():
        if st.button("▶ Start Auto-Refresh (every 2h)"):
            start_scheduler()
            st.rerun()

    stats = load_stats()
    st.markdown("---")
    st.metric("Total Jobs", stats["total"])
    st.metric("HIGH Priority", stats["high"])
    st.metric("New Today", stats["new_today"])
    st.metric("H1B Confirmed", stats["h1b"])


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["▶ Run Pipeline", "🔍 Browse Jobs", "📥 Exports", "⚙ Sources"])


# ── Tab 1: Run Pipeline ───────────────────────────────────────────────────────
with tab1:
    st.header("Run Job Search Pipeline")

    states_cfg = yaml.safe_load(Path("config/states.yaml").read_text())
    all_states = list(states_cfg["states"].keys())
    preferred = states_cfg.get("preferred_states", ["NC", "SC"])

    col1, col2 = st.columns(2)
    with col1:
        selected_states = st.multiselect(
            "States to search",
            options=all_states,
            default=preferred,
            help="NC and SC are pre-selected as priority states",
        )
    with col2:
        terms_cfg = yaml.safe_load(Path("config/search_terms.yaml").read_text())
        all_terms = []
        for group in terms_cfg.get("specialty_terms", {}).values():
            all_terms.extend(group)
        selected_terms = st.multiselect(
            "Specialty terms",
            options=all_terms,
            default=all_terms[:5],
        )

    log_container = st.empty()
    run_btn = st.button("🚀 Run Now", type="primary", use_container_width=True)

    if run_btn:
        log_lines = []
        log_box = st.empty()

        def update_log(msg: str):
            log_lines.append(msg)
            log_box.text("\n".join(log_lines[-30:]))

        with st.spinner("Running pipeline..."):
            from src.main import run_pipeline
            result = run_pipeline(
                states=selected_states or None,
                terms=selected_terms or None,
                progress_cb=update_log,
            )

        st.success(f"✅ Done — {result['total_new']} new jobs found ({result['total_high']} HIGH priority)")
        st.cache_data.clear()
        st.rerun()


# ── Tab 2: Browse Jobs ────────────────────────────────────────────────────────
with tab2:
    st.header("Browse Jobs")

    # Filters
    f1, f2, f3, f4, f5 = st.columns(5)
    with f1:
        filt_states = st.multiselect("State", options=["NC", "SC"] + [s for s in all_states if s not in ["NC", "SC"]], default=[])
    with f2:
        filt_visa = st.selectbox("Visa", ["All", "H1B Confirmed", "J1 Confirmed", "Any Visa"])
    with f3:
        filt_priority = st.selectbox("Priority", ["All", "HIGH", "MEDIUM", "LOW"])
    with f4:
        filt_specialty = st.selectbox("Specialty", ["All", "Internal Medicine", "Family Medicine"])
    with f5:
        filt_salary = st.number_input("Min Salary $", min_value=0, value=0, step=10000)

    jobs = load_jobs(
        state_filter=filt_states or None,
        visa_filter=filt_visa if filt_visa != "All" else None,
        priority_filter=filt_priority if filt_priority != "All" else None,
        specialty_filter=filt_specialty if filt_specialty != "All" else None,
        salary_min=filt_salary if filt_salary > 0 else None,
    )

    df = jobs_to_df(jobs)
    st.caption(f"{len(df)} jobs found")

    if df.empty:
        st.info("No jobs match your filters. Run the pipeline first.")
    else:
        # Priority color coding
        def priority_style(val):
            colors = {"HIGH": "background-color: #d4edda", "MEDIUM": "background-color: #fff3cd", "LOW": ""}
            return colors.get(val, "")

        display_cols = ["Title", "Employer", "City", "State", "Salary (Posted)", "DOL Historical $",
                        "Contact", "Email", "Phone", "H1B", "J1", "Posted", "Priority", "Score", "Status"]
        styled = df[display_cols].style.applymap(priority_style, subset=["Priority"])
        selected_row = st.dataframe(styled, use_container_width=True, on_select="rerun", selection_mode="single-row")

        # Download filtered view
        csv_bytes = df.to_csv(index=False).encode()
        st.download_button("⬇ Download filtered CSV", csv_bytes, "filtered_jobs.csv", "text/csv")

        # Detail panel for selected row
        if selected_row and selected_row.selection.rows:
            idx = selected_row.selection.rows[0]
            job_id = int(df.iloc[idx]["ID"])
            job = next((j for j in jobs if j.id == job_id), None)

            if job:
                with st.expander(f"📋 {job.title} — {job.employer}", expanded=True):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown(f"**Employer:** {job.employer}")
                        st.markdown(f"**Location:** {job.city}, {job.state}")
                        st.markdown(f"**Specialty:** {job.specialty or 'N/A'}")
                        st.markdown(f"**Job Type:** {job.job_type or 'N/A'}")
                        if job.salary_text:
                            st.markdown(f"**Salary (Posted):** {job.salary_text}")
                        if job.dol_salary_min:
                            st.markdown(f"**DOL Historical:** ${job.dol_salary_min:,}–${job.dol_salary_max:,} ({job.dol_salary_year}, {job.dol_case_count} filings)")
                    with c2:
                        st.markdown(f"**H1B:** `{job.h1b_status}`")
                        st.markdown(f"**J1:** `{job.j1_status}`")
                        st.markdown(f"**Waiver:** `{job.waiver_status}`")
                        st.markdown(f"**Contact:** {job.contact_name or 'N/A'}")
                        st.markdown(f"**Email:** {job.contact_email or 'N/A'}")
                        st.markdown(f"**Phone:** {job.contact_phone or 'N/A'}")
                        st.markdown(f"**Posted:** {job.posted_date or 'N/A'}")
                        st.markdown(f"**Priority:** **{job.priority_label}** (score {job.priority_score:.0f})")

                    st.markdown(f"**Source:** [{job.source_url}]({job.source_url})")
                    if job.short_summary:
                        st.markdown("**Summary:**")
                        st.text(job.short_summary[:500])

                    # Status update
                    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
                    session = get_session()
                    db_job = session.query(Job).filter_by(id=job_id).first()
                    if db_job:
                        with col_s1:
                            if st.button("✅ Applied", key=f"applied_{job_id}"):
                                db_job.status = "applied"
                                session.commit()
                                st.cache_data.clear()
                                st.rerun()
                        with col_s2:
                            if st.button("👀 Reviewed", key=f"reviewed_{job_id}"):
                                db_job.status = "reviewed"
                                session.commit()
                                st.cache_data.clear()
                                st.rerun()
                        with col_s3:
                            if st.button("❌ Reject", key=f"reject_{job_id}"):
                                db_job.status = "rejected"
                                session.commit()
                                st.cache_data.clear()
                                st.rerun()
                        with col_s4:
                            email_to = st.text_input("Email to", value=job.contact_email or "", key=f"email_{job_id}")
                            if st.button("✉ Create Gmail Draft", key=f"draft_{job_id}"):
                                from src.gmail_drafts import create_draft
                                result = create_draft(session, job_id, email_to or None)
                                if result.get("success"):
                                    st.success("Draft created in Gmail!")
                                else:
                                    st.error(result.get("error", "Unknown error"))
                    session.close()


# ── Tab 3: Exports ────────────────────────────────────────────────────────────
with tab3:
    st.header("Export History")

    export_dir = Path(os.getenv("EXPORT_DIR", "data/exports"))
    if not export_dir.exists():
        st.info("No exports yet. Run the pipeline first.")
    else:
        run_dirs = sorted(export_dir.iterdir(), reverse=True)
        for run_dir in run_dirs[:10]:
            if run_dir.is_dir():
                with st.expander(f"📁 {run_dir.name}", expanded=(run_dir == run_dirs[0])):
                    for csv_file in run_dir.glob("*.csv"):
                        data = csv_file.read_bytes()
                        st.download_button(
                            f"⬇ {csv_file.name}",
                            data,
                            csv_file.name,
                            "text/csv",
                            key=str(csv_file),
                        )
                    summary = run_dir / "daily_summary.txt"
                    if summary.exists():
                        st.text(summary.read_text())


# ── Tab 4: Sources ────────────────────────────────────────────────────────────
with tab4:
    st.header("Sources & Employers")

    session = get_session()

    # Source run stats
    st.subheader("Job Board Sources")
    runs = (
        session.query(ScrapeRun)
        .order_by(ScrapeRun.started_at.desc())
        .limit(100)
        .all()
    )
    if runs:
        run_rows = [{
            "Source": r.source_name,
            "Started": str(r.started_at)[:16],
            "Found": r.jobs_found,
            "New": r.new_jobs,
            "Dupes": r.duplicates_found,
            "Errors": r.errors or "",
            "Status": r.status,
        } for r in runs]
        st.dataframe(pd.DataFrame(run_rows), use_container_width=True)

    # Employer career pages
    st.subheader("Hospital Career Pages")
    employers = session.query(Employer).order_by(Employer.state, Employer.employer_name).all()

    if employers:
        emp_rows = [{"Name": e.employer_name, "State": e.state, "Type": e.employer_type, "URL": e.careers_url} for e in employers]
        st.dataframe(pd.DataFrame(emp_rows), use_container_width=True)

    # Add employer
    st.subheader("Add Employer Career Page")
    with st.form("add_employer"):
        emp_name = st.text_input("Employer Name")
        emp_url = st.text_input("Careers URL")
        emp_state = st.selectbox("State", options=all_states)
        emp_type = st.selectbox("Type", ["hospital", "academic", "fqhc", "va", "unknown"])
        submitted = st.form_submit_button("Add")
        if submitted and emp_name and emp_url:
            existing = session.query(Employer).filter_by(careers_url=emp_url).first()
            if not existing:
                session.add(Employer(
                    employer_name=emp_name,
                    careers_url=emp_url,
                    state=emp_state,
                    employer_type=emp_type,
                ))
                session.commit()
                st.success(f"Added {emp_name}")
                st.rerun()
            else:
                st.warning("Already exists")

    # Manual CSV import
    st.subheader("Manual CSV Import")
    st.markdown("Upload a CSV with columns: `title`, `employer`, `state`, `city`, `salary_text`, `visa_text`, `contact_email`, `source_url`")
    uploaded = st.file_uploader("Upload CSV", type="csv")
    if uploaded:
        import_path = Path("data/manual_imports") / uploaded.name
        import_path.write_bytes(uploaded.read())
        st.success(f"Saved to {import_path}. Will be imported on next pipeline run.")

    session.close()
