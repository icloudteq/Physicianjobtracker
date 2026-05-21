from bs4 import BeautifulSoup

from src.models import RawJob
from src.scrapers.base import BaseScraper

_SPECIALTY_MAP = {
    "internal medicine": "internal-medicine",
    "hospitalist": "hospitalist",
    "family medicine": "family-medicine",
    "primary care": "internal-medicine",
}

_STATE_NAMES = {
    "NC": "north-carolina", "SC": "south-carolina", "TX": "texas",
    "CA": "california", "NY": "new-york", "FL": "florida",
    "GA": "georgia", "VA": "virginia", "TN": "tennessee",
    "AL": "alabama", "MS": "mississippi", "LA": "louisiana",
    "OH": "ohio", "PA": "pennsylvania", "IL": "illinois",
    "MI": "michigan", "IN": "indiana", "KY": "kentucky",
    "MO": "missouri", "AR": "arkansas", "OK": "oklahoma",
    "AZ": "arizona", "NM": "new-mexico", "CO": "colorado",
    "WA": "washington", "OR": "oregon", "MN": "minnesota",
    "WI": "wisconsin", "NJ": "new-jersey", "MD": "maryland",
    "MA": "massachusetts", "CT": "connecticut", "WV": "west-virginia",
}


class DocCafeScraper(BaseScraper):
    source_name = "doccafe"
    source_type = "job_board"

    def fetch(self, states: list[str], terms: list[str]) -> list[RawJob]:
        jobs = []
        specialties = set()
        for term in terms:
            for key, slug in _SPECIALTY_MAP.items():
                if key in term.lower():
                    specialties.add(slug)

        if not specialties:
            specialties = {"internal-medicine", "family-medicine", "hospitalist"}

        for state in states:
            state_slug = _STATE_NAMES.get(state.upper())
            if not state_slug:
                continue
            for specialty in specialties:
                url = f"https://www.doccafe.com/physician/{specialty}-jobs-in-{state_slug}"
                html = self.get(url)
                if not html:
                    continue
                jobs.extend(self._parse(html, state, specialty, url))
        return jobs

    def _parse(self, html: str, state: str, specialty: str, source_url: str) -> list[RawJob]:
        soup = BeautifulSoup(html, "lxml")
        jobs = []

        for card in soup.select(".job-listing, .job-card, article.job, [class*='job-item']"):
            title_el = card.select_one("h2, h3, .job-title, [class*='title']")
            employer_el = card.select_one(".employer, .company, [class*='employer'], [class*='company']")
            location_el = card.select_one(".location, [class*='location'], [class*='city']")
            link_el = card.select_one("a[href]")

            if not title_el or not link_el:
                continue

            title = title_el.get_text(strip=True)
            employer = employer_el.get_text(strip=True) if employer_el else "Unknown"
            location = location_el.get_text(strip=True) if location_el else ""
            city = location.split(",")[0].strip() if "," in location else location

            href = link_el.get("href", "")
            if href.startswith("/"):
                href = f"https://www.doccafe.com{href}"

            raw_text = card.get_text(" ", strip=True)

            jobs.append(RawJob(
                source_name=self.source_name,
                source_type=self.source_type,
                source_url=href or source_url,
                title=title,
                employer=employer,
                city=city,
                state=state.upper(),
                specialty=specialty.replace("-", " ").title(),
                raw_text=raw_text,
                short_summary=raw_text[:400],
            ))
        return jobs
