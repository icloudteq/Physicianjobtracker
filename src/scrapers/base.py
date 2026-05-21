import time
import hashlib
import requests
from abc import ABC, abstractmethod
from typing import List
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
from src.models import Job
from src.logger import get_logger

log = get_logger(__name__)
_ua = UserAgent()


class BaseScraper(ABC):
    name: str = "base"
    source_type: str = "job_board"
    rate_limit: float = 3.0

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": _ua.random,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(5),
        retry=retry_if_exception_type(requests.RequestException),
    )
    def get(self, url: str, **kwargs) -> requests.Response:
        time.sleep(self.rate_limit)
        resp = self.session.get(url, timeout=20, **kwargs)
        if resp.status_code == 403:
            log.warning(f"{self.name}: 403 on {url} — skipping")
            raise PermissionError(f"403 blocked: {url}")
        if resp.status_code == 429:
            log.warning(f"{self.name}: 429 rate limited — waiting 30s")
            time.sleep(30)
            raise requests.RequestException("Rate limited")
        resp.raise_for_status()
        return resp

    @abstractmethod
    def scrape(self, state: str, terms: List[str]) -> List[Job]:
        """Scrape jobs for a state and specialty terms. Return list of Job objects."""
        ...

    def make_hash(self, title: str, employer: str, state: str, city: str = "") -> str:
        raw = f"{title.lower().strip()}|{employer.lower().strip()}|{state.lower()}|{city.lower()}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def safe_text(self, el) -> str:
        if el is None:
            return ""
        return el.get_text(strip=True)

    def extract_posted_date(self, item) -> str:
        """Try common HTML patterns for job posting dates. Returns raw text or empty string."""
        time_el = item.select_one("time[datetime]")
        if time_el:
            return time_el.get("datetime", "") or time_el.get_text(strip=True)
        for sel in (
            ".date-posted, .posted-date, .post-date, .listing-date, "
            ".date, .posted, .job-date, [class*='date-posted'], "
            "[class*='posted-date'], [class*='post-date']"
        ).split(", "):
            el = item.select_one(sel.strip())
            if el:
                text = el.get_text(strip=True)
                if text:
                    return text
        return ""
