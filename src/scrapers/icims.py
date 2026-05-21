"""
iCIMS ATS scraper â€” covers Cone Health, ECU Health, AdventHealth, Bon Secours,
Trinity Health, SSM Health, Mercy, Ochsner, Emory, and hundreds more iCIMS clients.
Uses the public iCIMS HTML search endpoint â€” no authentication required.
All tenants fetched in parallel.
"""
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.models import RawJob
from src.scrapers.base import BaseScraper
from src.logger import get_logger

log = get_logger("icims")

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
    "NV": "Nevada", "ID": "Idaho", "MT": "Montana", "WY": "Wyoming",
    "ND": "North Dakota", "SD": "South Dakota", "IA": "Iowa",
    "MI": "Michigan", "IL": "Illinois",
}

# (employer_name, icims_tenant, home_state)
# tenant is the subdomain of .icims.com
ICIMS_TENANTS = [
    # North Carolina
    ("Cone Health",              "conehealth",          "NC"),
    ("ECU Health",               "ecuhealth",           "NC"),
    ("Cape Fear Valley Health",  "cfvhs",               "NC"),
    ("CaroMont Health",          "caromonthealth",       "NC"),
    ("FirstHealth of the Carolinas", "firsthealth",     "NC"),
    # South Carolina
    ("Bon Secours",              "bonsecours",          "SC"),
    ("Spartanburg Regional",     "srmcsc",              "SC"),
    ("AnMed Health",             "anmedhealth",         "SC"),
    # National / multi-state
    ("AdventHealth",             "adventhealth",        "ALL"),
    ("Tenet Health",             "tenethealth",         "ALL"),
    ("Community Health Systems", "chscorp",             "ALL"),
    ("UHS",                      "uhsinc",              "ALL"),
    ("Ascension Health",         "ascension",           "ALL"),
    ("Banner Health",            "bannerhealth",        "ALL"),
    ("OhioHealth",               "ohiohealth",          "ALL"),
    ("WellSpan Health",          "wellspan",            "ALL"),
    ("Geisinger",                "geisinger",           "ALL"),
    ("Intermountain Health",     "intermountain",       "ALL"),
    ("Allegheny Health Network", "ahnnetwork",          "ALL"),
    ("Jefferson Health",         "jeffersonhealth",     "ALL"),
    ("Mercy Health",             "mercy",               "ALL"),
    ("SSM Health",               "ssmhealth",           "ALL"),
    ("Trinity Health",           "trinity-health",      "ALL"),
    ("Hackensack Meridian",      "hackensackmeridian",  "ALL"),
    ("RWJBarnabas Health",       "rwjbh",               "ALL"),
    ("MaineHealth",              "mainehealth",         "ALL"),
    ("Emory Healthcare",         "emory",               "ALL"),
    ("Ochsner Health",           "ochsner",             "ALL"),
    ("Memorial Hermann",         "mhhs",                "ALL"),
    ("UC San Diego Health",      "ucsdhealth",          "ALL"),
    ("Lifespan",                 "lifespan",            "ALL"),
    ("Centura Health",           "centura",             "ALL"),
    ("WakeMed",                  "wakemed",             "NC"),
]


class IcimsScraper(BaseScraper):
    source_name = "icims"
    source_type = "hospital"

    def fetch(self, states: list[str], terms: list[str]) -> list[RawJob]:
        targets = [
            (employer, tenant, states if emp_state == "ALL" else [emp_state])
            for employer, tenant, emp_state in ICIMS_TENANTS
            if emp_state == "ALL" or emp_state in states
        ]
        all_jobs: list[RawJob] = []
        with ThreadPoolExecutor(max_workers=min(len(targets), 20)) as pool:
            futures = {pool.submit(self._scrape_tenant, *t): t[0] for t in targets}
            for future in as_completed(futures):
                try:
                    all_jobs.extend(future.result())
                except Exception as e:
                    log.warning(f"iCIMS tenant failed: {e}")
        return all_jobs

    def _scrape_tenant(self, employer: str, tenant: str, states: list[str]) -> list[RawJob]:
        jobs = []
        for state in states:
            state_name = _STATE_NAMES.get(state.upper(), state)
            url = f"https://{tenant}.icims.com/jobs/search"
            html = self.get(url, params={
                "ss": "1",
                "searchKeyword": "physician",
                "searchLocation": state_name,
            })
            if not html:
                continue
            parsed = self._parse(html, employer, tenant, state, url)
            if parsed:
                log.info(f"iCIMS {employer}/{state}: {len(parsed)} jobs")
            jobs.extend(parsed)
        return jobs

    def _parse(self, html: str, employer: str, tenant: str, state: str, source_url: str) -> list[RawJob]:
        soup = BeautifulSoup(html, "html.parser")
        jobs = []

        rows = (
            soup.select("tr.iCIMS_JobsTable_BodyRow") or
            soup.select(".iCIMS_JobsTable_BodyRow") or
            soup.select("[class*='job-list'] li") or
            soup.select("li[class*='job'], .job-result, article.job")
        )

        for row in rows[:100]:
            title_el = row.select_one(
                ".iCIMS_JobTitle, [class*='job-title'], [class*='title'], h2, h3, a"
            )
            location_el = row.select_one(
                ".iCIMS_JobLocation, [class*='location'], [class*='city']"
            )
            link_el = row.select_one("a[href]")

            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not any(kw in title.lower() for kw in _PHYSICIAN_KEYWORDS):
                continue

            location = location_el.get_text(strip=True) if location_el else ""
            city = location.split(",")[0].strip() if "," in location else location

            href = ""
            if link_el:
                href = link_el.get("href", "")
                if href.startswith("/"):
                    href = f"https://{tenant}.icims.com{href}"

            raw_text = row.get_text(" ", strip=True)
            jobs.append(RawJob(
                source_name=self.source_name,
                source_type=self.source_type,
                source_url=href or source_url,
                title=title,
                employer=employer,
                employer_type="direct",
                city=city,
                state=state.upper(),
                raw_text=raw_text,
                short_summary=raw_text[:400],
            ))
        return jobs

