from bs4 import BeautifulSoup
from src.models import RawJob
from src.scrapers.base import BaseScraper

_STATE_SLUGS = {
    "NC": "north-carolina", "SC": "south-carolina", "TX": "texas",
    "NM": "new-mexico", "AZ": "arizona", "OK": "oklahoma", "LA": "louisiana",
    "CA": "california", "NY": "new-york", "FL": "florida", "GA": "georgia",
    "VA": "virginia", "TN": "tennessee", "OH": "ohio", "PA": "pennsylvania",
    "MD": "maryland", "AL": "alabama", "MS": "mississippi", "KY": "kentucky",
    "MO": "missouri", "AR": "arkansas", "CO": "colorado", "WA": "washington",
    "OR": "oregon", "MN": "minnesota", "WI": "wisconsin", "NJ": "new-jersey",
    "MA": "massachusetts", "CT": "connecticut",
}

_SPECIALTIES = ["internal-medicine", "hospitalist"]
_BASE = "https://www.doccafe.com"

_SKIP_TITLES = {"view job", "featured job", "featured", "save job", "apply"}


def _parse_card(card_div) -> dict:
    """Extract employer, city, posted_date from a DocCafe job card div."""
    field_rows = card_div.select(".field-row")
    texts = [fr.get_text(strip=True) for fr in field_rows]
    # texts[0] = title, [1] = employer, [2] = specialty (+ View Job noise), [3] = location, [4] = date
    employer = texts[1] if len(texts) > 1 else "Unknown"
    employer = employer or "Unknown"

    city = ""
    posted_date_raw = ""
    if len(texts) > 3:
        location_text = texts[3]  # e.g. "Roanoke Rapids,North Carolina,Locums/Travel"
        city = location_text.split(",")[0].strip()
    if len(texts) > 4:
        posted_date_raw = texts[4]  # e.g. "May 19, 2026"

    return {"employer": employer, "city": city, "posted_date_raw": posted_date_raw}


class DocCafeScraper(BaseScraper):
    source_name = "doccafe"
    source_type = "job_board"

    def fetch(self, states: list[str], terms: list[str]) -> list[RawJob]:
        jobs = []
        seen_hrefs = set()
        for state in states:
            slug = _STATE_SLUGS.get(state.upper())
            if not slug:
                continue
            for spec in _SPECIALTIES:
                url = f"{_BASE}/physician-jobs/specialty/{spec}/us/state/{slug}"
                html = self.get(url)
                if not html:
                    continue
                soup = BeautifulSoup(html, "html.parser")
                for card_div in soup.select("div.job-search-result"):
                    link = card_div.select_one("a[href*='/job/physician']")
                    if not link:
                        continue
                    href = link.get("href", "")
                    if not href or href in seen_hrefs:
                        continue
                    title = link.get_text(strip=True)
                    if not title or title.lower() in _SKIP_TITLES:
                        continue
                    seen_hrefs.add(href)
                    apply_url = href if href.startswith("http") else f"{_BASE}{href}"

                    parsed = _parse_card(card_div)
                    card_text = card_div.get_text(" ", strip=True)

                    jobs.append(RawJob(
                        source_name=self.source_name,
                        source_type=self.source_type,
                        source_url=apply_url,
                        title=title,
                        employer=parsed["employer"],
                        city=parsed["city"],
                        state=state.upper(),
                        specialty=spec.replace("-", " ").title(),
                        raw_text=card_text,
                        short_summary=card_text[:400],
                        posted_date_raw=parsed["posted_date_raw"],
                    ))
        return jobs
