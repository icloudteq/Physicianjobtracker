from src.models import Job

PRIORITY_STATES = {"NC", "SC"}

WEIGHTS = {
    "h1b_confirmed": 30,
    "h1b_possible": 15,
    "j1_confirmed": 25,
    "j1_possible": 12,
    "waiver_likely": 20,
    "salary_posted": 10,
    "priority_state": 20,
    "direct_employer": 8,
    "academic": 5,
    "fqhc_rural": 8,
}


def score_job(job: Job) -> tuple[float, str]:
    """Returns (score, label). Label: high / medium / normal / low."""
    score = 0.0

    if job.h1b_status == "confirmed":
        score += WEIGHTS["h1b_confirmed"]
    elif job.h1b_status == "possible":
        score += WEIGHTS["h1b_possible"]

    if job.j1_status == "confirmed":
        score += WEIGHTS["j1_confirmed"]
    elif job.j1_status == "possible":
        score += WEIGHTS["j1_possible"]

    if job.waiver_status == "likely":
        score += WEIGHTS["waiver_likely"]

    if job.salary_min and job.salary_min > 0:
        score += WEIGHTS["salary_posted"]

    if job.state in PRIORITY_STATES:
        score += WEIGHTS["priority_state"]

    if job.source_type == "direct_employer":
        score += WEIGHTS["direct_employer"]

    title_lower = job.title.lower()
    if any(t in title_lower for t in ["faculty", "academic", "professor", "associate professor"]):
        score += WEIGHTS["academic"]

    employer_lower = job.employer.lower()
    if any(t in employer_lower for t in ["fqhc", "community health", "rural", "va ", "veterans"]):
        score += WEIGHTS["fqhc_rural"]

    if score >= 60:
        label = "high"
    elif score >= 35:
        label = "medium"
    elif score >= 15:
        label = "normal"
    else:
        label = "low"

    return round(score, 2), label
