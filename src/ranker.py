from src.models import RawJob

PREFERRED_STATES = {"NC", "SC"}
NEARBY_STATES = {"VA", "GA", "TN"}  # neighboring — partial credit

_ACADEMIC_KEYWORDS = {"university", "academic", "medical school", "college", "faculty"}
_FQHC_KEYWORDS = {"fqhc", "community health", "rural health", "federally qualified"}
_VA_KEYWORDS = {"veterans affairs", " va ", "va hospital", "va medical"}
_HOSPITALIST_KEYWORDS = {"hospitalist", "nocturnist"}
_RECRUITER_KEYWORDS = {"staffing", "recruiting", "search group", "placement"}


def score_job(raw: RawJob, enriched: dict) -> tuple[float, str]:
    score = 0.0

    state_upper = (raw.state or "").upper()
    if state_upper in PREFERRED_STATES:
        score += 20
    elif state_upper in NEARBY_STATES:
        score += 8

    # Salary posted
    if enriched.get("salary_min") or enriched.get("salary_max"):
        score += 15

    # H1B confirmed in job text
    if enriched.get("h1b_status") == "confirmed":
        score += 20
    elif enriched.get("h1b_status") == "possible":
        # DOL LCA match is strong evidence; generic "possible" from text is weaker
        dol_match = enriched.get("dol_salary_min") is not None
        score += 12 if dol_match else 5

    # J1 confirmed
    if enriched.get("j1_status") == "confirmed":
        score += 15
    elif enriched.get("j1_status") == "possible":
        score += 4

    # DOL salary data available (employer has H1B filings = salary transparency)
    if enriched.get("dol_salary_min") and not (enriched.get("salary_min")):
        score += 5  # bonus for DOL salary data when posted salary missing

    # Direct employer (not recruiter)
    employer_lower = raw.employer.lower()
    if not any(k in employer_lower for k in _RECRUITER_KEYWORDS):
        score += 10

    # Academic / university
    if any(k in employer_lower for k in _ACADEMIC_KEYWORDS):
        score += 8

    # FQHC / rural / underserved
    if any(k in employer_lower for k in _FQHC_KEYWORDS):
        score += 8

    # VA hospital
    if any(k in employer_lower for k in _VA_KEYWORDS):
        score += 5

    # Hospitalist / Nocturnist title match
    title_lower = (raw.title or "").lower()
    if any(k in title_lower for k in _HOSPITALIST_KEYWORDS):
        score += 5

    # Contact info present
    if enriched.get("contact_email") or enriched.get("contact_name"):
        score += 10

    label = "HIGH" if score >= 40 else ("MEDIUM" if score >= 20 else "LOW")
    return score, label
