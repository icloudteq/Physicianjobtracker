from bs4 import BeautifulSoup

from src.models import RawJob
from src.scrapers.base import BaseScraper

_STATE_NAMES = {
    "NC": "North Carolina", "SC": "South Carolina", "TX": "Texas",
    "CA": "California", "NY": "New York", "FL": "Florida",
    "GA": "Georgia", "VA": "Virginia", "OH": "Ohio",
}


class NEJMScraper(BaseScraper):
    source_name = "nejm"
    source_type = "job_board"
    BASE = "https://careers.nejm.org"

    def fetch(self, states: list[str], terms: list[str]) -> list[RawJob]:
        jobs = []
        for term in terms[:3]:  # limit queries to avoid rate limiting
            for state in states:
                url = f"{self.BASE}/jobs/"
                html = self.get(url, params={"keywords": term, "location": state})
                if html:
                    jobs.extend(self._parse(html, state, term))
        return jobs

    def _parse(self, html: str, state: str, term: str) -> list[RawJob]:
        soup = BeautifulSoup(html, "lxml")
        jobs = []

        for card in soup.select(".job-result, .vacancy, article, [class*='job']"):
            title_el = card.select_one("h2, h3, .job-title, a")
            employer_el = card.select_one(".employer, .organization, [class*='employer']")
            location_el = card.select_one(".location, [class*='location']")
            link_el = card.select_one("a[href]")

            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            if not any(kw in title.lower() for kw in ["medicine", "hospitalist", "physician", "nocturnist", "family"]):
                continue

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
