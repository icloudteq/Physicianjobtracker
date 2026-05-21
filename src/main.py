"""
Pipeline orchestrator. Can be called from Streamlit dashboard or CLI.
Usage: python -m src.main --states NC SC --run
"""
import argparse
import json
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
    from src.scrapers.csv_importer import import_all_from_dir
    from src.scrapers.doccafe import DocCafeScraper
    from src.scrapers.generic_hospital import GenericHospitalScraper
    from src.scrapers.health_ecareers import HealthECareersScraper
    from src.scrapers.hospital_recruiting import HospitalRecruitingScraper
    from src.scrapers.nejm import NEJMScraper
    return [
        DocCafeScraper(),
        NEJMScraper(),
        HealthECareersScraper(),
        HospitalRecruitingScraper(),
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
    scrapers = _get_scrapers()
    total_new = 0
    total_high = 0
    run_results = []

    # Run job board scrapers
    for scraper in scrapers:
        if not scraper.enabled:
            continue
        log_progress(f"Scraping {scraper.source_name}...")
        result = ScrapeRunResult(
            source_name=scraper.source_name,
            started_at=datetime.utcnow(),
            selected_states=states,
            selected_terms=terms,
        )
        try:
            raw_jobs = scraper.fetch(states, terms)
            result.jobs_found = len(raw_jobs)
            new_count = 0
            for raw in raw_jobs:
                enriched = _enrich(raw, session)
                _, is_new = upsert_job(session, raw, enriched)
                if is_new:
                    new_count += 1
                    if enriched.get("priority_label") == "HIGH":
                        total_high += 1
            result.new_jobs = new_count
            total_new += new_count
            log_progress(f"  {scraper.source_name}: {len(raw_jobs)} found, {new_count} new")
        except Exception as e:
            result.errors = str(e)
            result.status = "error"
            log.error(f"Scraper {scraper.source_name} failed: {e}")
        finally:
            result.finished_at = datetime.utcnow()
            result.status = result.status or "completed"
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
            run_results.append(result)

    # Scrape pre-curated hospital career pages
    from src.scrapers.generic_hospital import GenericHospitalScraper
    hosp_scraper = GenericHospitalScraper()
    employers = session.query(Employer).all()
    for emp in employers:
        if not emp.careers_url:
            continue
        emp_state = emp.state if emp.state != "ALL" else states[0]
        log_progress(f"Scraping {emp.employer_name}...")
        try:
            raw_jobs = hosp_scraper.scrape_employer(emp.employer_name, emp.careers_url, emp_state, terms)
            for raw in raw_jobs:
                enriched = _enrich(raw, session)
                _, is_new = upsert_job(session, raw, enriched)
                if is_new:
                    total_new += 1
                    if enriched.get("priority_label") == "HIGH":
                        total_high += 1
        except Exception as e:
            log.error(f"Hospital scrape failed for {emp.employer_name}: {e}")

    # CSV manual imports
    from src.scrapers.csv_importer import import_all_from_dir
    csv_jobs = import_all_from_dir()
    for raw in csv_jobs:
        enriched = _enrich(raw, session)
        _, is_new = upsert_job(session, raw, enriched)
        if is_new:
            total_new += 1

    # Export
    export_path = export_run(session)
    log_progress(f"Exported to {export_path}")

    session.close()

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
