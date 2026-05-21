from bs4 import BeautifulSoup
from typing import List
from src.scrapers.base import BaseScraper
from src.models import Job
from src.logger import get_logger

log = get_logger(__name__)

STATE_MAP = {
    "NC": "north-carolina", "SC": "south-carolina", "TX": "texas",
    "NM": "new-mexico", "AZ": "arizona", "OK": "oklahoma", "LA": "louisiana",
}

SPECIALTIES = [
    "internal-medicine",
    "hospitalist",
    "primary-care",
]


class DocCafeScraper(BaseScraper):
    name = "DocCafe"
    source_type = "job_board"
    rate_limit = 3.0
    base_url = "https://www.doccafe.com"

    def scrape(self, state: str, terms: List[str]) -> List[Job]:
        jobs = []
        state_slug = STATE_MAP.get(state, state.lower().replace(" ", "-"))
        for specialty in SPECIALTIES:
            url = f"{self.base_url}/physician-jobs/{state_slug}/{specialty}"
            jobs.extend(self._scrape_page(url, state))
        return jobs

    def _scrape_page(self, url: str, state: str) -> List[Job]:
        jobs = []
        try:
            resp = self.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            listings = soup.select(".job-listing, .job-card, article.job, .position-item")
            if not listings:
                listings = soup.select("[class*='job']")
            for item in listings:
                title_el = item.select_one("h2, h3, .job-title, .position-title, a[href*='job']")
                employer_el = item.select_one(".employer, .company, .facility, .organization")
                location_el = item.select_one(".location, .city, [class*='location']")
                link_el = item.select_one("a[href]")

                title = self.safe_text(title_el)
                employer = self.safe_text(employer_el)
                location = self.safe_text(location_el)
                apply_url = ""
                if link_el:
                    href = link_el.get("href", "")
                    apply_url = href if href.startswith("http") else f"{self.base_url}{href}"

                if not title or len(title) < 5:
                    continue

                city = location.split(",")[0].strip() if "," in location else location.strip()

                full_text = item.get_text(" ", strip=True)
                job = Job(
                    source_name=self.name,
                    source_type=self.source_type,
                    source_url=url,
                    apply_url=apply_url,
                    title=title,
                    employer=employer or "Unknown",
                    city=city,
                    state=state,
                    posted_date=self.extract_posted_date(item) or None,
                    short_summary=full_text[:500],
                    full_text_hash=self.make_hash(title, employer or "", state, city),
                )
                jobs.append(job)
        except PermissionError as e:
            log.warning(f"DocCafe blocked on {url}: {e}")
        except Exception as e:
            log.error(f"DocCafe error on {url}: {e}")
        return jobs
