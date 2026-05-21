"""
Pipeline orchestrator. Can be called from Streamlit dashboard or CLI.
Usage: python -m src.main --states NC SC --run
"""
import argparse
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Callable

import yaml

from src.contact_extractor import extract_contact
from src.date_parser import parse_posted_date
from src.db import Employer, Job, ScrapeRun, get_session
from src.dedupe import upsert_job
from src.dol_salary import ensure_lca_loaded, lookup_salary
from src.exporters import export_run
from src.logger import get_logger
from src.models import RawJob, ScrapeRunResult
from src.notifier import notify
from src.ranker import score_job
from src.salary_parser import parse_salary
from src.visa_classifier import classify_visa

log = get_logger("main")

# Scrapers registry
def _get_scrapers():
    from src.scrapers.doccafe import DocCafeScraper
    from src.scrapers.health_ecareers import HealthECareersScraper
    from src.scrapers.hospital_recruiting import HospitalRecruitingScraper
    from src.scrapers.icims import IcimsScraper
    from src.scrapers.jama import JAMACareerScraper
    from src.scrapers.nejm import NEJMScraper
    from src.scrapers.practicematch import PracticeMatchScraper
    from src.scrapers.practicelink import PracticeLinkScraper
    from src.scrapers.taleo import TaleoScraper
    from src.scrapers.workday import WorkdayScraper
    return [
        DocCafeScraper(),
        NEJMScraper(),
        JAMACareerScraper(),
        HealthECareersScraper(),
        HospitalRecruitingScraper(),
        WorkdayScraper(),
        IcimsScraper(),
        TaleoScraper(),
        PracticeMatchScraper(),
        PracticeLinkScraper(),
    ]


def _load_config():
    with open("config/states.yaml") as f:
        states_cfg = yaml.safe_load(f)
    with open("config/search_terms.yaml") as f:
        terms_cfg = yaml.safe_load(f)
    with open("config/sources.yaml") as f:
        sources_cfg = yaml.safe_load(f)
    return states_cfg, terms_cfg, sources_cfg


def _flatten_terms(terms_cfg: dict, selected: list[str] | None = None) -> list[str]:
    all_terms = []
    for group in terms_cfg.get("specialty_terms", {}).values():
        all_terms.extend(group)
    if selected:
        return [t for t in all_terms if any(s.lower() in t.lower() for s in selected)]
    return all_terms


def _enrich(raw: RawJob, session) -> dict:
    text = raw.raw_text or ""
    salary_min, salary_max, salary_text = parse_salary(raw.salary_text or text)
    visa_data = classify_visa(raw.visa_text or text)
    contact_data = extract_contact(text)
    posted_date = parse_posted_date(raw.posted_date_raw or text)
    dol_data = lookup_salary(raw.employer, raw.state or "", session)

    # DOL LCA match = employer has filed H1B petitions = treat as H1B possible
    if dol_data.get("dol_salary_min") and visa_data.get("h1b_status") == "unknown":
        visa_data["h1b_status"] = "possible"
        visa_data["visa_text"] = f"DOL LCA data: {dol_data.get('dol_case_count', 'N/A')} H1B filings ({dol_data.get('dol_salary_year', '')})"

    enriched = {
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_text": salary_text or raw.salary_text,
        "posted_date": posted_date,
        "posted_date_raw": raw.posted_date_raw,
        **visa_data,
        **contact_data,
        **dol_data,
    }

    score, label = score_job(raw, enriched)
    enriched["priority_score"] = score
    enriched["priority_label"] = label
    return enriched


def run_pipeline(
    states: list[str] | None = None,
    terms: list[str] | None = None,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    def log_progress(msg: str):
        log.info(msg)
        if progress_cb:
            progress_cb(msg)

    states_cfg, terms_cfg, sources_cfg = _load_config()

    if not states:
        states = [k for k, v in states_cfg["states"].items() if v.get("search_enabled")]
    if not terms:
        terms = _flatten_terms(terms_cfg)

    log_progress(f"Starting pipeline: {len(states)} states, {len(terms)} terms")

    # Ensure DOL salary data is loaded (one-time download)
    log_progress("Checking DOL salary cache...")
    ensure_lca_loaded()

    session = get_session()
    db_lock = threading.Lock()
    scrapers = _get_scrapers()
    total_new = 0
    total_high = 0
    run_results = []

    def _run_one_scraper(scraper) -> ScrapeRunResult:
        result = ScrapeRunResult(
            source_name=scraper.source_name,
            started_at=datetime.utcnow(),
            selected_states=states,
            selected_terms=terms,
        )
        try:
            log_progress(f"Scraping {scraper.source_name}...")
            raw_jobs = scraper.fetch(states, terms)
            result.jobs_found = len(raw_jobs)
            new_count = 0
            with db_lock:
                for raw in raw_jobs:
                    enriched = _enrich(raw, session)
                    _, is_new = upsert_job(session, raw, enriched)
                    if is_new:
                        new_count += 1
                        if enriched.get("priority_label") == "HIGH":
                            result.jobs_found  # counted below
            result.new_jobs = new_count
            log_progress(f"  {scraper.source_name}: {len(raw_jobs)} found, {new_count} new")
        except Exception as e:
            result.errors = str(e)
            result.status = "error"
            log.error(f"Scraper {scraper.source_name} failed: {e}")
        finally:
            result.finished_at = datetime.utcnow()
            result.status = result.status or "completed"
        return result

    # Run all scrapers in parallel
    active = [s for s in scrapers if s.enabled]
    log_progress(f"Running {len(active)} scrapers in parallel…")
    with ThreadPoolExecutor(max_workers=len(active)) as pool:
        futures = {pool.submit(_run_one_scraper, s): s for s in active}
        for future in as_completed(futures):
            result = future.result()
            total_new += result.new_jobs
            # count HIGH from DB after all inserts
            run_results.append(result)
            with db_lock:
                run_record = ScrapeRun(
                    source_name=result.source_name,
                    selected_states=json.dumps(result.selected_states),
                    selected_terms=json.dumps(result.selected_terms),
                    started_at=result.started_at,
                    finished_at=result.finished_at,
                    jobs_found=result.jobs_found,
                    new_jobs=result.new_jobs,
                    errors=result.errors,
                    status=result.status,
                )
                session.add(run_record)
                session.commit()

    # Count HIGH priority after all scrapers done
    from src.db import Job
    total_high = session.query(Job).filter_by(priority_label="HIGH").count()

    # Scrape pre-curated hospital career pages — also in parallel
    from src.scrapers.generic_hospital import GenericHospitalScraper
    hosp_scraper = GenericHospitalScraper()
    employers = session.query(Employer).all()
    active_employers = [e for e in employers if e.careers_url]

    def _scrape_employer(emp) -> int:
        emp_state = emp.state if emp.state != "ALL" else (states[0] if states else "NC")
        try:
            raw_jobs = hosp_scraper.scrape_employer(emp.employer_name, emp.careers_url, emp_state, terms)
            new_count = 0
            with db_lock:
                for raw in raw_jobs:
                    enriched = _enrich(raw, session)
                    _, is_new = upsert_job(session, raw, enriched)
                    if is_new:
                        new_count += 1
            return new_count
        except Exception as e:
            log.error(f"Hospital scrape failed for {emp.employer_name}: {e}")
            return 0

    if active_employers:
        log_progress(f"Scraping {len(active_employers)} hospital career pages in parallel…")
        with ThreadPoolExecutor(max_workers=min(len(active_employers), 16)) as pool:
            emp_futures = [pool.submit(_scrape_employer, emp) for emp in active_employers]
            for f in as_completed(emp_futures):
                total_new += f.result()

    # CSV manual imports
    from src.scrapers.csv_importer import import_all_from_dir
    csv_jobs = import_all_from_dir()
    for raw in csv_jobs:
        enriched = _enrich(raw, session)
        _, is_new = upsert_job(session, raw, enriched)
        if is_new:
            total_new += 1

    # Detail-enrich NC/SC jobs: fetch individual pages for H1B/salary/contact
    from src.detail_enricher import enrich_job_details
    nc_sc_states = [s for s in states if s.upper() in ("NC", "SC")]
    if nc_sc_states:
        log_progress("Detail-enriching NC/SC jobs for H1B/salary/contact…")
        detail_result = enrich_job_details(states=nc_sc_states, limit=150)
        log_progress(
            f"  Detail enrichment: {detail_result['enriched']} updated "
            f"(H1B={detail_result['h1b_found']}, salary={detail_result['salary_found']}, "
            f"contact={detail_result['contact_found']})"
        )

    # Export
    export_path = export_run(session)
    log_progress(f"Exported to {export_path}")

    session.close()

    # Refresh HIGH count after detail enrichment
    session2 = get_session()
    total_high = session2.query(Job).filter_by(priority_label="HIGH").count()
    session2.close()

    notify(total_new, total_high)
    log_progress(f"Pipeline complete. {total_new} new jobs ({total_high} HIGH priority)")

    return {
        "total_new": total_new,
        "total_high": total_high,
        "export_path": export_path,
        "sources": [r.model_dump() for r in run_results],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Physician Job Tracker Pipeline")
    parser.add_argument("--states", nargs="+", help="State codes e.g. NC SC TX")
    parser.add_argument("--run", action="store_true", help="Run the pipeline")
    args = parser.parse_args()

    if args.run:
        result = run_pipeline(states=args.states)
        print(f"\nDone: {result['total_new']} new jobs, {result['total_high']} HIGH priority")
        print(f"Exported to: {result['export_path']}")
