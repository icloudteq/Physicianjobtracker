"""
iCIMS ATS scraper — covers Novant Health, Cone Health, Roper St. Francis, etc.
iCIMS has a public job search API that can be queried without login.
"""
import time
import requests
from bs4 import BeautifulSoup
from typing import List
import yaml
from pathlib import Path
from src.models import Job
from src.logger import get_logger
from fake_useragent import UserAgent

log = get_logger(__name__)
_ua = UserAgent()

PHYSICIAN_KEYWORDS = [
    "internal medicine", "hospitalist", "nocturnist", "primary care physician",
    "internist", "im physician", "general internist",
]


class ICIMSScraper:
    name = "iCIMS ATS"
    source_type = "direct_employer"
    rate_limit = 4.0

    def _get_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update({"User-Agent": _ua.random})
        return s

    def scrape_tenant(self, icims_id: str, employer_name: str, state: str, city: str = "") -> List[Job]:
        jobs = []
        session = self._get_session()
        search_terms = ["internal medicine", "hospitalist", "physician"]

        for term in search_terms:
            url = (
                f"https://careers-{icims_id}.icims.com/jobs/search"
                f"?ss=1&searchKeyword={term.replace(' ', '+')}&searchCategory=&searchLocation=&in_iframe=1"
            )
            try:
                time.sleep(self.rate_limit)
                resp = session.get(url, timeout=20)
                if resp.status_code in (403, 429):
                    log.warning(f"iCIMS {employer_name}: blocked ({resp.status_code})")
                    break
                soup = BeautifulSoup(resp.text, "html.parser")
                listings = soup.select(".iCIMS_JobsTable tr, .job-row, li.job")
                for item in listings:
                    title_el = item.select_one("a[href*='/jobs/'], .iCIMS_JobTitle, .job-title")
                    location_el = item.select_one(".iCIMS_JobLocation, .location")
                    title = title_el.get_text(strip=True) if title_el else ""
                    location = location_el.get_text(strip=True) if location_el else ""
                    if not title or not any(kw in title.lower() for kw in PHYSICIAN_KEYWORDS):
                        continue
                    apply_url = ""
                    if title_el and title_el.name == "a":
                        href = title_el.get("href", "")
                        apply_url = href if href.startswith("http") else f"https://careers-{icims_id}.icims.com{href}"
                    city_parsed = location.split(",")[0].strip() if "," in location else location

                    import hashlib
                    h = hashlib.sha256(f"{title.lower()}|{employer_name.lower()}|{state.lower()}".encode()).hexdigest()
                    full_text = item.get_text(" ", strip=True)
                    jobs.append(Job(
                        source_name=f"{employer_name} (iCIMS)",
                        source_type=self.source_type,
                        source_url=url,
                        apply_url=apply_url,
                        title=title,
                        employer=employer_name,
                        city=city_parsed or city,
                        state=state,
                        visa_text=full_text,
                        short_summary=full_text[:500],
                        full_text_hash=h,
                    ))
            except Exception as e:
                log.error(f"iCIMS {employer_name} error: {e}")
        return jobs

    def scrape(self, state: str, terms: List[str]) -> List[Job]:
        cfg_path = Path(__file__).parent.parent.parent / "config" / "states.yaml"
        with open(cfg_path) as f:
            states_cfg = yaml.safe_load(f)

        jobs = []
        state_data = states_cfg.get("states", {}).get(state, {})
        for employer in state_data.get("key_employers", []):
            if employer.get("ats") == "icims" and employer.get("icims_id"):
                log.info(f"Scraping iCIMS: {employer['name']}")
                jobs.extend(self.scrape_tenant(
                    str(employer["icims_id"]), employer["name"], state
                ))
        return jobs
