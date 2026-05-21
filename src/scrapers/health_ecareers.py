from bs4 import BeautifulSoup
from typing import List
from src.scrapers.base import BaseScraper
from src.models import Job
from src.logger import get_logger

log = get_logger(__name__)


class HealthECareersScraper(BaseScraper):
    name = "Health eCareers"
    source_type = "job_board"
    rate_limit = 4.0
    base_url = "https://www.healthecareers.com"

    def scrape(self, state: str, terms: List[str]) -> List[Job]:
        jobs = []
        specialties = ["internal+medicine", "hospitalist"]
        for spec in specialties:
            url = f"{self.base_url}/jobs?specialty={spec}&location={state}"
            jobs.extend(self._scrape_page(url, state))
        return jobs

    def _scrape_page(self, url: str, state: str) -> List[Job]:
        jobs = []
        try:
            resp = self.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            listings = soup.select(".job-card, .job-result, .job-listing, li.job")
            for item in listings:
                title_el = item.select_one("h2, h3, .job-title, a.position-title")
                employer_el = item.select_one(".employer, .company, .facility-name")
                location_el = item.select_one(".location, .city-state")
                link_el = item.select_one("a[href]")
                salary_el = item.select_one(".salary, [class*='salary'], [class*='compensation']")

                title = self.safe_text(title_el)
                employer = self.safe_text(employer_el)
                location = self.safe_text(location_el)
                salary_text = self.safe_text(salary_el)

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
                    salary_text=salary_text,
                    visa_text=full_text,
                    posted_date=self.extract_posted_date(item) or None,
                    short_summary=full_text[:500],
                    full_text_hash=self.make_hash(title, employer or "", state, city),
                ))
        except PermissionError as e:
            log.warning(f"HealthECareers blocked: {e}")
        except Exception as e:
            log.error(f"HealthECareers error {url}: {e}")
        return jobs
