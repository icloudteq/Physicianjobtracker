"""
JAMA Career Center scraper â€” AMA/JAMA network medical job board.
Uses the same YM Careers platform as NEJM Career Center.
"""
from bs4 import BeautifulSoup

from src.models import RawJob
from src.scrapers.base import BaseScraper

_STATE_NAMES = {
    "NC": "North Carolina", "SC": "South Carolina", "TX": "Texas",
    "CA": "California", "NY": "New York", "FL": "Florida",
    "GA": "Georgia", "VA": "Virginia", "OH": "Ohio", "TN": "Tennessee",
    "PA": "Pennsylvania", "MD": "Maryland", "AL": "Alabama",
    "MS": "Mississippi", "LA": "Louisiana", "AR": "Arkansas",
    "KY": "Kentucky", "WV": "West Virginia", "IN": "Indiana",
    "MO": "Missouri", "KS": "Kansas", "NE": "Nebraska",
    "OK": "Oklahoma", "AZ": "Arizona", "NM": "New Mexico",
    "CO": "Colorado", "WA": "Washington", "OR": "Oregon",
    "MN": "Minnesota", "WI": "Wisconsin", "NJ": "New Jersey",
    "MA": "Massachusetts", "CT": "Connecticut",
}

_PHYSICIAN_KEYWORDS = [
    "physician", "hospitalist", "nocturnist", "internal medicine",
    "family medicine", "family practice", "primary care", "md ", "d.o.",
]


class JAMACareerScraper(BaseScraper):
    source_name = "jama_career"
    source_type = "job_board"
    BASE = "https://careers.jamanetwork.com"

    def fetch(self, states: list[str], terms: list[str]) -> list[RawJob]:
        jobs = []
        for state in states:
            state_name = _STATE_NAMES.get(state.upper(), state)
            url = f"{self.BASE}/jobs/"
            html = self.get(url, params={"keywords": "physician", "location": state_name})
            if html:
                jobs.extend(self._parse(html, state))
        return jobs

    def _parse(self, html: str, state: str) -> list[RawJob]:
        soup = BeautifulSoup(html, "html.parser")
        jobs = []

        cards = soup.select(
            ".job-result, .vacancy, .job-listing, article.job, "
            "[class*='job-card'], [class*='job-item'], li.job"
        )
        # YM Careers fallback selectors
        if not cards:
            cards = soup.select("li[class*='job'], .lJobItemTitle, [class*='JobsTable']")

        for card in cards[:100]:
            title_el = card.select_one(
                "h2, h3, .job-title, .lJobItemTitle, [class*='title'], a"
            )
            employer_el = card.select_one(
                ".employer, .organization, [class*='employer'], [class*='company']"
            )
            location_el = card.select_one(".location, [class*='location'], [class*='city']")
            link_el = card.select_one("a[href]")

            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not any(kw in title.lower() for kw in _PHYSICIAN_KEYWORDS):
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
                raw_text=raw_text,
                short_summary=raw_text[:400],
            ))
        return jobs

