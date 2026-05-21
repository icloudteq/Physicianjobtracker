from bs4 import BeautifulSoup
from typing import List
from src.scrapers.base import BaseScraper
from src.models import Job
from src.logger import get_logger

log = get_logger(__name__)

STATE_FULL = {
    "NC": "North Carolina", "SC": "South Carolina", "TX": "Texas",
    "NM": "New Mexico", "AZ": "Arizona", "OK": "Oklahoma", "LA": "Louisiana",
}


class NEJMScraper(BaseScraper):
    name = "NEJM CareerCenter"
    source_type = "job_board"
    rate_limit = 4.0
    base_url = "https://www.nejmcareercenter.org"

    def scrape(self, state: str, terms: List[str]) -> List[Job]:
        jobs = []
        state_full = STATE_FULL.get(state, state)
        search_terms = ["internal+medicine", "hospitalist", "primary+care+physician"]
        for term in search_terms:
            url = f"{self.base_url}/jobs/?q={term}&location={state_full.replace(' ', '+')}"
            jobs.extend(self._scrape_page(url, state))
        return jobs

    def _scrape_page(self, url: str, state: str) -> List[Job]:
        jobs = []
        try:
            resp = self.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            listings = soup.select(".job-result, .job-listing, .search-result-item, article.job")
            for item in listings:
                title_el = item.select_one("h2, h3, .job-title, a.title")
                employer_el = item.select_one(".employer, .organization, .company")
                location_el = item.select_one(".location, .city")
                link_el = item.select_one("a[href]")

                title = self.safe_text(title_el)
                employer = self.safe_text(employer_el)
                location = self.safe_text(location_el)

                if not title:
                    continue

                apply_url = ""
                if link_el:
                    href = link_el.get("href", "")
                    apply_url = href if href.startswith("http") else f"{self.base_url}{href}"

                city = location.split(",")[0].strip() if location else ""
                full_text = item.get_text(" ", strip=True)

                jobs.append(Job(
                    source_name=self.name,
                    source_type=self.source_type,
                    source_url=url,
                    apply_url=apply_url,
                    title=title,
                    employer=employer or "Unknown",
                    city=city,
                    state=state,
                    visa_text=full_text,
                    posted_date=self.extract_posted_date(item) or None,
                    short_summary=full_text[:500],
                    full_text_hash=self.make_hash(title, employer or "", state, city),
                ))
        except PermissionError as e:
            log.warning(f"NEJM blocked: {e}")
        except Exception as e:
            log.error(f"NEJM error {url}: {e}")
        return jobs
