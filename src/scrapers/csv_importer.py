"""
Manual CSV importer for PracticeLink, PracticeMatch, Indeed, LinkedIn, etc.
Drop CSV files into data/manual_imports/ and run this.
"""
import csv
import hashlib
from pathlib import Path
from typing import List
from src.models import Job
from src.logger import get_logger

log = get_logger(__name__)

IMPORT_DIR = Path(__file__).parent.parent.parent / "data" / "manual_imports"

COLUMN_MAP = {
    "title": ["title", "job title", "position", "job_title"],
    "employer": ["employer", "company", "facility", "organization", "hospital"],
    "state": ["state", "st"],
    "city": ["city", "location"],
    "salary_text": ["salary", "compensation", "pay", "salary_text"],
    "visa_text": ["visa", "visa_text", "sponsorship", "h1b", "j1"],
    "apply_url": ["apply_url", "url", "link", "apply link", "job url"],
    "source_url": ["source_url", "source", "source link"],
    "contact_email": ["contact_email", "email", "recruiter email"],
    "contact_phone": ["contact_phone", "phone"],
}


def _resolve_col(headers: List[str], field: str) -> str:
    headers_lower = [h.lower().strip() for h in headers]
    for alias in COLUMN_MAP.get(field, [field]):
        if alias.lower() in headers_lower:
            return headers[headers_lower.index(alias.lower())]
    return ""


def import_csv(filepath: Path, source_name: str = "") -> List[Job]:
    jobs = []
    if not source_name:
        source_name = filepath.stem.replace("_", " ").title()

    try:
        with open(filepath, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            col = {field: _resolve_col(list(headers), field) for field in COLUMN_MAP}

            for row in reader:
                title = row.get(col["title"], "").strip()
                employer = row.get(col["employer"], "").strip()
                state = row.get(col["state"], "").strip().upper()
                city = row.get(col["city"], "").strip()

                if not title or not state:
                    continue

                apply_url = row.get(col["apply_url"], "").strip()
                source_url = row.get(col["source_url"], apply_url).strip()
                salary_text = row.get(col["salary_text"], "").strip()
                visa_text = row.get(col["visa_text"], "").strip()
                contact_email = row.get(col["contact_email"], "").strip()
                contact_phone = row.get(col["contact_phone"], "").strip()

                raw = f"{title.lower()}|{employer.lower()}|{state.lower()}|{city.lower()}"
                h = hashlib.sha256(raw.encode()).hexdigest()

                jobs.append(Job(
                    source_name=source_name,
                    source_type="manual_import",
                    source_url=source_url,
                    apply_url=apply_url,
                    title=title,
                    employer=employer or "Unknown",
                    city=city,
                    state=state,
                    salary_text=salary_text,
                    visa_text=visa_text,
                    contact_email=contact_email,
                    contact_phone=contact_phone,
                    short_summary=f"Manual import: {title} at {employer}",
                    full_text_hash=h,
                ))
    except Exception as e:
        log.error(f"CSV import error {filepath}: {e}")
    log.info(f"CSV import: {filepath.name} → {len(jobs)} jobs")
    return jobs


def import_all() -> List[Job]:
    jobs = []
    IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    for csv_file in IMPORT_DIR.glob("*.csv"):
        jobs.extend(import_csv(csv_file))
    return jobs
