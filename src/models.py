import sqlite3
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class Job:
    source_name: str
    source_type: str
    source_url: str
    title: str
    employer: str
    state: str
    city: str = ""
    apply_url: str = ""
    specialty: str = ""
    job_type: str = ""
    salary_text: str = ""
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    visa_text: str = ""
    h1b_status: str = "unknown"
    j1_status: str = "unknown"
    waiver_status: str = "unknown"
    employer_type: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    short_summary: str = ""
    full_text_hash: str = ""
    priority_score: float = 0.0
    priority_label: str = "normal"
    manual_review_required: bool = False
    status: str = "new"
    id: Optional[int] = None
    duplicate_group_id: Optional[int] = None
    posted_date: Optional[str] = None
    first_seen_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_seen_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class Employer:
    employer_name: str
    website: str
    state: str
    city: str = ""
    careers_url: str = ""
    employer_type: str = ""
    notes: str = ""
    id: Optional[int] = None


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    source_type TEXT DEFAULT 'job_board',
    source_url TEXT,
    apply_url TEXT,
    title TEXT NOT NULL,
    employer TEXT NOT NULL,
    employer_type TEXT DEFAULT '',
    city TEXT DEFAULT '',
    state TEXT NOT NULL,
    specialty TEXT DEFAULT '',
    job_type TEXT DEFAULT '',
    salary_text TEXT DEFAULT '',
    salary_min REAL,
    salary_max REAL,
    visa_text TEXT DEFAULT '',
    h1b_status TEXT DEFAULT 'unknown',
    j1_status TEXT DEFAULT 'unknown',
    waiver_status TEXT DEFAULT 'unknown',
    contact_email TEXT DEFAULT '',
    contact_phone TEXT DEFAULT '',
    short_summary TEXT DEFAULT '',
    full_text_hash TEXT DEFAULT '',
    posted_date TEXT,
    first_seen_at TEXT,
    last_seen_at TEXT,
    status TEXT DEFAULT 'new',
    duplicate_group_id INTEGER,
    priority_score REAL DEFAULT 0,
    priority_label TEXT DEFAULT 'normal',
    manual_review_required INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS employers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employer_name TEXT NOT NULL,
    website TEXT,
    careers_url TEXT,
    city TEXT,
    state TEXT,
    employer_type TEXT,
    notes TEXT,
    UNIQUE(employer_name, state)
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    selected_states TEXT,
    selected_terms TEXT,
    source_name TEXT,
    started_at TEXT,
    finished_at TEXT,
    jobs_found INTEGER DEFAULT 0,
    new_jobs INTEGER DEFAULT 0,
    duplicates_found INTEGER DEFAULT 0,
    errors TEXT DEFAULT '',
    status TEXT DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS gmail_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER REFERENCES jobs(id),
    recipient_email TEXT,
    subject TEXT,
    draft_body TEXT,
    gmail_draft_id TEXT,
    created_at TEXT,
    status TEXT DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS manual_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER REFERENCES jobs(id),
    reason TEXT,
    reviewed INTEGER DEFAULT 0,
    notes TEXT DEFAULT '',
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(state);
CREATE INDEX IF NOT EXISTS idx_jobs_h1b ON jobs(h1b_status);
CREATE INDEX IF NOT EXISTS idx_jobs_j1 ON jobs(j1_status);
CREATE INDEX IF NOT EXISTS idx_jobs_priority ON jobs(priority_score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_hash ON jobs(full_text_hash);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
"""
