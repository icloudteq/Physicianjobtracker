"""
Oracle Taleo ATS scraper â€” covers Vanderbilt, Memorial Hermann, UT Health,
Sutter Health, UC system, and many academic medical centers.
Uses the Taleo public RSS/XML feed where available, HTML search as fallback.
All tenants fetched in parallel.
"""
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.models import RawJob
from src.scrapers.base import BaseScraper
from src.logger import get_logger

log = get_logger("taleo")

_PHYSICIAN_KEYWORDS = [
    "physician", "hospitalist", "nocturnist", "internal medicine",
    "family medicine", "family practice", "primary care", "md ", "d.o.",
    "attending", "faculty physician",
]

_STATE_ABBR = {v: k for k, v in {
    "NC": "North Carolina", "SC": "South Carolina", "TX": "Texas",
    "CA": "California", "NY": "New York", "FL": "Florida",
    "GA": "Georgia", "VA": "Virginia", "OH": "Ohio", "TN": "Tennessee",
    "PA": "Pennsylvania", "MD": "Maryland", "AL": "Alabama",
    "LA": "Louisiana", "KY": "Kentucky", "IN": "Indiana",
    "MO": "Missouri", "CO": "Colorado", "WA": "Washington",
    "OR": "Oregon", "MN": "Minnesota", "WI": "Wisconsin",
    "NJ": "New Jersey", "MA": "Massachusetts", "CT": "Connecticut",
    "UT": "Utah", "MI": "Michigan", "IL": "Illinois",
    "AZ": "Arizona", "NM": "New Mexico", "KS": "Kansas",
    "NE": "Nebraska", "OK": "Oklahoma", "AR": "Arkansas",
    "WV": "West Virginia", "MS": "Mississippi",
}.items()}

# (employer_name, taleo_company, home_state, career_section)
# career_section is usually "1" or "Candidate" â€” try "1" first
TALEO_TENANTS = [
    # Tennessee / Southeast
    ("Vanderbilt University Medical Center", "vumc",        "TN", "1"),
    # Texas
    ("Memorial Hermann Health System",       "mhhs",        "TX", "1"),
    ("UTHealth Houston",                     "uth",         "TX", "1"),
    ("Texas Health Resources",               "texashealth", "TX", "1"),
    # California
    ("Sutter Health",                        "sutter",      "CA", "1"),
    ("UC Davis Health",                      "ucdavishealth","CA","1"),
    ("UC Irvine Health",                     "ucirvine",    "CA", "1"),
    # Midwest
    ("University of Michigan Health",        "umich",       "MI", "1"),
    ("Northwestern Medicine",                "nm",          "IL", "1"),
    ("Rush University Medical Center",       "rush",        "IL", "1"),
    ("OSF Healthcare",                       "osf",         "IL", "1"),
    # Mid-Atlantic
    ("MedStar Health",                       "medstar",     "MD", "1"),
    ("Inova Health System",                  "inova",       "VA", "1"),
    ("VCU Health",                           "vcuhealth",   "VA", "1"),
    # National
    ("LifePoint Health",                     "lifepoint",   "ALL", "1"),
    ("RegionalOne Health",                   "regionalone", "ALL", "1"),
]


class TaleoScraper(BaseScraper):
    source_name = "taleo"
    source_type = "hospital"

    def fetch(self, states: list[str], terms: list[str]) -> list[RawJob]:
        targets = [
            (employer, company, section, states if emp_state == "ALL" else [emp_state])
            for employer, company, emp_state, section in TALEO_TENANTS
            if emp_state == "ALL" or emp_state in states
        ]
        all_jobs: list[RawJob] = []
        with ThreadPoolExecutor(max_workers=min(len(targets), 16)) as pool:
            futures = {pool.submit(self._scrape_tenant, *t): t[0] for t in targets}
            for future in as_completed(futures):
                try:
                    all_jobs.extend(future.result())
                except Exception as e:
                    log.warning(f"Taleo tenant failed: {e}")
        return all_jobs

    def _scrape_tenant(self, employer: str, company: str, section: str, states: list[str]) -> list[RawJob]:
        # Try RSS feed first (faster, structured data)
        rss_url = f"https://{company}.taleo.net/careersection/{section}/jobboard.ftl"
        rss_html = self.get(rss_url, params={"lang": "en", "type": "rssfeed"})
        if rss_html:
            jobs = self._parse_rss(rss_html, employer, states)
            if jobs:
                log.info(f"Taleo RSS {employer}: {len(jobs)} jobs")
                return jobs

        # Fallback: HTML search page
        search_url = f"https://{company}.taleo.net/careersection/{section}/jobsearch.ftl"
        html = self.get(search_url, params={"lang": "en", "searchKeyword": "physician"})
        if not html:
            return []
        jobs = self._parse_html(html, employer, company, section, states)
        if jobs:
            log.info(f"Taleo HTML {employer}: {len(jobs)} jobs")
        return jobs

    def _parse_rss(self, content: str, employer: str, states: list[str]) -> list[RawJob]:
        jobs = []
        try:
            root = ET.fromstring(content.encode("utf-8", errors="replace"))
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            items = root.findall(".//item") or root.findall(".//atom:entry", ns)
            for item in items:
                title = (item.findtext("title") or "").strip()
                if not any(kw in title.lower() for kw in _PHYSICIAN_KEYWORDS):
                    continue

                link = (item.findtext("link") or "").strip()
                description = (item.findtext("description") or "").strip()
                location = (item.findtext("location") or "").strip()

                state = self._infer_state(location + " " + description, states)
                if not state:
                    continue

                city = location.split(",")[0].strip() if "," in location else location
                jobs.append(RawJob(
                    source_name=self.source_name,
                    source_type=self.source_type,
                    source_url=link,
                    title=title,
                    employer=employer,
                    employer_type="direct",
                    city=city,
                    state=state,
                    raw_text=description,
                    short_summary=description[:400],
                ))
        except ET.ParseError:
            pass
        return jobs

    def _parse_html(self, html: str, employer: str, company: str, section: str, states: list[str]) -> list[RawJob]:
        soup = BeautifulSoup(html, "html.parser")
        jobs = []
        base_url = f"https://{company}.taleo.net"

        rows = (
            soup.select("tr.listSectionContentShort") or
            soup.select(".listSectionContentShort") or
            soup.select("tr[class*='job'], .job-result, [class*='career-row']")
        )

        for row in rows[:100]:
            title_el = row.select_one(
                ".jobTitle, [class*='title'], td a, h2, h3"
            )
            location_el = row.select_one(
                ".jobLocation, [class*='location'], [class*='city']"
            )
            link_el = row.select_one("a[href]")

            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not any(kw in title.lower() for kw in _PHYSICIAN_KEYWORDS):
                continue

            location = location_el.get_text(strip=True) if location_el else ""
            state = self._infer_state(location, states)
            if not state:
                continue

            city = location.split(",")[0].strip() if "," in location else location
            href = ""
            if link_el:
                href = link_el.get("href", "")
                if href.startswith("/"):
                    href = f"{base_url}{href}"

            raw_text = row.get_text(" ", strip=True)
            jobs.append(RawJob(
                source_name=self.source_name,
                source_type=self.source_type,
                source_url=href or f"{base_url}/careersection/{section}/jobsearch.ftl",
                title=title,
                employer=employer,
                employer_type="direct",
                city=city,
                state=state,
                raw_text=raw_text,
                short_summary=raw_text[:400],
            ))
        return jobs

    def _infer_state(self, text: str, states: list[str]) -> str | None:
        text_upper = text.upper()
        for state in states:
            if state.upper() in text_upper:
                return state.upper()
            state_name = {v: k for k, v in _STATE_ABBR.items()}.get(state.upper(), "")
            if state_name and state_name.upper() in text_upper:
                return state.upper()
        return None

