from bs4 import BeautifulSoup
from typing import List
from src.scrapers.base import BaseScraper
from src.models import Job
from src.logger import get_logger

log = get_logger(__name__)


class HospitalRecruitingScraper(BaseScraper):
    name = "HospitalRecruiting"
    source_type = "job_board"
    rate_limit = 3.0
    base_url = "https://www.hospitalrecruiting.com"

    def scrape(self, state: str, terms: List[str]) -> List[Job]:
        jobs = []
        state_lower = state.lower()
        specialties = ["internal-medicine", "hospitalist", "primary-care-internal-medicine"]
        for spec in specialties:
            url = f"{self.base_url}/physician-jobs/{spec}/{state_lower}"
            jobs.extend(self._scrape_listing(url, state))
        return jobs

    def _scrape_listing(self, url: str, state: str) -> List[Job]:
        jobs = []
        try:
            resp = self.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            listings = soup.select(".job-card, .listing-item, .job-listing, article")
            for item in listings:
                title_el = item.select_one("h2, h3, .title, .job-title")
                employer_el = item.select_one(".employer, .company, .facility")
                location_el = item.select_one(".location, .city-state")
                link_el = item.select_one("a[href*='job'], a[href*='position']")
                salary_el = item.select_one(".salary, .compensation, [class*='salary']")

                title = self.safe_text(title_el)
                employer = self.safe_text(employer_el)
                location = self.safe_text(location_el)
                salary_text = self.safe_text(salary_el)

                apply_url = ""
                if link_el:
                    href = link_el.get("href", "")
                    apply_url = href if href.startswith("http") else f"{self.base_url}{href}"

                if not title or len(title) < 5:
                    continue

                city = location.split(",")[0].strip() if "," in location else location

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
                    salary_text=salary_text,
                    visa_text=full_text,
                    posted_date=self.extract_posted_date(item) or None,
                    short_summary=full_text[:500],
                    full_text_hash=self.make_hash(title, employer or "", state, city),
                )
                jobs.append(job)
        except PermissionError as e:
            log.warning(f"HospitalRecruiting blocked: {e}")
        except Exception as e:
            log.error(f"HospitalRecruiting error on {url}: {e}")
        return jobs
