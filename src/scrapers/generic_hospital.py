from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from src.models import RawJob
from src.scrapers.base import BaseScraper, check_robots

_PHYSICIAN_KEYWORDS = [
    "physician", "hospitalist", "nocturnist", "internal medicine",
    "family medicine", "family practice", "primary care", "md ", "d.o.",
]

_JOB_SELECTORS = [
    ".job", ".position", ".opening", ".vacancy", "article",
    "[class*='job-card']", "[class*='job-item']", "[class*='position']",
    "[class*='career']", "li[class*='job']",
]


class GenericHospitalScraper(BaseScraper):
    source_name = "generic_hospital"
    source_type = "hospital"

    def fetch(self, states: list[str], terms: list[str]) -> list[RawJob]:
        return []

    def scrape_employer(self, employer_name: str, careers_url: str, state: str, terms: list[str]) -> list[RawJob]:
        if not check_robots(careers_url):
            self.log.info(f"robots.txt blocks {careers_url}")
            return []

        html = self.get(careers_url)
        if not html:
            return []

        jobs = self._extract_jobs(html, employer_name, careers_url, state, terms)

        # Try common search param patterns if no jobs found on landing page
        if not jobs:
            for param in [{"q": "physician"}, {"keyword": "physician"}, {"search": "physician"}]:
                html2 = self.get(careers_url, params=param)
                if html2:
                    jobs = self._extract_jobs(html2, employer_name, careers_url, state, terms)
                    if jobs:
                        break

        return jobs

    def _extract_jobs(self, html: str, employer: str, source_url: str, state: str, terms: list[str]) -> list[RawJob]:
        soup = BeautifulSoup(html, "html.parser")
        jobs = []

        for selector in _JOB_SELECTORS:
            cards = soup.select(selector)
            if len(cards) > 2:
                for card in cards[:50]:
                    job = self._parse_card(card, employer, source_url, state)
                    if job:
                        title_lower = job.title.lower()
                        if any(kw in title_lower for kw in _PHYSICIAN_KEYWORDS):
                            jobs.append(job)
                if jobs:
                    break

        # Fallback: find links that look like physician jobs
        if not jobs:
            for link in soup.find_all("a", href=True):
                text = link.get_text(strip=True)
                if any(kw in text.lower() for kw in _PHYSICIAN_KEYWORDS) and len(text) > 10:
                    href = link["href"]
                    if href.startswith("/"):
                        href = urljoin(source_url, href)
                    jobs.append(RawJob(
                        source_name=self.source_name,
                        source_type=self.source_type,
                        source_url=href,
                        title=text[:200],
                        employer=employer,
                        state=state.upper(),
                        raw_text=text,
                        short_summary=text[:400],
                        manual_review_required=True,
                    ))

        return jobs

    def _parse_card(self, card, employer: str, source_url: str, state: str) -> RawJob | None:
        title_el = card.select_one("h2, h3, h4, .title, [class*='title'], [class*='job-name']")
        if not title_el:
            return None

        title = title_el.get_text(strip=True)
        if len(title) < 5 or len(title) > 300:
            return None

        location_el = card.select_one(".location, [class*='location'], [class*='city']")
        location = location_el.get_text(strip=True) if location_el else ""
        city = location.split(",")[0].strip() if "," in location else ""

        link_el = card.select_one("a[href]")
        href = ""
        if link_el:
            href = link_el.get("href", "")
            if href.startswith("/"):
                href = urljoin(source_url, href)

        raw_text = card.get_text(" ", strip=True)

        return RawJob(
            source_name=self.source_name,
            source_type=self.source_type,
            source_url=href or source_url,
            title=title,
            employer=employer,
            city=city,
            state=state.upper(),
            raw_text=raw_text,
            short_summary=raw_text[:400],
        )

