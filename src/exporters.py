import csv
import json
from pathlib import Path
from datetime import datetime
from typing import List
import pandas as pd
from src.logger import get_logger

log = get_logger(__name__)
EXPORT_DIR = Path(__file__).parent.parent / "data" / "exports"


def _today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def export_csv(jobs: List[dict], filename: str = "") -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    if not filename:
        filename = f"physician_jobs_{_today()}.csv"
    path = EXPORT_DIR / filename

    fields = [
        "id", "title", "employer", "city", "state", "source_name",
        "salary_text", "salary_min", "salary_max",
        "h1b_status", "j1_status", "waiver_status",
        "priority_score", "priority_label",
        "apply_url", "source_url", "first_seen_at",
    ]
    df = pd.DataFrame(jobs)
    for f in fields:
        if f not in df.columns:
            df[f] = ""
    df[fields].to_csv(path, index=False)
    log.info(f"CSV export: {path} ({len(jobs)} jobs)")
    return path


def export_high_priority(jobs: List[dict]) -> Path:
    high = [j for j in jobs if j.get("priority_label") in ("high", "medium")]
    return export_csv(high, f"high_priority_jobs_{_today()}.csv")


def export_summary_report(jobs: List[dict], states: List[str]) -> str:
    total = len(jobs)
    h1b_conf = sum(1 for j in jobs if j.get("h1b_status") == "confirmed")
    h1b_poss = sum(1 for j in jobs if j.get("h1b_status") == "possible")
    j1_conf = sum(1 for j in jobs if j.get("j1_status") == "confirmed")
    j1_poss = sum(1 for j in jobs if j.get("j1_status") == "possible")
    high_pri = sum(1 for j in jobs if j.get("priority_label") == "high")
    medium_pri = sum(1 for j in jobs if j.get("priority_label") == "medium")
    with_salary = sum(1 for j in jobs if j.get("salary_text") or j.get("salary_min"))

    by_state = {}
    for j in jobs:
        s = j.get("state", "Unknown")
        by_state[s] = by_state.get(s, 0) + 1

    by_source = {}
    for j in jobs:
        s = j.get("source_name", "Unknown")
        by_source[s] = by_source.get(s, 0) + 1

    report = f"""
═══════════════════════════════════════════════════
  PHYSICIAN JOB INTELLIGENCE — DAILY REPORT
  {_today()} | States: {', '.join(states)}
═══════════════════════════════════════════════════

TOTAL JOBS: {total}
  ├─ High Priority: {high_pri}
  ├─ Medium Priority: {medium_pri}
  ├─ With Salary Posted: {with_salary}
  ├─ H1B Confirmed: {h1b_conf}
  ├─ H1B Possible: {h1b_poss}
  ├─ J1 Confirmed: {j1_conf}
  └─ J1 Possible: {j1_poss}

BY STATE:
{chr(10).join(f'  {s}: {n}' for s, n in sorted(by_state.items(), key=lambda x: -x[1]))}

BY SOURCE:
{chr(10).join(f'  {s}: {n}' for s, n in sorted(by_source.items(), key=lambda x: -x[1]))}

═══════════════════════════════════════════════════
TOP 10 HIGH PRIORITY JOBS:
"""
    top = sorted(jobs, key=lambda j: j.get("priority_score", 0), reverse=True)[:10]
    for i, j in enumerate(top, 1):
        report += f"""
  {i}. {j.get('title', '')}
     {j.get('employer', '')} — {j.get('city', '')}, {j.get('state', '')}
     H1B: {j.get('h1b_status','?')} | J1: {j.get('j1_status','?')} | Score: {j.get('priority_score', 0)}
     Apply: {j.get('apply_url', j.get('source_url', ''))}
"""

    path = EXPORT_DIR / f"daily_summary_{_today()}.txt"
    path.write_text(report, encoding="utf-8")
    log.info(f"Summary report: {path}")
    return report
