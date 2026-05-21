from src.models import RawJob

PREFERRED_STATES = {"NC", "SC"}

_ACADEMIC_KEYWORDS = {"university", "academic", "medical school", "college", "faculty"}
_FQHC_KEYWORDS = {"fqhc", "community health", "rural health", "federally qualified"}
_VA_KEYWORDS = {"veterans affairs", " va ", "va hospital", "va medical"}
_HOSPITALIST_KEYWORDS = {"hospitalist", "nocturnist"}
_RECRUITER_KEYWORDS = {"staffing", "recruiting", "search group", "placement"}


def score_job(raw: RawJob, enriched: dict) -> tuple[float, str]:
    score = 0.0

    # NC/SC preferred states — highest signal
    if (raw.state or "").upper() in PREFERRED_STATES:
        score += 20

    # Salary posted
    if enriched.get("salary_min") or enriched.get("salary_max"):
        score += 15

    # H1B confirmed
    if enriched.get("h1b_status") == "confirmed":
        score += 20
    elif enriched.get("h1b_status") == "possible":
        score += 5

    # J1 confirmed
    if enriched.get("j1_status") == "confirmed":
        score += 15
    elif enriched.get("j1_status") == "possible":
        score += 4

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

    label = "HIGH" if score >= 60 else ("MEDIUM" if score >= 30 else "LOW")
    return score, label
