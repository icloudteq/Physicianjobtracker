import re
from typing import Optional

_H1B = re.compile(r'\bH[-\s]?1[-\s]?B\b', re.IGNORECASE)
_J1 = re.compile(r'\bJ[-\s]?1\b', re.IGNORECASE)
_CONRAD = re.compile(r'\bConrad\s*30\b', re.IGNORECASE)
_POSSIBLE = re.compile(
    r'visa\s+sponsorship|immigration\s+assistance|sponsorship\s+available|we\s+sponsor',
    re.IGNORECASE
)
_NO = re.compile(
    r'no\s+visa\s+sponsorship|unable\s+to\s+sponsor|'
    r'must\s+be\s+authorized\s+to\s+work\s+without\s+sponsorship|'
    r'will\s+not\s+sponsor',
    re.IGNORECASE
)


def classify_visa(text: str) -> dict:
    """
    Returns dict with keys: h1b_status, j1_status, waiver_status, visa_text.
    All statuses: confirmed | possible | no | unknown
    """
    if not text:
        return {"h1b_status": "unknown", "j1_status": "unknown",
                "waiver_status": "unknown", "visa_text": None}

    # Use full text for detail pages (up to 8k), short for listing cards
    snippet = text[:8000]

    h1b = "unknown"
    j1 = "unknown"
    waiver = "unknown"

    if _NO.search(snippet):
        h1b = "no"
        j1 = "no"
    else:
        if _H1B.search(snippet):
            h1b = "confirmed"
        if _J1.search(snippet) or _CONRAD.search(snippet):
            j1 = "confirmed"
        if _CONRAD.search(snippet):
            waiver = "likely"
        if h1b == "unknown" and j1 == "unknown" and _POSSIBLE.search(snippet):
            h1b = "possible"
            j1 = "possible"

    # Extract the sentence containing visa info for display
    visa_text = None
    if h1b != "unknown" or j1 != "unknown":
        for pattern in (_H1B, _J1, _CONRAD, _POSSIBLE, _NO):
            m = pattern.search(snippet)
            if m:
                start = max(0, m.start() - 80)
                end = min(len(snippet), m.end() + 120)
                visa_text = snippet[start:end].strip()
                break

    return {
        "h1b_status": h1b,
        "j1_status": j1,
        "waiver_status": waiver,
        "visa_text": visa_text,
    }
