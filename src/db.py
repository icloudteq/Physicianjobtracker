import sqlite3
import hashlib
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from typing import Tuple
from src.models import Job, Employer, SCHEMA
from src.logger import get_logger

log = get_logger(__name__)
DB_PATH = Path(__file__).parent.parent / "data" / "jobs.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        existing = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        if "posted_date" not in existing:
            conn.execute("ALTER TABLE jobs ADD COLUMN posted_date TEXT")
    log.info(f"Database initialized at {DB_PATH}")


def job_exists(conn: sqlite3.Connection, full_text_hash: str) -> bool:
    row = conn.execute(
        "SELECT id FROM jobs WHERE full_text_hash = ?", (full_text_hash,)
    ).fetchone()
    return row is not None


def upsert_job(job: Job) -> Tuple[int, bool]:
    """Insert new job or update last_seen_at for existing. Returns (id, is_new)."""
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        if job.full_text_hash and job_exists(conn, job.full_text_hash):
            conn.execute(
                "UPDATE jobs SET last_seen_at=?, updated_at=? WHERE full_text_hash=?",
                (now, now, job.full_text_hash),
            )
            row = conn.execute(
                "SELECT id FROM jobs WHERE full_text_hash=?", (job.full_text_hash,)
            ).fetchone()
            return row["id"], False

        cursor = conn.execute(
            """INSERT INTO jobs (
                source_name, source_type, source_url, apply_url, title, employer,
                employer_type, city, state, specialty, job_type, salary_text,
                salary_min, salary_max, visa_text, h1b_status, j1_status,
                waiver_status, contact_email, contact_phone, short_summary,
                full_text_hash, posted_date, first_seen_at, last_seen_at, status,
                priority_score, priority_label, manual_review_required,
                created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                job.source_name, job.source_type, job.source_url, job.apply_url,
                job.title, job.employer, job.employer_type, job.city, job.state,
                job.specialty, job.job_type, job.salary_text, job.salary_min,
                job.salary_max, job.visa_text, job.h1b_status, job.j1_status,
                job.waiver_status, job.contact_email, job.contact_phone,
                job.short_summary, job.full_text_hash, job.posted_date, now, now,
                job.status, job.priority_score, job.priority_label,
                int(job.manual_review_required), now, now,
            ),
        )
        return cursor.lastrowid, True


def get_jobs(
    states: Optional[List[str]] = None,
    h1b_only: bool = False,
    j1_only: bool = False,
    min_priority: float = 0,
    limit: int = 500,
    offset: int = 0,
) -> List[dict]:
    filters = ["1=1"]
    params = []
    if states:
        placeholders = ",".join("?" * len(states))
        filters.append(f"state IN ({placeholders})")
        params.extend(states)
    if h1b_only:
        filters.append("h1b_status IN ('confirmed','possible')")
    if j1_only:
        filters.append("j1_status IN ('confirmed','possible')")
    if min_priority > 0:
        filters.append("priority_score >= ?")
        params.append(min_priority)

    where = " AND ".join(filters)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM jobs WHERE {where} ORDER BY priority_score DESC, first_seen_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return [dict(r) for r in rows]


def get_job_count(states: Optional[List[str]] = None) -> int:
    filters = ["1=1"]
    params = []
    if states:
        placeholders = ",".join("?" * len(states))
        filters.append(f"state IN ({placeholders})")
        params.extend(states)
    where = " AND ".join(filters)
    with get_conn() as conn:
        row = conn.execute(f"SELECT COUNT(*) as n FROM jobs WHERE {where}", params).fetchone()
    return row["n"]


def get_stats() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) as n FROM jobs").fetchone()["n"]
        by_state = conn.execute(
            "SELECT state, COUNT(*) as n FROM jobs GROUP BY state ORDER BY n DESC"
        ).fetchall()
        h1b = conn.execute(
            "SELECT h1b_status, COUNT(*) as n FROM jobs GROUP BY h1b_status"
        ).fetchall()
        j1 = conn.execute(
            "SELECT j1_status, COUNT(*) as n FROM jobs GROUP BY j1_status"
        ).fetchall()
        sources = conn.execute(
            "SELECT source_name, COUNT(*) as n FROM jobs GROUP BY source_name ORDER BY n DESC"
        ).fetchall()
    return {
        "total": total,
        "by_state": [dict(r) for r in by_state],
        "h1b": [dict(r) for r in h1b],
        "j1": [dict(r) for r in j1],
        "sources": [dict(r) for r in sources],
    }


def log_scrape_run(source_name: str, states: List[str], terms: List[str]) -> int:
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO scrape_runs (selected_states, selected_terms, source_name, started_at, status) VALUES (?,?,?,?,?)",
            (",".join(states), ",".join(terms), source_name, now, "running"),
        )
        return cur.lastrowid


def finish_scrape_run(run_id: int, jobs_found: int, new_jobs: int, dupes: int, errors: str, status: str = "done"):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            "UPDATE scrape_runs SET finished_at=?, jobs_found=?, new_jobs=?, duplicates_found=?, errors=?, status=? WHERE id=?",
            (now, jobs_found, new_jobs, dupes, errors, status, run_id),
        )


def make_hash(title: str, employer: str, state: str, city: str = "") -> str:
    raw = f"{title.lower().strip()}|{employer.lower().strip()}|{state.lower()}|{city.lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def save_gmail_draft(job_id: int, recipient: str, subject: str, body: str, gmail_id: str = "") -> int:
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO gmail_drafts (job_id, recipient_email, subject, draft_body, gmail_draft_id, created_at, status) VALUES (?,?,?,?,?,?,?)",
            (job_id, recipient, subject, body, gmail_id, now, "created"),
        )
        return cur.lastrowid
