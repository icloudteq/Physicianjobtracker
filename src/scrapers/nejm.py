from bs4 import BeautifulSoup
from src.models import RawJob
from src.scrapers.base import BaseScraper

_STATE_NAMES = {
    "NC": "North Carolina", "SC": "South Carolina", "TX": "Texas",
    "NM": "New Mexico", "AZ": "Arizona", "OK": "Oklahoma", "LA": "Louisiana",
    "CA": "California", "NY": "New York", "FL": "Florida", "GA": "Georgia",
    "VA": "Virginia", "OH": "Ohio", "TN": "Tennessee", "PA": "Pennsylvania",
    "MD": "Maryland", "AL": "Alabama", "MS": "Mississippi",
}

_PHYSICIAN_KEYWORDS = [
    "physician", "hospitalist", "nocturnist", "internal medicine",
    "family medicine", "primary care", "internist", "md ", "m.d.",
]

_BASE = "https://www.nejmcareercenter.org"


class NEJMScraper(BaseScraper):
    source_name = "nejm"
    source_type = "job_board"

    def fetch(self, states: list[str], terms: list[str]) -> list[RawJob]:
        jobs = []
        seen = set()
        search_terms = ["physician", "hospitalist", "internal medicine"]
        for state in states:
            state_name = _STATE_NAMES.get(state.upper(), state)
            for term in search_terms:
                html = self.get(f"{_BASE}/jobs/", params={"keywords": term, "location": state_name})
                if not html:
                    continue
                soup = BeautifulSoup(html, "html.parser")
                # Primary selector â€” YM Careers platform
                cards = soup.select("li[class*='job']")
                for card in cards:
                    link_el = card.select_one("a[href]")
                    if not link_el:
                        continue
                    href = link_el.get("href", "")
                    if href in seen:
                        continue
                    title_el = card.select_one("h2, h3, .lJobItemTitle, [class*='title'], a")
                    title = (title_el or link_el).get_text(strip=True)
                    if not title or len(title) < 6:
                        continue
                    if not any(kw in title.lower() for kw in _PHYSICIAN_KEYWORDS):
                        continue
                    seen.add(href)
                    apply_url = href if href.startswith("http") else f"{_BASE}{href}"
                    employer_el = card.select_one(".employer, .organization, [class*='employer'], [class*='company']")
                    location_el = card.select_one(".location, [class*='location'], [class*='city']")
                    employer = employer_el.get_text(strip=True) if employer_el else "Unknown"
                    location = location_el.get_text(strip=True) if location_el else ""
                    city = location.split(",")[0].strip() if "," in location else ""
                    raw_text = card.get_text(" ", strip=True)
                    jobs.append(RawJob(
                        source_name=self.source_name,
                        source_type=self.source_type,
                        source_url=apply_url,
                        title=title,
                        employer=employer,
                        city=city,
                        state=state.upper(),
                        specialty="Internal Medicine",
                        raw_text=raw_text,
                        short_summary=raw_text[:400],
                    ))
        return jobs

