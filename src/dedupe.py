import hashlib
import uuid
from datetime import datetime
from typing import Optional

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from src.db import Job
from src.models import RawJob


def make_hash(title: str, employer: str, city: str, state: str) -> str:
    key = f"{title.lower()}|{employer.lower()}|{(city or '').lower()}|{(state or '').lower()}"
    return hashlib.sha256(key.encode()).hexdigest()


def find_fuzzy_match(session: Session, title: str, employer: str, threshold: int = 88) -> Optional[Job]:
    candidates = (
        session.query(Job)
        .filter(Job.employer.ilike(f"%{employer[:20]}%"))
        .limit(50)
        .all()
    )
    query_str = f"{title} {employer}"
    for candidate in candidates:
        score = fuzz.token_sort_ratio(
            query_str,
            f"{candidate.title} {candidate.employer}"
        )
        if score >= threshold:
            return candidate
    return None


def upsert_job(session: Session, raw: RawJob, enriched: dict) -> tuple[Job, bool]:
    """
    Insert or update a job. Returns (job, is_new).
    enriched contains: salary_min, salary_max, salary_text,
    h1b_status, j1_status, waiver_status, visa_text,
    contact_name, contact_email, contact_phone,
    posted_date, priority_score, priority_label,
    dol_salary_min, dol_salary_max, dol_salary_year, dol_case_count
    """
    text_hash = make_hash(raw.title, raw.employer, raw.city or "", raw.state or "")

    existing = session.query(Job).filter_by(full_text_hash=text_hash).first()
    if existing:
        existing.last_seen_at = datetime.utcnow()
        existing.updated_at = datetime.utcnow()
        for k, v in enriched.items():
            if v is not None:
                setattr(existing, k, v)
        session.commit()
        return existing, False

    fuzzy_match = find_fuzzy_match(session, raw.title, raw.employer)
    group_id = fuzzy_match.duplicate_group_id if fuzzy_match else str(uuid.uuid4())

    job = Job(
        source_name=raw.source_name,
        source_type=raw.source_type,
        source_url=raw.source_url,
        apply_url=raw.apply_url,
        title=raw.title,
        employer=raw.employer,
        employer_type=raw.employer_type,
        city=raw.city,
        state=raw.state,
        specialty=raw.specialty,
        job_type=raw.job_type,
        short_summary=raw.short_summary,
        full_text_hash=text_hash,
        duplicate_group_id=group_id,
        first_seen_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow(),
        **{k: v for k, v in enriched.items() if v is not None},
    )
    session.add(job)
    session.commit()
    return job, True
