"""
PracticeMatch scraper â€” large physician-specific job board.
Scrapes public job listings without requiring login.
"""
from bs4 import BeautifulSoup

from src.models import RawJob
from src.scrapers.base import BaseScraper
from src.logger import get_logger

log = get_logger("practicematch")

_PHYSICIAN_KEYWORDS = [
    "physician", "hospitalist", "nocturnist", "internal medicine",
    "family medicine", "family practice", "primary care", "md ", "d.o.",
]

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
    "MA": "Massachusetts", "CT": "Connecticut", "UT": "Utah",
    "NV": "Nevada", "MI": "Michigan", "IL": "Illinois",
}

BASE = "https://www.practicematch.com"
_SEARCH_PATHS = [
    "/physician-job-openings/",
    "/jobs/",
    "/search-physician-jobs/",
]

_SPECIALTIES = [
    "internal-medicine",
    "family-medicine",
    "hospitalist",
    "primary-care",
]


class PracticeMatchScraper(BaseScraper):
    source_name = "practicematch"
    source_type = "job_board"

    def fetch(self, states: list[str], terms: list[str]) -> list[RawJob]:
        jobs = []
        for state in states:
            state_name = _STATE_NAMES.get(state.upper(), state)
            for path in _SEARCH_PATHS:
                html = self.get(
                    f"{BASE}{path}",
                    params={"specialty": "all", "location": state_name, "state": state},
                )
                if not html:
                    continue
                parsed = self._parse(html, state, f"{BASE}{path}")
                if parsed:
                    jobs.extend(parsed)
                    log.info(f"PracticeMatch {state} ({path}): {len(parsed)} jobs")
                    break
        return jobs

    def _parse(self, html: str, state: str, source_url: str) -> list[RawJob]:
        soup = BeautifulSoup(html, "html.parser")
        jobs = []

        cards = (
            soup.select(".job-listing, .job-card, .position-card") or
            soup.select("article.job, [class*='job-item'], [class*='opportunity']") or
            soup.select("li[class*='job'], tr[class*='job'], [class*='career-item']")
        )

        for card in cards[:100]:
            title_el = card.select_one(
                "h2, h3, .job-title, [class*='title'], [class*='position-name']"
            )
            employer_el = card.select_one(
                ".employer, .practice, .organization, [class*='employer'], [class*='practice']"
            )
            location_el = card.select_one(
                ".location, [class*='location'], [class*='city'], [class*='state']"
            )
            link_el = card.select_one("a[href]")

            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title:
                continue
            if not any(kw in title.lower() for kw in _PHYSICIAN_KEYWORDS):
                continue

            employer = employer_el.get_text(strip=True) if employer_el else "Unknown"
            location = location_el.get_text(strip=True) if location_el else ""
            city = location.split(",")[0].strip() if "," in location else location

            href = ""
            if link_el:
                href = link_el.get("href", "")
                if href.startswith("/"):
                    href = f"{BASE}{href}"

            raw_text = card.get_text(" ", strip=True)
            jobs.append(RawJob(
                source_name=self.source_name,
                source_type=self.source_type,
                source_url=href or source_url,
                title=title,
                employer=employer,
                city=city,
                state=state.upper(),
                raw_text=raw_text,
                short_summary=raw_text[:400],
            ))
        return jobs

