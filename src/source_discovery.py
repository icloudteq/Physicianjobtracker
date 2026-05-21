import time
from urllib.parse import urlparse

from duckduckgo_search import DDGS

from src.db import Employer, get_session
from src.logger import get_logger
from src.scrapers.base import check_robots

log = get_logger("source_discovery")

_QUERY_TEMPLATES = [
    '"{specialty}" jobs "{state_name}" hospital careers',
    '"{specialty}" physician "{state_name}" health system site:careers',
    'H1B "{specialty}" physician "{state_name}" hospital',
    'J1 waiver "{specialty}" physician "{state_name}"',
    '"{specialty}" physician "{state_name}" university faculty jobs',
]

_STATE_NAMES = {
    "NC": "North Carolina", "SC": "South Carolina", "TX": "Texas",
    "CA": "California", "NY": "New York", "FL": "Florida",
    "GA": "Georgia", "VA": "Virginia", "OH": "Ohio", "PA": "Pennsylvania",
    "IL": "Illinois", "MI": "Michigan", "TN": "Tennessee", "AL": "Alabama",
    "MS": "Mississippi", "LA": "Louisiana", "AR": "Arkansas", "OK": "Oklahoma",
    "AZ": "Arizona", "NM": "New Mexico", "CO": "Colorado", "WA": "Washington",
    "OR": "Oregon", "MN": "Minnesota", "WI": "Wisconsin", "NJ": "New Jersey",
    "MD": "Maryland", "MA": "Massachusetts", "IN": "Indiana", "MO": "Missouri",
}

_CAREER_INDICATORS = [
    "careers", "jobs", "employment", "work-with-us", "join-our-team",
    "opportunities", "physician-careers", "physician-jobs",
]

_SKIP_DOMAINS = {
    "indeed.com", "linkedin.com", "glassdoor.com", "ziprecruiter.com",
    "monster.com", "careerbuilder.com", "simplyhired.com", "dice.com",
    "facebook.com", "twitter.com", "instagram.com", "reddit.com",
    "wikipedia.org", "yelp.com",
}


def discover_employers(states: list[str], terms: list[str], max_per_query: int = 5) -> list[dict]:
    session = get_session()
    found = []

    specialties = list({t.split()[0] + " " + t.split()[1] if len(t.split()) > 1 else t for t in terms[:3]})

    for state in states:
        state_name = _STATE_NAMES.get(state.upper(), state)
        for specialty in specialties[:2]:
            for template in _QUERY_TEMPLATES[:3]:
                query = template.format(specialty=specialty, state_name=state_name)
                try:
                    with DDGS() as ddgs:
                        results = list(ddgs.text(query, max_results=max_per_query))
                    for r in results:
                        url = r.get("href", "")
                        if not url:
                            continue
                        domain = urlparse(url).netloc.lower().replace("www.", "")
                        if any(skip in domain for skip in _SKIP_DOMAINS):
                            continue
                        if not any(ind in url.lower() for ind in _CAREER_INDICATORS):
                            continue
                        if not check_robots(url):
                            continue
                        existing = session.query(Employer).filter_by(careers_url=url).first()
                        if not existing:
                            emp = Employer(
                                employer_name=r.get("title", domain)[:100],
                                careers_url=url,
                                state=state.upper(),
                                employer_type="unknown",
                            )
                            session.add(emp)
                            session.commit()
                            found.append({"name": emp.employer_name, "url": url, "state": state})
                            log.info(f"Discovered: {url}")
                    time.sleep(1)
                except Exception as e:
                    log.warning(f"Discovery search error: {e}")
    session.close()
    return found
