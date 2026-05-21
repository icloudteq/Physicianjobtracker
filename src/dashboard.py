"""
Streamlit Web Dashboard — run: streamlit run src/dashboard.py
"""
import streamlit as st
import pandas as pd
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import init_db, get_jobs, get_stats, get_job_count, save_gmail_draft
from src.main import run_pipeline, DEFAULT_STATES, DEFAULT_TERMS
from src.gmail_drafts import create_drafts_for_jobs
from src.exporters import export_csv, export_high_priority, export_summary_report

st.set_page_config(
    page_title="Physician Job Tracker",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()

# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.title("🏥 Physician Job Tracker")
st.sidebar.caption("Private tool for Internal Medicine job search")

st.sidebar.header("Search Settings")

ALL_STATES = ["NC", "SC", "TX", "NM", "AZ", "OK", "LA"]
selected_states = st.sidebar.multiselect(
    "Target States",
    ALL_STATES,
    default=["NC", "SC"],
)

ALL_TERMS = [
    "Internal Medicine Physician", "Hospitalist", "Nocturnist",
    "Primary Care Physician", "Outpatient Internal Medicine",
    "Academic Internal Medicine", "Internal Medicine Faculty",
    "IM Hospitalist", "PCP Internal Medicine",
]
selected_terms = st.sidebar.multiselect(
    "Specialty Terms",
    ALL_TERMS,
    default=["Internal Medicine Physician", "Hospitalist"],
)

st.sidebar.divider()
st.sidebar.header("Filters")
show_h1b = st.sidebar.checkbox("H1B Only (confirmed/possible)")
show_j1 = st.sidebar.checkbox("J1 Only (confirmed/possible)")
min_score = st.sidebar.slider("Min Priority Score", 0, 100, 0)
priority_filter = st.sidebar.multiselect(
    "Priority Label",
    ["high", "medium", "normal", "low"],
    default=[],
)

st.sidebar.divider()

# ── Run Pipeline ─────────────────────────────────────────────────────────────
if st.sidebar.button("🚀 Run Job Search Now", type="primary", use_container_width=True):
    if not selected_states:
        st.sidebar.error("Select at least one state.")
    else:
        with st.spinner(f"Searching {', '.join(selected_states)} across all sources..."):
            result = run_pipeline(selected_states, selected_terms)
        st.sidebar.success(
            f"Done! {result['total_new']} new jobs found."
            + (f" ({len(result['errors'])} errors)" if result["errors"] else "")
        )
        st.rerun()

# ── Main Content ──────────────────────────────────────────────────────────────
st.title("🏥 Physician Job Intelligence Dashboard")

stats = get_stats()
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Jobs", stats["total"])
with col2:
    h1b_conf = next((r["n"] for r in stats["h1b"] if r["h1b_status"] == "confirmed"), 0)
    st.metric("H1B Confirmed", h1b_conf)
with col3:
    j1_conf = next((r["n"] for r in stats["j1"] if r["j1_status"] == "confirmed"), 0)
    st.metric("J1 Confirmed", j1_conf)
with col4:
    nc_sc = sum(r["n"] for r in stats["by_state"] if r["state"] in ("NC", "SC"))
    st.metric("NC + SC Jobs", nc_sc)

st.divider()

# ── Load & Filter Jobs ────────────────────────────────────────────────────────
jobs = get_jobs(
    states=selected_states or None,
    h1b_only=show_h1b,
    j1_only=show_j1,
    min_priority=min_score,
    limit=1000,
)
if priority_filter:
    jobs = [j for j in jobs if j.get("priority_label") in priority_filter]

df = pd.DataFrame(jobs) if jobs else pd.DataFrame()

tab1, tab2, tab3 = st.tabs(["📋 Job List", "📊 Analytics", "📧 Email Drafts"])

# ── Tab 1: Job List ───────────────────────────────────────────────────────────
with tab1:
    st.subheader(f"Jobs ({len(df)} results)")

    if df.empty:
        st.info("No jobs found. Run a search to get started.")
    else:
        DISPLAY_COLS = [
            "title", "employer", "city", "state", "source_name",
            "posted_date", "h1b_status", "j1_status", "waiver_status",
            "salary_text", "priority_score", "priority_label",
            "apply_url", "first_seen_at",
        ]
        for c in DISPLAY_COLS:
            if c not in df.columns:
                df[c] = ""

        def color_priority(val):
            colors = {"high": "background-color:#d4edda", "medium": "background-color:#fff3cd",
                      "normal": "", "low": "background-color:#f8d7da"}
            return colors.get(val, "")

        def color_visa(val):
            if val == "confirmed": return "color:green;font-weight:bold"
            if val == "possible": return "color:orange"
            if val == "no": return "color:red"
            return "color:gray"

        styled = df[DISPLAY_COLS].style\
            .applymap(color_priority, subset=["priority_label"])\
            .applymap(color_visa, subset=["h1b_status", "j1_status"])

        selected_rows = st.dataframe(
            df[DISPLAY_COLS],
            use_container_width=True,
            hide_index=True,
            column_config={
                "apply_url": st.column_config.LinkColumn("Apply Link"),
                "priority_score": st.column_config.NumberColumn("Score", format="%.0f"),
                "posted_date": st.column_config.TextColumn("Posted Date"),
                "first_seen_at": st.column_config.DatetimeColumn("First Seen"),
            },
            on_select="rerun",
            selection_mode="multi-row",
        )

        col_e, col_c = st.columns([1, 1])
        with col_e:
            if st.button("📤 Export to CSV"):
                path = export_csv(jobs)
                st.success(f"Exported: {path}")
        with col_c:
            if st.button("📋 Export High Priority"):
                path = export_high_priority(jobs)
                st.success(f"Exported: {path}")

# ── Tab 2: Analytics ──────────────────────────────────────────────────────────
with tab2:
    st.subheader("Job Analytics")
    if df.empty:
        st.info("No data yet. Run a search first.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            if "state" in df.columns:
                state_counts = df["state"].value_counts().reset_index()
                state_counts.columns = ["State", "Count"]
                st.bar_chart(state_counts.set_index("State"))
                st.caption("Jobs by State")
        with c2:
            if "source_name" in df.columns:
                src_counts = df["source_name"].value_counts().reset_index()
                src_counts.columns = ["Source", "Count"]
                st.bar_chart(src_counts.set_index("Source").head(10))
                st.caption("Jobs by Source")

        c3, c4 = st.columns(2)
        with c3:
            if "h1b_status" in df.columns:
                h1b_counts = df["h1b_status"].value_counts().reset_index()
                h1b_counts.columns = ["H1B Status", "Count"]
                st.dataframe(h1b_counts, use_container_width=True, hide_index=True)
                st.caption("H1B Distribution")
        with c4:
            if "j1_status" in df.columns:
                j1_counts = df["j1_status"].value_counts().reset_index()
                j1_counts.columns = ["J1 Status", "Count"]
                st.dataframe(j1_counts, use_container_width=True, hide_index=True)
                st.caption("J1 Distribution")

        if "priority_label" in df.columns:
            priority_counts = df["priority_label"].value_counts().reset_index()
            priority_counts.columns = ["Priority", "Count"]
            st.bar_chart(priority_counts.set_index("Priority"))
            st.caption("Jobs by Priority")

# ── Tab 3: Email Drafts ───────────────────────────────────────────────────────
with tab3:
    st.subheader("Create Gmail Drafts")
    st.info("Drafts are created but NEVER auto-sent. Review in Gmail before sending.")

    recipient = st.text_input(
        "Recipient Email (hospital/recruiter)",
        placeholder="recruiting@hospitalname.com",
    )

    if not df.empty:
        st.markdown("**Select jobs to draft emails for:**")
        high_pri_jobs = [j for j in jobs if j.get("priority_label") in ("high", "medium")]
        if high_pri_jobs:
            st.markdown(f"*{len(high_pri_jobs)} high/medium priority jobs available*")
            if st.button("📧 Create Drafts for All High Priority Jobs"):
                if not recipient:
                    st.error("Enter a recipient email first.")
                else:
                    count = create_drafts_for_jobs(high_pri_jobs[:20], recipient)
                    st.success(f"Created {count} Gmail drafts. Check your Gmail Drafts folder.")
        else:
            st.info("No high priority jobs found. Run a search first.")
    else:
        st.info("No jobs loaded. Run a search first.")

    st.divider()
    st.subheader("📁 Manual CSV Import")
    st.markdown("""
    For PracticeLink, PracticeMatch, Indeed, LinkedIn exports:
    1. Export CSV from the job board
    2. Drop file in `data/manual_imports/`
    3. Click Run Job Search — importer runs automatically

    **Required columns:** `title`, `employer`, `state`
    **Optional:** `city`, `salary_text`, `visa_text`, `apply_url`, `contact_email`
    """)
    uploaded = st.file_uploader("Or upload CSV directly here:", type=["csv"])
    if uploaded:
        import_path = Path(__file__).parent.parent / "data" / "manual_imports" / uploaded.name
        import_path.write_bytes(uploaded.read())
        st.success(f"Saved to {import_path}. Run a search to import it.")
