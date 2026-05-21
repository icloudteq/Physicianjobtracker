from rapidfuzz import fuzz
from typing import List
from typing import Tuple
from src.models import Job
from src.logger import get_logger

log = get_logger(__name__)
DUPE_THRESHOLD = 88


def is_duplicate(a: Job, b: Job) -> bool:
    if a.state != b.state:
        return False
    title_score = fuzz.token_sort_ratio(a.title.lower(), b.title.lower())
    employer_score = fuzz.token_sort_ratio(a.employer.lower(), b.employer.lower())
    if title_score >= DUPE_THRESHOLD and employer_score >= DUPE_THRESHOLD:
        return True
    city_match = not a.city or not b.city or a.city.lower() == b.city.lower()
    if title_score >= 95 and city_match:
        return True
    return False


def dedupe_batch(jobs: List[Job]) -> Tuple[List[Job], int]:
    """Remove duplicates from a list, return (unique_jobs, dupe_count)."""
    unique = []
    dupe_count = 0
    for job in jobs:
        if not any(is_duplicate(job, u) for u in unique):
            unique.append(job)
        else:
            dupe_count += 1
            log.debug(f"Dupe skipped: {job.title} @ {job.employer}")
    return unique, dupe_count
