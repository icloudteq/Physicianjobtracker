"""
Fetches individual job detail pages to extract H1B/salary/contact info
from full job descriptions. Targets NC/SC jobs with unknown visa status.
"""
import time
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from src.contact_extractor import extract_contact
from src.db import Job, get_session
from src.dol_salary import lookup_salary
from src.logger import get_logger
from src.ranker import score_job
from src.models import RawJob
from src.salary_parser import parse_salary
from src.visa_classifier import classify_visa

log = get_logger("detail_enricher")

# Sources where detail pages are plain HTML (skip JS-heavy ATS)
_PLAIN_HTML_SOURCES = {
    "doccafe", "nejm", "jama", "hospital_recruiting",
    "health_ecareers", "practicematch", "practicelink",
}

_BLOCKED_SIGNALS = [
    "just a moment", "checking your browser", "cloudflare",
    "captcha", "access denied", "403 forbidden", "please verify",
    "sign in to continue", "login required",
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_CLIENT = httpx.Client(
    headers=_HEADERS,
    timeout=httpx.Timeout(connect=6.0, read=10.0, write=5.0, pool=5.0),
    follow_redirects=True,
)


def _fetch_detail_text(url: str) -> Optional[str]:
    """Fetch job detail page and return cleaned text."""
    try:
        resp = _CLIENT.get(url)
        resp.raise_for_status()
        html = resp.text
        if any(sig in html.lower() for sig in _BLOCKED_SIGNALS):
            return None
        soup = BeautifulSoup(html, "html.parser")
        # Remove nav/header/footer noise
        for tag in soup(["nav", "header", "footer", "script", "style", "aside"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
        return text[:8000]  # cap at 8k chars — full job description
    except Exception as e:
        log.debug(f"Detail fetch failed {url}: {e}")
        return None


def enrich_job_details(
    states: list[str] | None = None,
    limit: int = 200,
    delay: float = 0.4,
    priority_only: bool = False,
) -> dict:
    """
    Fetch detail pages for jobs with unknown visa/salary/contact status.

    Args:
        states: restrict to these state codes (default: NC, SC)
        limit: max jobs to process in one run
        delay: seconds between requests (be respectful)
        priority_only: if True, only process HIGH/MEDIUM jobs

    Returns:
        dict with counts: enriched, h1b_found, salary_found, contact_found
    """
    if states is None:
        states = ["NC", "SC"]

    session = get_session()
    try:
        query = session.query(Job).filter(
            Job.state.in_(states),
            Job.source_url.isnot(None),
            Job.source_name.in_(_PLAIN_HTML_SOURCES),
            Job.h1b_status == "unknown",
        )
        if priority_only:
            query = query.filter(Job.priority_label.in_(["HIGH", "MEDIUM"]))
        jobs = query.order_by(Job.priority_score.desc()).limit(limit).all()

        log.info(f"Detail enricher: {len(jobs)} jobs to process in {states}")

        enriched = h1b_found = salary_found = contact_found = 0

        for job in jobs:
            text = _fetch_detail_text(job.source_url)
            time.sleep(delay)

            if not text:
                continue

            # Re-classify with full text
            visa = classify_visa(text)
            salary_min, salary_max, salary_text = parse_salary(text)
            contact = extract_contact(text)

            # DOL match as H1B proxy (re-check if employer name now known)
            if job.employer and job.employer != "Unknown" and visa["h1b_status"] == "unknown":
                dol = lookup_salary(job.employer, job.state or "", session)
                if dol.get("dol_salary_min"):
                    visa["h1b_status"] = "possible"
                    visa["visa_text"] = f"DOL LCA data: {dol.get('dol_case_count','N/A')} H1B filings"

            changed = False

            if visa["h1b_status"] != "unknown":
                job.h1b_status = visa["h1b_status"]
                job.j1_status = visa["j1_status"]
                job.waiver_status = visa["waiver_status"]
                if visa["visa_text"]:
                    job.visa_text = visa["visa_text"]
                h1b_found += 1
                changed = True

            if salary_min and not job.salary_min:
                job.salary_min = salary_min
                job.salary_max = salary_max
                job.salary_text = salary_text
                salary_found += 1
                changed = True
            elif salary_max and not job.salary_max:
                job.salary_max = salary_max
                job.salary_text = salary_text
                salary_found += 1
                changed = True

            if contact["contact_email"] and not job.contact_email:
                job.contact_email = contact["contact_email"]
                contact_found += 1
                changed = True
            if contact["contact_phone"] and not job.contact_phone:
                job.contact_phone = contact["contact_phone"]
                contact_found += 1
                changed = True
            if contact["contact_name"] and not job.contact_name:
                job.contact_name = contact["contact_name"]
                changed = True

            if changed:
                # Re-score with updated data
                raw = RawJob(
                    source_name=job.source_name,
                    source_type=job.source_type,
                    source_url=job.source_url or "",
                    title=job.title,
                    employer=job.employer,
                    city=job.city or "",
                    state=job.state,
                    raw_text=job.short_summary or "",
                )
                enriched_data = {
                    "salary_min": job.salary_min,
                    "salary_max": job.salary_max,
                    "h1b_status": job.h1b_status,
                    "j1_status": job.j1_status,
                    "contact_email": job.contact_email,
                    "contact_name": job.contact_name,
                }
                score, label = score_job(raw, enriched_data)
                job.priority_score = score
                job.priority_label = label
                enriched += 1

        session.commit()
        log.info(
            f"Detail enrichment done: {enriched} updated, "
            f"H1B={h1b_found}, salary={salary_found}, contact={contact_found}"
        )
        return {
            "enriched": enriched,
            "h1b_found": h1b_found,
            "salary_found": salary_found,
            "contact_found": contact_found,
            "total_checked": len(jobs),
        }
    finally:
        session.close()


if __name__ == "__main__":
    import sys
    states = sys.argv[1:] or ["NC", "SC"]
    result = enrich_job_details(states=states, limit=300)
    print(f"Enriched {result['enriched']}/{result['total_checked']} jobs")
    print(f"  H1B found: {result['h1b_found']}")
    print(f"  Salary found: {result['salary_found']}")
    print(f"  Contact found: {result['contact_found']}")
