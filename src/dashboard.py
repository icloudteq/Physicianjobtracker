"""
Physician Job Tracker — Streamlit App
Run with: streamlit run src/dashboard.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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

# Auto-refresh UI every 60s so new jobs appear without manual reload
st_autorefresh(interval=60_000, key="auto_refresh")

# Auto-start background scheduler (runs pipeline every 2h silently)
if not is_running():
    start_scheduler()


@st.cache_data(ttl=60)
def load_jobs(status_filter=None, state_filter=None, visa_filter=None,
              priority_filter=None, specialty_filter=None, job_type_filter=None,
              salary_min=None, date_from=None):
    session = get_session()
    q = session.query(Job)
    if status_filter and status_filter != "All":
        q = q.filter(Job.status == status_filter)
    if state_filter:
        q = q.filter(Job.state.in_(state_filter))
    if visa_filter == "H1B Confirmed":
        q = q.filter(Job.h1b_status == "confirmed")
    elif visa_filter == "H1B Possible":
        q = q.filter(Job.h1b_status == "possible")
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
    # Job type filter
    if job_type_filter == "Permanent":
        q = q.filter(~Job.title.ilike("%locum%"), ~Job.title.ilike("%temp%"), ~Job.title.ilike("%contract%"))
    elif job_type_filter == "Locums / Temp":
        q = q.filter(Job.title.ilike("%locum%") | Job.title.ilike("%temp%") | Job.title.ilike("%contract%") | Job.short_summary.ilike("%locum%"))
    elif job_type_filter == "Hospitalist":
        q = q.filter(Job.title.ilike("%hospitalist%") | Job.specialty.ilike("%hospitalist%"))
    elif job_type_filter == "Nocturnist":
        q = q.filter(Job.title.ilike("%nocturnist%"))
    elif job_type_filter == "Primary Care":
        q = q.filter(
            Job.title.ilike("%primary care%") | Job.title.ilike("%family medicine%") |
            Job.title.ilike("%internal medicine%") | Job.title.ilike("%internist%")
        )
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
            salary_display = j.salary_text[:50]

        dol_salary = ""
        if j.dol_salary_min:
            dol_salary = f"${j.dol_salary_min:,}–${j.dol_salary_max:,} ({j.dol_salary_year})"

        location = ", ".join(x for x in [j.city or "", j.state or ""] if x)

        rows.append({
            "ID": j.id,
            "Priority": j.priority_label or "LOW",
            "H1B": j.h1b_status or "unknown",
            "J1": j.j1_status or "unknown",
            "Title": j.title,
            "Employer": j.employer,
            "Location": location,
            "Specialty": j.specialty or "",
            "Salary (Posted)": salary_display,
            "DOL Salary": dol_salary,
            "Email": j.contact_email or "",
            "Phone": j.contact_phone or "",
            "Contact": j.contact_name or "",
            "Posted": str(j.posted_date) if j.posted_date else (
                j.first_seen_at.strftime("%Y-%m-%d") if j.first_seen_at else ""
            ),
            "Score": round(j.priority_score or 0, 1),
            "Source": j.source_name or "",
            "Apply": j.source_url or "",
            "Status": j.status or "new",
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
tab2, tab1, tab3, tab4 = st.tabs(["🔍 Browse Jobs", "▶ Run Pipeline", "📥 Exports", "⚙ Sources"])


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

    run_btn = st.button("🚀 Run Now", type="primary", use_container_width=True)

    if run_btn:
        # Live status panel
        s1, s2, s3 = st.columns(3)
        metric_new   = s1.empty()
        metric_src   = s2.empty()
        metric_high  = s3.empty()
        prog_bar     = st.progress(0, text="Starting…")
        log_box      = st.empty()

        metric_new.metric("New Jobs Found", 0)
        metric_src.metric("Current Source", "—")
        metric_high.metric("HIGH Priority", 0)

        log_lines: list[str] = []
        live_new   = [0]
        live_high  = [0]
        src_count  = [0]
        _N_SCRAPERS = 14  # 10 board scrapers + ~4 hospital/csv phases

        def update_log(msg: str):
            ts = datetime.utcnow().strftime("%H:%M:%S")

            if msg.startswith("Scraping "):
                src_count[0] += 1
                src = msg.removeprefix("Scraping ").removesuffix("…").removesuffix("...")
                metric_src.metric("Current Source", src)
                prog_bar.progress(
                    min(src_count[0] / _N_SCRAPERS, 0.95),
                    text=f"Scraping {src}…",
                )
                icon = "🔍"
            elif " found, " in msg and " new" in msg:
                try:
                    new_n = int(msg.strip().split(",")[1].strip().split(" ")[0])
                    live_new[0] += new_n
                    metric_new.metric("New Jobs Found", live_new[0])
                except (ValueError, IndexError):
                    pass
                icon = "✅"
            elif "HIGH" in msg or "high" in msg:
                icon = "⭐"
            elif "Pipeline complete" in msg:
                prog_bar.progress(1.0, text="Done")
                icon = "🏁"
            elif "error" in msg.lower() or "failed" in msg.lower():
                icon = "❌"
            else:
                icon = "·"

            log_lines.append(f"{ts}  {icon}  {msg}")
            log_box.code("\n".join(log_lines[-50:]), language=None)

        from src.main import run_pipeline
        result = run_pipeline(
            states=selected_states or None,
            terms=selected_terms or None,
            progress_cb=update_log,
        )

        metric_new.metric("New Jobs Found", result["total_new"])
        metric_high.metric("HIGH Priority", result["total_high"])
        metric_src.metric("Current Source", "Done ✅")
        prog_bar.progress(1.0, text="Complete")

        st.success(f"✅ Done — {result['total_new']} new jobs, {result['total_high']} HIGH priority. Exported to {result['export_path']}")
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.subheader("H1B Detail Enricher")
    st.caption("Fetches full job pages for NC/SC to extract H1B status, salary, and contact info from complete job descriptions.")
    col_enrich1, col_enrich2, col_enrich3 = st.columns([1, 1, 2])
    with col_enrich1:
        enrich_limit = st.number_input("Max jobs to check", min_value=10, max_value=500, value=200, step=10)
    with col_enrich2:
        enrich_states = st.multiselect("States", options=["NC", "SC", "VA", "GA", "TN"], default=["NC", "SC"])
    with col_enrich3:
        st.write("")
        enrich_btn = st.button("🔬 Enrich H1B/Salary/Contact", use_container_width=True)

    if enrich_btn:
        with st.spinner("Fetching job detail pages…"):
            from src.detail_enricher import enrich_job_details
            er = enrich_job_details(states=enrich_states or ["NC", "SC"], limit=int(enrich_limit))
        st.success(
            f"✅ Enriched {er['enriched']}/{er['total_checked']} jobs — "
            f"H1B: {er['h1b_found']} | Salary: {er['salary_found']} | Contact: {er['contact_found']}"
        )
        st.cache_data.clear()
        st.rerun()


# ── Tab 2: Browse Jobs ────────────────────────────────────────────────────────
with tab2:
    st.header("Browse Jobs")

    # Row 1: States, Visa, Priority, Job Type, Salary
    f1, f2, f3, f4, f5 = st.columns(5)
    with f1:
        filt_states = st.multiselect("State", options=["NC", "SC"] + [s for s in all_states if s not in ["NC", "SC"]], default=["NC", "SC"])
    with f2:
        filt_visa = st.selectbox("Visa / H1B", ["All", "H1B Confirmed", "H1B Possible", "J1 Confirmed", "Any Visa"])
    with f3:
        filt_priority = st.selectbox("Priority", ["All", "HIGH", "MEDIUM", "LOW"])
    with f4:
        filt_job_type = st.selectbox("Job Type", ["All", "Permanent", "Locums / Temp", "Hospitalist", "Nocturnist", "Primary Care"])
    with f5:
        filt_salary = st.number_input("Min Salary $", min_value=0, value=0, step=10000)

    jobs = load_jobs(
        state_filter=filt_states or None,
        visa_filter=filt_visa if filt_visa != "All" else None,
        priority_filter=filt_priority if filt_priority != "All" else None,
        job_type_filter=filt_job_type if filt_job_type != "All" else None,
        salary_min=filt_salary if filt_salary > 0 else None,
    )

    df = jobs_to_df(jobs)
    st.caption(f"{len(df)} jobs found")

    if df.empty:
        st.info("No jobs match your filters. Run the pipeline first.")
    else:
        def priority_style(val):
            colors = {"HIGH": "background-color:#d4edda;color:#155724;font-weight:bold",
                      "MEDIUM": "background-color:#fff3cd;color:#856404",
                      "LOW": "color:#6c757d"}
            return colors.get(val, "")

        def h1b_style(val):
            colors = {"confirmed": "background-color:#d4edda;color:#155724;font-weight:bold",
                      "possible": "background-color:#cce5ff;color:#004085",
                      "no": "background-color:#f8d7da;color:#721c24",
                      "unknown": "color:#6c757d"}
            return colors.get(val, "")

        display_cols = [
            "Priority", "H1B", "J1", "Title", "Employer", "Location",
            "Salary (Posted)", "DOL Salary", "Email", "Phone", "Contact",
            "Posted", "Source", "Apply", "Score", "Status",
        ]
        styled = (
            df[display_cols]
            .style
            .map(priority_style, subset=["Priority"])
            .map(h1b_style, subset=["H1B"])
        )
        col_cfg = {
            "Apply": st.column_config.LinkColumn("Apply Link", display_text="Apply"),
            "Priority": st.column_config.TextColumn("Priority", width="small"),
            "H1B": st.column_config.TextColumn("H1B", width="small"),
            "J1": st.column_config.TextColumn("J1", width="small"),
            "Score": st.column_config.NumberColumn("Score", width="small"),
        }
        selected_row = st.dataframe(
            styled, use_container_width=True,
            on_select="rerun", selection_mode="single-row",
            column_config=col_cfg,
        )

        csv_bytes = df.to_csv(index=False).encode()
        st.download_button("⬇ Download filtered CSV", csv_bytes, "filtered_jobs.csv", "text/csv")

        # Detail panel for selected row
        if selected_row and selected_row.selection.rows:
            idx = selected_row.selection.rows[0]
            job_id = int(df.iloc[idx]["ID"])
            job = next((j for j in jobs if j.id == job_id), None)

            if job:
                h1b_emoji = {"confirmed": "✅", "possible": "🔵", "no": "❌"}.get(job.h1b_status, "❓")
                with st.expander(f"{h1b_emoji} {job.title} — {job.employer} | {job.city or ''}, {job.state}", expanded=True):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.markdown("**Position**")
                        st.markdown(f"**Title:** {job.title}")
                        st.markdown(f"**Employer:** {job.employer}")
                        st.markdown(f"**Location:** {job.city or 'N/A'}, {job.state}")
                        st.markdown(f"**Specialty:** {job.specialty or 'N/A'}")
                        st.markdown(f"**Type:** {job.job_type or 'N/A'}")
                        st.markdown(f"**Posted:** {job.posted_date or (job.first_seen_at.strftime('%Y-%m-%d') if job.first_seen_at else 'N/A')}")
                    with c2:
                        st.markdown("**Salary**")
                        if job.salary_text:
                            st.markdown(f"**Posted:** {job.salary_text}")
                        elif job.salary_min:
                            st.markdown(f"**Posted:** ${job.salary_min:,}–${job.salary_max:,}" if job.salary_max else f"${job.salary_min:,}+")
                        else:
                            st.markdown("**Posted:** Not listed")
                        if job.dol_salary_min:
                            st.markdown(f"**DOL Historical:** ${job.dol_salary_min:,}–${job.dol_salary_max:,}")
                            st.caption(f"({job.dol_salary_year}, {job.dol_case_count} H1B filings)")
                        st.markdown("**Contact**")
                        st.markdown(f"**Name:** {job.contact_name or 'N/A'}")
                        st.markdown(f"**Email:** {job.contact_email or 'N/A'}")
                        st.markdown(f"**Phone:** {job.contact_phone or 'N/A'}")
                    with c3:
                        st.markdown("**Visa Sponsorship**")
                        st.markdown(f"**H1B:** `{job.h1b_status}` {h1b_emoji}")
                        st.markdown(f"**J1:** `{job.j1_status}`")
                        st.markdown(f"**Waiver:** `{job.waiver_status}`")
                        if job.visa_text:
                            st.caption(f'"{job.visa_text}"')
                        st.markdown("**Priority**")
                        st.markdown(f"**Label:** **{job.priority_label}** (score {job.priority_score:.0f})")
                        st.markdown(f"**Source:** {job.source_name}")

                    if job.source_url:
                        st.link_button("Apply / View Full Posting", job.source_url, use_container_width=True)

                    if job.short_summary:
                        with st.expander("Job Summary"):
                            st.text(job.short_summary[:800])

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
