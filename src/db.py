import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import (Boolean, Column, Date, DateTime, Float, Integer,
                        String, Text, create_engine, event)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    source_name = Column(String)
    source_type = Column(String)
    source_url = Column(Text)
    apply_url = Column(Text)
    title = Column(String)
    employer = Column(String)
    employer_type = Column(String, default="unknown")
    city = Column(String)
    state = Column(String(2))
    specialty = Column(String)
    job_type = Column(String, default="unknown")
    salary_text = Column(Text)
    salary_min = Column(Integer)
    salary_max = Column(Integer)
    dol_salary_min = Column(Integer)
    dol_salary_max = Column(Integer)
    dol_salary_year = Column(Integer)
    dol_case_count = Column(Integer)
    visa_text = Column(Text)
    h1b_status = Column(String, default="unknown")
    j1_status = Column(String, default="unknown")
    waiver_status = Column(String, default="unknown")
    contact_name = Column(String)
    contact_email = Column(String)
    contact_phone = Column(String)
    posted_date = Column(Date)
    posted_date_raw = Column(String)
    short_summary = Column(Text)
    full_text_hash = Column(String, unique=True, index=True)
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="new")
    duplicate_group_id = Column(String, index=True)
    priority_score = Column(Float, default=0.0)
    priority_label = Column(String, default="LOW")
    manual_review_required = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class Employer(Base):
    __tablename__ = "employers"

    id = Column(Integer, primary_key=True)
    employer_name = Column(String)
    website = Column(String)
    careers_url = Column(String)
    city = Column(String)
    state = Column(String(2))
    employer_type = Column(String)
    notes = Column(Text)


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id = Column(Integer, primary_key=True)
    selected_states = Column(Text)
    selected_terms = Column(Text)
    source_name = Column(String)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    jobs_found = Column(Integer, default=0)
    new_jobs = Column(Integer, default=0)
    duplicates_found = Column(Integer, default=0)
    errors = Column(Text)
    status = Column(String)


class GmailDraft(Base):
    __tablename__ = "gmail_drafts"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer)
    recipient_email = Column(String)
    subject = Column(String)
    draft_body = Column(Text)
    gmail_draft_id = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="created")


class ManualReview(Base):
    __tablename__ = "manual_reviews"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer)
    reason = Column(Text)
    reviewed = Column(Boolean, default=False)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class DolLcaCache(Base):
    __tablename__ = "dol_lca_cache"

    id = Column(Integer, primary_key=True)
    employer_name = Column(String, index=True)
    job_title = Column(String)
    state = Column(String(2))
    wage_min = Column(Integer)
    wage_max = Column(Integer)
    lca_year = Column(Integer)
    case_count = Column(Integer, default=1)
    fetched_at = Column(DateTime, default=datetime.utcnow)


def get_engine(db_path: str | None = None):
    path = db_path or os.getenv("DB_PATH", "data/jobs.db")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    event.listen(engine, "connect", lambda c, _: c.execute("PRAGMA journal_mode=WAL"))
    return engine


def init_db(db_path: str | None = None) -> sessionmaker:
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def get_session(db_path: str | None = None) -> Session:
    SessionLocal = init_db(db_path)
    return SessionLocal()
