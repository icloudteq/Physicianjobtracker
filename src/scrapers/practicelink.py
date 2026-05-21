"""
PracticeLink scraper â€” physician-specific job board with public search results.
Scrapes the public search/browse pages without login.
"""
from bs4 import BeautifulSoup

from src.models import RawJob
from src.scrapers.base import BaseScraper
from src.logger import get_logger

log = get_logger("practicelink")

_PHYSICIAN_KEYWORDS = [
    "physician", "hospitalist", "nocturnist", "internal medicine",
    "family medicine", "family practice", "primary care", "md ", "d.o.",
]

_STATE_SLUGS = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas",
    "CA": "california", "CO": "colorado", "CT": "connecticut",
    "DE": "delaware", "FL": "florida", "GA": "georgia",
    "HI": "hawaii", "ID": "idaho", "IL": "illinois", "IN": "indiana",
    "IA": "iowa", "KS": "kansas", "KY": "kentucky", "LA": "louisiana",
    "ME": "maine", "MD": "maryland", "MA": "massachusetts", "MI": "michigan",
    "MN": "minnesota", "MS": "mississippi", "MO": "missouri", "MT": "montana",
    "NE": "nebraska", "NV": "nevada", "NH": "new-hampshire", "NJ": "new-jersey",
    "NM": "new-mexico", "NY": "new-york", "NC": "north-carolina",
    "ND": "north-dakota", "OH": "ohio", "OK": "oklahoma", "OR": "oregon",
    "PA": "pennsylvania", "RI": "rhode-island", "SC": "south-carolina",
    "SD": "south-dakota", "TN": "tennessee", "TX": "texas", "UT": "utah",
    "VT": "vermont", "VA": "virginia", "WA": "washington",
    "WV": "west-virginia", "WI": "wisconsin", "WY": "wyoming",
}

_SPECIALTIES = [
    "internal-medicine",
    "family-medicine",
    "hospitalist",
]

BASE = "https://www.practicelink.com"


class PracticeLinkScraper(BaseScraper):
    source_name = "practicelink"
    source_type = "job_board"

    def fetch(self, states: list[str], terms: list[str]) -> list[RawJob]:
        jobs = []
        for state in states:
            state_slug = _STATE_SLUGS.get(state.upper())
            if not state_slug:
                continue
            for specialty in _SPECIALTIES:
                url = f"{BASE}/physician-jobs/{specialty}/{state_slug}/"
                html = self.get(url)
                if not html:
                    continue
                parsed = self._parse(html, state, url)
                if parsed:
                    log.info(f"PracticeLink {specialty}/{state}: {len(parsed)} jobs")
                jobs.extend(parsed)
        return jobs

    def _parse(self, html: str, state: str, source_url: str) -> list[RawJob]:
        soup = BeautifulSoup(html, "html.parser")
        jobs = []

        cards = (
            soup.select(".job-listing, .job-card, .opportunity-card") or
            soup.select("article.job, [class*='job-item'], [class*='opportunity']") or
            soup.select("li[class*='job'], tr[class*='job']")
        )

        for card in cards[:100]:
            title_el = card.select_one(
                "h2, h3, .job-title, [class*='title'], [class*='position']"
            )
            employer_el = card.select_one(
                ".employer, .practice, [class*='employer'], [class*='practice'], "
                "[class*='company'], [class*='organization']"
            )
            location_el = card.select_one(
                ".location, [class*='location'], [class*='city']"
            )
            salary_el = card.select_one(
                ".salary, [class*='salary'], [class*='compensation']"
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
            salary_text = salary_el.get_text(strip=True) if salary_el else None

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
                salary_text=salary_text,
                raw_text=raw_text,
                short_summary=raw_text[:400],
            ))
        return jobs

