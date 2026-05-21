from bs4 import BeautifulSoup

from src.models import RawJob
from src.scrapers.base import BaseScraper

_SPECIALTY_SLUGS = {
    "internal medicine": "internal-medicine-jobs",
    "hospitalist": "hospitalist-jobs",
    "family medicine": "family-medicine-jobs",
    "nocturnist": "nocturnist-jobs",
    "primary care": "primary-care-jobs",
}


class HospitalRecruitingScraper(BaseScraper):
    source_name = "hospital_recruiting"
    source_type = "job_board"
    BASE = "https://www.hospitalrecruiting.com"

    def fetch(self, states: list[str], terms: list[str]) -> list[RawJob]:
        jobs = []
        slugs = set()
        for term in terms:
            for key, slug in _SPECIALTY_SLUGS.items():
                if key in term.lower():
                    slugs.add(slug)
        if not slugs:
            slugs = {"internal-medicine-jobs", "hospitalist-jobs", "family-medicine-jobs"}

        for slug in slugs:
            for state in states:
                url = f"{self.BASE}/{slug}/{state.lower()}/"
                html = self.get(url)
                if html:
                    jobs.extend(self._parse(html, state, slug, url))
        return jobs

    def _parse(self, html: str, state: str, slug: str, source_url: str) -> list[RawJob]:
        soup = BeautifulSoup(html, "lxml")
        jobs = []

        for card in soup.select(".job, .listing, article, [class*='job-item'], [class*='position']"):
            title_el = card.select_one("h2, h3, .title, [class*='title']")
            employer_el = card.select_one(".employer, .hospital, [class*='employer'], [class*='hospital']")
            location_el = card.select_one(".location, [class*='location'], [class*='city']")
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
            specialty = slug.replace("-jobs", "").replace("-", " ").title()

            jobs.append(RawJob(
                source_name=self.source_name,
                source_type=self.source_type,
                source_url=href or source_url,
                title=title,
                employer=employer,
                city=city,
                state=state.upper(),
                specialty=specialty,
                raw_text=raw_text,
                short_summary=raw_text[:400],
            ))
        return jobs
