import os
from datetime import datetime
from pathlib import Path

import pandas as pd
from jinja2 import Template
from sqlalchemy.orm import Session

from src.db import Job, ScrapeRun
from src.logger import get_logger

log = get_logger("exporters")

_MASTER_COLS = [
    "id", "title", "employer", "employer_type", "city", "state", "specialty",
    "salary_text", "salary_min", "salary_max",
    "dol_salary_min", "dol_salary_max", "dol_salary_year", "dol_case_count",
    "contact_name", "contact_email", "contact_phone",
    "h1b_status", "j1_status", "waiver_status",
    "posted_date", "priority_label", "priority_score",
    "source_name", "source_url", "status", "first_seen_at",
]

_SUMMARY_TEMPLATE = """
Physician Job Tracker — Daily Summary
Date: {{ date }}
=======================================
Total new jobs found: {{ total_new }}
HIGH priority: {{ high }}
MEDIUM priority: {{ medium }}
LOW priority: {{ low }}

States with most jobs:
{% for state, count in top_states %}  {{ state }}: {{ count }}{% endfor %}

H1B confirmed jobs: {{ h1b_confirmed }}
J1 confirmed jobs: {{ j1_confirmed }}
Jobs with salary posted: {{ has_salary }}
Jobs with contact info: {{ has_contact }}

Sources run:
{% for s in sources %}  {{ s.source_name }}: {{ s.new_jobs }} new / {{ s.jobs_found }} found / {{ s.errors or 'no errors' }}{% endfor %}
"""


def export_run(session: Session, run_date: str | None = None) -> str:
    today = run_date or datetime.utcnow().strftime("%Y-%m-%d")
    export_dir = Path(os.getenv("EXPORT_DIR", "data/exports")) / today
    export_dir.mkdir(parents=True, exist_ok=True)

    jobs = session.query(Job).filter(
        Job.first_seen_at >= f"{today} 00:00:00"
    ).all()

    if not jobs:
        log.info("No new jobs to export today")
        return str(export_dir)

    rows = []
    for j in jobs:
        row = {col: getattr(j, col, None) for col in _MASTER_COLS}
        rows.append(row)

    df = pd.DataFrame(rows)

    master_path = export_dir / "master_jobs.csv"
    df.to_csv(master_path, index=False)
    log.info(f"Exported {len(df)} jobs → {master_path}")

    high_df = df[df["priority_label"] == "HIGH"]
    if not high_df.empty:
        high_path = export_dir / "jobs_high_priority.csv"
        high_df.to_csv(high_path, index=False)

    _write_summary(session, df, export_dir, today)
    return str(export_dir)


def _write_summary(session: Session, df: pd.DataFrame, export_dir: Path, today: str) -> None:
    sources = session.query(ScrapeRun).filter(
        ScrapeRun.started_at >= f"{today} 00:00:00"
    ).all()

    from collections import Counter
    state_counts = Counter(df["state"].dropna())
    top_states = state_counts.most_common(5)

    ctx = {
        "date": today,
        "total_new": len(df),
        "high": len(df[df["priority_label"] == "HIGH"]),
        "medium": len(df[df["priority_label"] == "MEDIUM"]),
        "low": len(df[df["priority_label"] == "LOW"]),
        "top_states": top_states,
        "h1b_confirmed": len(df[df["h1b_status"] == "confirmed"]),
        "j1_confirmed": len(df[df["j1_status"] == "confirmed"]),
        "has_salary": len(df[df["salary_min"].notna()]),
        "has_contact": len(df[df["contact_email"].notna()]),
        "sources": sources,
    }

    summary = Template(_SUMMARY_TEMPLATE).render(**ctx)
    (export_dir / "daily_summary.txt").write_text(summary, encoding="utf-8")
