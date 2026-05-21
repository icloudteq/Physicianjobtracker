from bs4 import BeautifulSoup

from src.models import RawJob
from src.scrapers.base import BaseScraper


class HealthECareersScraper(BaseScraper):
    source_name = "health_ecareers"
    source_type = "job_board"
    BASE = "https://www.healthecareers.com"

    def fetch(self, states: list[str], terms: list[str]) -> list[RawJob]:
        jobs = []
        for term in terms[:4]:
            for state in states:
                url = f"{self.BASE}/jobs/search"
                html = self.get(url, params={"q": term, "l": state, "specialty": "internal-medicine"})
                if html:
                    jobs.extend(self._parse(html, state, term))
        return jobs

    def _parse(self, html: str, state: str, term: str) -> list[RawJob]:
        soup = BeautifulSoup(html, "html.parser")
        jobs = []

        for card in soup.select(".job-listing, .search-result, [class*='job-card'], [class*='result-item']"):
            title_el = card.select_one("h2, h3, .title, [class*='job-title']")
            employer_el = card.select_one(".employer, .company-name, [class*='employer']")
            location_el = card.select_one(".location, [class*='location']")
            link_el = card.select_one("a[href]")

            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            employer = employer_el.get_text(strip=True) if employer_el else "Unknown"
            location = location_el.get_text(strip=True) if location_el else ""
            city = location.split(",")[0].strip() if "," in location else ""

            href = ""
            if link_el:
                href = link_el.get("href", "")
                if href.startswith("/"):
                    href = f"{self.BASE}{href}"

            raw_text = card.get_text(" ", strip=True)
            jobs.append(RawJob(
                source_name=self.source_name,
                source_type=self.source_type,
                source_url=href or f"{self.BASE}/jobs/",
                title=title,
                employer=employer,
                city=city,
                state=state.upper(),
                specialty=term,
                raw_text=raw_text,
                short_summary=raw_text[:400],
            ))
        return jobs

