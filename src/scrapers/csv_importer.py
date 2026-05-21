import csv
import os
from pathlib import Path

from src.logger import get_logger
from src.models import RawJob

log = get_logger("csv_importer")

REQUIRED_COLS = {"title", "employer"}
OPTIONAL_COLS = {
    "city", "state", "source_url", "apply_url", "salary_text",
    "visa_text", "contact_name", "contact_email", "contact_phone",
    "posted_date_raw", "short_summary", "employer_type",
}


def import_csv(file_path: str, source_name: str = "csv_import") -> list[RawJob]:
    path = Path(file_path)
    if not path.exists():
        log.error(f"CSV file not found: {file_path}")
        return []

    jobs = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = {h.lower().strip() for h in (reader.fieldnames or [])}

        if not REQUIRED_COLS.issubset(headers):
            log.error(f"CSV missing required columns {REQUIRED_COLS}, got {headers}")
            return []

        for row in reader:
            clean = {k.lower().strip(): v.strip() for k, v in row.items() if v}
            title = clean.get("title", "")
            employer = clean.get("employer", "")
            if not title or not employer:
                continue

            jobs.append(RawJob(
                source_name=source_name,
                source_type="csv_import",
                source_url=clean.get("source_url", ""),
                apply_url=clean.get("apply_url"),
                title=title,
                employer=employer,
                employer_type=clean.get("employer_type", "unknown"),
                city=clean.get("city"),
                state=clean.get("state"),
                salary_text=clean.get("salary_text"),
                visa_text=clean.get("visa_text"),
                contact_name=clean.get("contact_name"),
                contact_email=clean.get("contact_email"),
                contact_phone=clean.get("contact_phone"),
                posted_date_raw=clean.get("posted_date_raw"),
                short_summary=clean.get("short_summary", "")[:400],
                raw_text=clean.get("short_summary", ""),
            ))

    log.info(f"Imported {len(jobs)} jobs from {file_path}")
    return jobs


def import_all_from_dir(directory: str = "data/manual_imports") -> list[RawJob]:
    jobs = []
    for f in Path(directory).glob("*.csv"):
        jobs.extend(import_csv(str(f), source_name=f.stem))
    return jobs
