import re
from bs4 import BeautifulSoup
from src.models import RawJob
from src.scrapers.base import BaseScraper

_BASE = "https://www.hospitalrecruiting.com"
_PHYSICIAN_KEYWORDS = [
    "physician", "hospitalist", "nocturnist", "internal medicine", "internist",
    "primary care", "md ", " m.d", "d.o.", "doctor",
]
_SPECIALTIES = ["internal-medicine", "hospitalist", "primary-care"]

_COMPANY_RE = re.compile(r"Company:\s*([^\n\r]{3,80}?)(?:\s{3,}|Description|$)", re.IGNORECASE)
_CITY_RE = re.compile(
    r"(?:Internal Medicine|Hospitalist|Primary Care|Family Practice|Family Medicine|General Practice|Physician)\s*-\s*([^,\n]{2,40}),\s*[A-Za-z\s]{2,20}(?:\s|$)",
    re.IGNORECASE,
)


def _slug_to_title(href: str) -> str:
    """Extract job title from URL slug as fallback."""
    slug = href.rstrip("/").rsplit("/", 1)[-1]
    return slug.replace("-", " ").title()


def _find_card_text(link) -> str:
    """Navigate up from link to find container with job card text."""
    el = link
    for _ in range(5):
        el = el.parent
        if el is None:
            break
        text = el.get_text(" ", strip=True)
        if "Company:" in text and len(text) > 40:
            return text
    # Fallback: use link's own parent text
    return link.parent.get_text(" ", strip=True) if link.parent else ""


class HospitalRecruitingScraper(BaseScraper):
    source_name = "hospital_recruiting"
    source_type = "job_board"

    def fetch(self, states: list[str], terms: list[str]) -> list[RawJob]:
        jobs = []
        seen = set()
        for state in states:
            for spec in _SPECIALTIES:
                html = self.get(f"{_BASE}/jobs/", params={"specialty": spec, "state": state.lower()})
                if not html:
                    continue
                soup = BeautifulSoup(html, "html.parser")
                for link in soup.select("a[href*='/job/']"):
                    href = link.get("href", "")
                    if not href or href in seen:
                        continue
                    seen.add(href)
                    apply_url = href if href.startswith("http") else f"{_BASE}{href}"

                    # Card text from the surrounding container
                    card_text = _find_card_text(link)
                    if not card_text:
                        continue

                    # Title: from link text OR from card text (before specialty dash)
                    title = link.get_text(strip=True)
                    if not title or len(title) < 6:
                        # Try first heading inside card container
                        el = link
                        for _ in range(5):
                            el = el.parent
                            if el is None:
                                break
                            h = el.select_one("h2, h3, h4, strong")
                            if h and len(h.get_text(strip=True)) > 5:
                                title = h.get_text(strip=True)
                                break
                    if not title or len(title) < 6:
                        title = _slug_to_title(href)

                    if not any(kw in title.lower() for kw in _PHYSICIAN_KEYWORDS):
                        if not any(kw in card_text.lower() for kw in _PHYSICIAN_KEYWORDS):
                            continue

                    # Employer from "Company:" pattern
                    employer = "Unknown"
                    m = _COMPANY_RE.search(card_text)
                    if m:
                        employer = m.group(1).strip()

                    # City from specialty-location pattern
                    city = ""
                    loc_m = _CITY_RE.search(card_text)
                    if loc_m:
                        city = loc_m.group(1).strip()

                    jobs.append(RawJob(
                        source_name=self.source_name,
                        source_type=self.source_type,
                        source_url=apply_url,
                        title=title,
                        employer=employer,
                        city=city,
                        state=state.upper(),
                        specialty=spec.replace("-", " ").title(),
                        raw_text=card_text,
                        short_summary=card_text[:400],
                    ))
        return jobs
