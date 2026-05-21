"""
Generic hospital career page scraper.
Handles custom hospital career pages that don't use a standard ATS.
Falls back to keyword-based link detection if selectors don't match.
"""
import time
import hashlib
import requests
from bs4 import BeautifulSoup
from typing import List, Optional
from fake_useragent import UserAgent
from src.models import Job
from src.logger import get_logger

log = get_logger(__name__)
_ua = UserAgent()

PHYSICIAN_KEYWORDS = [
    "internal medicine", "hospitalist", "nocturnist", "primary care",
    "internist", "im physician", "general internist", "physician",
]

JOB_SELECTORS = [
    ".job-card", ".job-listing", ".job-result", ".position-item",
    "li.job", "article.job", "[class*='job-card']", "[class*='JobRow']",
    ".career-listing", ".opening", ".position", "[data-job]",
    "tr.job", ".search-result-item",
]

TITLE_SELECTORS = [
    "h2", "h3", "h4", ".job-title", ".position-title", ".title",
    "a[href*='job']", "a[href*='position']", "a[href*='career']",
    "[class*='JobTitle']", "[data-automation-id*='jobTitle']",
]

LOCATION_SELECTORS = [
    ".location", ".city", "[class*='location']", "[class*='Location']",
    ".job-location", ".city-state",
]

SALARY_SELECTORS = [
    ".salary", ".compensation", "[class*='salary']", "[class*='Salary']",
]


class GenericHospitalScraper:
    name = "Hospital (Generic)"
    source_type = "direct_employer"
    rate_limit = 4.0

    def _get(self, url: str) -> Optional[requests.Response]:
        try:
            time.sleep(self.rate_limit)
            s = requests.Session()
            s.headers.update({"User-Agent": _ua.random})
            resp = s.get(url, timeout=25, allow_redirects=True)
            if resp.status_code == 403:
                log.warning(f"GenericHospital: 403 on {url}")
                return None
            if resp.status_code == 429:
                log.warning(f"GenericHospital: rate limited on {url}")
                return None
            resp.raise_for_status()
            return resp
        except Exception as e:
            log.warning(f"GenericHospital fetch error {url}: {e}")
            return None

    def _safe_text(self, el) -> str:
        return el.get_text(strip=True) if el else ""

    def _extract_jobs(self, soup: BeautifulSoup, source_url: str, employer_name: str, state: str) -> List[Job]:
        jobs = []
        listings = []
        for sel in JOB_SELECTORS:
            listings = soup.select(sel)
            if listings:
                break

        if not listings:
            all_links = soup.find_all("a", href=True)
            for link in all_links:
                text = link.get_text(strip=True).lower()
                if any(kw in text for kw in PHYSICIAN_KEYWORDS) and len(text) > 10:
                    title = link.get_text(strip=True)
                    href = link.get("href", "")
                    apply_url = href if href.startswith("http") else f"{source_url.rstrip('/')}/{href.lstrip('/')}"
                    h = hashlib.sha256(f"{title.lower()}|{employer_name.lower()}|{state.lower()}".encode()).hexdigest()
                    jobs.append(Job(
                        source_name=f"{employer_name} (Direct)",
                        source_type=self.source_type,
                        source_url=source_url,
                        apply_url=apply_url,
                        title=title,
                        employer=employer_name,
                        state=state,
                        short_summary=title,
                        full_text_hash=h,
                    ))
            return jobs

        for item in listings:
            title = ""
            for sel in TITLE_SELECTORS:
                el = item.select_one(sel)
                if el:
                    title = self._safe_text(el)
                    if title and len(title) > 5:
                        break

            if not title or not any(kw in title.lower() for kw in PHYSICIAN_KEYWORDS):
                continue

            location = ""
            for sel in LOCATION_SELECTORS:
                el = item.select_one(sel)
                if el:
                    location = self._safe_text(el)
                    break

            salary_text = ""
            for sel in SALARY_SELECTORS:
                el = item.select_one(sel)
                if el:
                    salary_text = self._safe_text(el)
                    break

            link_el = item.select_one("a[href]")
            apply_url = ""
            if link_el:
                href = link_el.get("href", "")
                apply_url = href if href.startswith("http") else f"{source_url.rstrip('/')}/{href.lstrip('/')}"

            city = location.split(",")[0].strip() if "," in location else location
            full_text = item.get_text(" ", strip=True)

            h = hashlib.sha256(f"{title.lower()}|{employer_name.lower()}|{state.lower()}|{city.lower()}".encode()).hexdigest()
            jobs.append(Job(
                source_name=f"{employer_name} (Direct)",
                source_type=self.source_type,
                source_url=source_url,
                apply_url=apply_url,
                title=title,
                employer=employer_name,
                city=city,
                state=state,
                salary_text=salary_text,
                visa_text=full_text,
                short_summary=full_text[:500],
                full_text_hash=h,
            ))
        return jobs

    def scrape_url(self, careers_url: str, employer_name: str, state: str) -> List[Job]:
        resp = self._get(careers_url)
        if not resp:
            log.warning(f"GenericHospital: skipping {employer_name} — blocked or error")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        jobs = self._extract_jobs(soup, careers_url, employer_name, state)
        log.info(f"GenericHospital: {employer_name} → {len(jobs)} physician jobs")
        return jobs

    def scrape(self, state: str, terms: List[str]) -> List[Job]:
        import yaml
        from pathlib import Path
        cfg_path = Path(__file__).parent.parent.parent / "config" / "states.yaml"
        with open(cfg_path) as f:
            states_cfg = yaml.safe_load(f)

        jobs = []
        state_data = states_cfg.get("states", {}).get(state, {})
        for employer in state_data.get("key_employers", []):
            if employer.get("ats") == "generic" and employer.get("careers_url"):
                log.info(f"GenericHospital: {employer['name']}")
                jobs.extend(self.scrape_url(employer["careers_url"], employer["name"], state))
        return jobs
