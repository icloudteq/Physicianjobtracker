"""
Physician Job Intelligence Pipeline
Run: python -m src.main --states NC SC --terms "Internal Medicine Physician" "Hospitalist"
"""
import argparse
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
from typing import List

from src.db import init_db, upsert_job, log_scrape_run, finish_scrape_run, get_jobs
from src.dedupe import dedupe_batch
from src.visa_classifier import classify_all
from src.salary_parser import parse_salary
from src.ranker import score_job
from src.exporters import export_csv, export_high_priority, export_summary_report
from src.logger import get_logger
from src.scrapers.doccafe import DocCafeScraper
from src.scrapers.hospital_recruiting import HospitalRecruitingScraper
from src.scrapers.nejm import NEJMScraper
from src.scrapers.health_ecareers import HealthECareersScraper
from src.scrapers.jama_career import JAMACareerScraper
from src.scrapers.acp_career import ACPCareerScraper
from src.scrapers.workday import WorkdayScraper
from src.scrapers.icims import ICIMSScraper
from src.scrapers.generic_hospital import GenericHospitalScraper
from src.scrapers.csv_importer import import_all

log = get_logger(__name__)

DEFAULT_STATES = ["NC", "SC"]
DEFAULT_TERMS = [
    "Internal Medicine Physician", "Hospitalist", "Nocturnist",
    "Primary Care Physician", "Outpatient Internal Medicine",
]

SCRAPERS = [
    DocCafeScraper,
    HospitalRecruitingScraper,
    NEJMScraper,
    HealthECareersScraper,
    JAMACareerScraper,
    ACPCareerScraper,
    WorkdayScraper,
    ICIMSScraper,
    GenericHospitalScraper,
]


def run_pipeline(states: List[str], terms: List[str], skip_scrapers: List[str] = None) -> dict:
    init_db()
    skip_scrapers = skip_scrapers or []
    all_jobs = []
    total_new = 0
    total_dupes = 0
    errors = []

    log.info(f"Pipeline start | States: {states} | Terms: {terms}")

    for ScraperClass in SCRAPERS:
        scraper = ScraperClass()
        if scraper.name in skip_scrapers:
            log.info(f"Skipping {scraper.name}")
            continue
        for state in states:
            run_id = log_scrape_run(scraper.name, [state], terms)
            try:
                log.info(f"Scraping {scraper.name} for {state}...")
                jobs = scraper.scrape(state, terms)
                log.info(f"  → {len(jobs)} raw jobs from {scraper.name}/{state}")

                unique_jobs, dupe_count = dedupe_batch(jobs)
                total_dupes += dupe_count

                new_count = 0
                for job in unique_jobs:
                    visa = classify_all(job.visa_text + " " + job.short_summary)
                    job.h1b_status = visa["h1b_status"]
                    job.j1_status = visa["j1_status"]
                    job.waiver_status = visa["waiver_status"]

                    sal_min, sal_max, sal_text = parse_salary(job.salary_text + " " + job.short_summary)
                    if sal_min:
                        job.salary_min = sal_min
                        job.salary_max = sal_max
                        job.salary_text = job.salary_text or sal_text

                    score, label = score_job(job)
                    job.priority_score = score
                    job.priority_label = label

                    _, is_new = upsert_job(job)
                    if is_new:
                        new_count += 1
                        all_jobs.append(job)

                total_new += new_count
                finish_scrape_run(run_id, len(jobs), new_count, dupe_count, "", "done")
                log.info(f"  → {new_count} new saved from {scraper.name}/{state}")

            except Exception as e:
                err_msg = f"{scraper.name}/{state}: {e}"
                errors.append(err_msg)
                log.error(err_msg)
                finish_scrape_run(run_id, 0, 0, 0, err_msg, "error")

    csv_imports = import_all()
    for job in csv_imports:
        visa = classify_all(job.visa_text)
        job.h1b_status = visa["h1b_status"]
        job.j1_status = visa["j1_status"]
        job.waiver_status = visa["waiver_status"]
        sal_min, sal_max, sal_text = parse_salary(job.salary_text)
        if sal_min:
            job.salary_min = sal_min
            job.salary_max = sal_max
        score, label = score_job(job)
        job.priority_score = score
        job.priority_label = label
        _, is_new = upsert_job(job)
        if is_new:
            total_new += 1

    all_db_jobs = get_jobs(states=states, limit=2000)
    export_csv(all_db_jobs)
    export_high_priority(all_db_jobs)
    report = export_summary_report(all_db_jobs, states)

    print(report)
    log.info(f"Pipeline done | New: {total_new} | Dupes skipped: {total_dupes} | Errors: {len(errors)}")
    return {
        "total_new": total_new,
        "total_dupes": total_dupes,
        "total_in_db": len(all_db_jobs),
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(description="Physician Job Intelligence Pipeline")
    parser.add_argument("--states", nargs="+", default=DEFAULT_STATES, help="State codes e.g. NC SC TX")
    parser.add_argument("--terms", nargs="+", default=DEFAULT_TERMS, help="Specialty search terms")
    parser.add_argument("--skip", nargs="*", default=[], help="Scraper names to skip")
    args = parser.parse_args()
    run_pipeline(args.states, args.terms, args.skip)


if __name__ == "__main__":
    main()
