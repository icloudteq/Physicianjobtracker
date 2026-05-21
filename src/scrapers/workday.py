"""
Workday ATS scraper — covers Duke, Atrium, Novant, UNC, WakeMed, MUSC, HCA,
CommonSpirit, and 20+ more. Uses public Workday JSON API — no login required.
All tenants fetched in parallel.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.models import RawJob
from src.scrapers.base import BaseScraper, HEADERS
from src.logger import get_logger

log = get_logger("workday")

PHYSICIAN_KEYWORDS = [
    "physician", "hospitalist", "nocturnist", "internal medicine",
    "family medicine", "family practice", "primary care", "md ", "d.o",
]

# (employer_name, tenant, job_board, home_state, employer_type)
WORKDAY_TENANTS = [
    # North Carolina
    ("Duke Health",           "dukehealth",        "Duke_Careers",             "NC",  "academic"),
    ("Atrium Health",         "atriumhealth",      "Atrium_Health_Careers",    "NC",  "hospital"),
    ("Novant Health",         "novanthealth",      "Novant_Health_Careers",    "NC",  "hospital"),
    ("WakeMed",               "wakemed",           "WakeMed_Careers",          "NC",  "hospital"),
    ("Wake Forest Baptist",   "wakehealth",        "Wake_Health_Careers",      "NC",  "academic"),
    ("Cone Health",           "conehealth",        "Cone_Health_Careers",      "NC",  "hospital"),
    ("UNC Health",            "unchealthcare",     "UNC_External_Careers",     "NC",  "academic"),
    # South Carolina
    ("Prisma Health",         "prismahealth",      "Prisma_Health_Careers",    "SC",  "hospital"),
    ("MUSC Health",           "musc",              "MUSC_External_Careers",    "SC",  "academic"),
    ("Roper St. Francis",     "roperstfrancis",    "RSF_Careers",              "SC",  "hospital"),
    # National / multi-state
    ("HCA Healthcare",        "hcahealthcare",     "HCA_External_Careers",     "ALL", "hospital"),
    ("CommonSpirit Health",   "commonspirit",      "CommonSpirit_Careers",     "ALL", "hospital"),
    ("Ascension Health",      "ascension",         "Ascension_Careers",        "ALL", "hospital"),
    ("Kaiser Permanente",     "kp",                "KP_External_Careers",      "ALL", "hospital"),
    ("Mayo Clinic",           "mayo",              "Mayo_External_Careers",    "ALL", "academic"),
    ("Cleveland Clinic",      "clevelandclinic",   "Cleveland_Clinic_Careers", "ALL", "academic"),
    ("Tenet Healthcare",      "tenethealth",       "Tenet_Careers",            "ALL", "hospital"),
    ("Trinity Health",        "trinityhealth",     "Trinity_Careers",          "ALL", "hospital"),
    ("AdventHealth",          "adventhealth",      "AdventHealth_Careers",     "ALL", "hospital"),
    ("Banner Health",         "bannerhealth",      "Banner_Careers",           "ALL", "hospital"),
    ("Intermountain Health",  "intermountain",     "Intermountain_Careers",    "ALL", "hospital"),
    ("Providence Health",     "providence",        "Providence_Careers",       "ALL", "hospital"),
    ("Geisinger",             "geisinger",         "Geisinger_Careers",        "ALL", "hospital"),
    ("Dignity Health",        "dignityhealth",     "Dignity_Careers",          "ALL", "hospital"),
    ("Baylor Scott White",    "bswhealth",         "BSW_External_Careers",     "ALL", "hospital"),
    ("Johns Hopkins",         "hopkinsmedicine",   "JHM_External_Careers",     "ALL", "academic"),
    ("Mass General Brigham",  "massgeneralbrigham","MGB_External_Careers",     "ALL", "academic"),
    ("NYU Langone",           "nyulangone",        "NYU_External_Careers",     "ALL", "academic"),
    ("Northwell Health",      "northwell",         "Northwell_Careers",        "ALL", "hospital"),
    ("Advocate Health",       "advocatehealth",    "Advocate_Careers",         "ALL", "hospital"),
]

_WD_API = "https://{tenant}.wd1.myworkdayjobs.com/wday/cxs/{tenant}/{board}/jobs"


class WorkdayScraper(BaseScraper):
    source_name = "workday"
    source_type = "hospital"

    def fetch(self, states: list[str], terms: list[str]) -> list[RawJob]:
        targets = [
            (employer, tenant, board, emp_state if emp_state != "ALL" else None, emp_type)
            for employer, tenant, board, emp_state, emp_type in WORKDAY_TENANTS
            if emp_state == "ALL" or emp_state in states
        ]

        all_jobs: list[RawJob] = []
        with ThreadPoolExecutor(max_workers=min(len(targets), 20)) as pool:
            futures = {
                pool.submit(self._fetch_tenant, *t, states): t[0]
                for t in targets
            }
            for future in as_completed(futures):
                try:
                    all_jobs.extend(future.result())
                except Exception as e:
                    log.warning(f"Workday tenant failed: {e}")
        return all_jobs

    def _fetch_tenant(self, employer: str, tenant: str, board: str,
                      emp_state: str | None, emp_type: str, states: list[str]) -> list[RawJob]:
        url = _WD_API.format(tenant=tenant, board=board)
        jobs: list[RawJob] = []
        offset = 0
        limit = 20

        while True:
            data = self.post_json(url, {
                "appliedFacets": {},
                "limit": limit,
                "offset": offset,
                "searchText": "physician",
            })
            if not data:
                break

            postings = data.get("jobPostings", [])
            if not postings:
                break

            for jp in postings:
                title = jp.get("title", "")
                if not any(kw in title.lower() for kw in PHYSICIAN_KEYWORDS):
                    continue

                location = jp.get("locationsText", "")
                job_state = self._extract_state(location, emp_state, states)
                if not job_state:
                    continue

                path = jp.get("externalPath", "")
                job_url = f"https://{tenant}.wd1.myworkdayjobs.com/{board}{path}"
                city = location.split(",")[0].strip() if "," in location else location
                posted = jp.get("postedOn", "") or jp.get("startDate", "")

                jobs.append(RawJob(
                    source_name=self.source_name,
                    source_type=emp_type,
                    source_url=job_url,
                    title=title,
                    employer=employer,
                    employer_type="direct",
                    city=city,
                    state=job_state,
                    raw_text=f"{title} {location}",
                    short_summary=f"{title} at {employer} in {location}",
                    posted_date_raw=posted,
                ))

            if len(postings) < limit:
                break
            offset += limit

        if jobs:
            log.info(f"Workday {employer}: {len(jobs)} jobs")
        return jobs

    def _extract_state(self, location: str, emp_state: str | None, states: list[str]) -> str | None:
        loc_upper = location.upper()
        for state in states:
            if state.upper() in loc_upper:
                return state.upper()
        if emp_state and emp_state in states:
            return emp_state
        if emp_state:
            return emp_state
        return None
