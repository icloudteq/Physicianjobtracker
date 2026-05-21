import re
from typing import Optional


_RANGE = re.compile(
    r'\$(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(?:–|-|to)\s*\$(\d{1,3}(?:,\d{3})*(?:\.\d+)?)',
    re.IGNORECASE
)
_SINGLE = re.compile(r'\$(\d{1,3}(?:,\d{3})+)', re.IGNORECASE)
_SHORTHAND = re.compile(r'\$(\d{2,3})[kK]\b')
_UP_TO = re.compile(r'up\s+to\s+\$(\d{1,3}(?:,\d{3})*)', re.IGNORECASE)
_PER_HOUR = re.compile(r'\$(\d{2,3}(?:\.\d+)?)\s*/?\s*(?:per\s+)?hour', re.IGNORECASE)


def _clean(v: str) -> int:
    return int(float(v.replace(",", "")))


_HOURLY_CONTEXT = re.compile(r'per\s+hour|/\s*hour|\bhr\b|\bph\b|hourly', re.IGNORECASE)


def _is_hourly(text: str, match_start: int, match_end: int) -> bool:
    """Check if a salary match is in a per-hour context."""
    window = text[max(0, match_start - 10):min(len(text), match_end + 30)]
    return bool(_HOURLY_CONTEXT.search(window))


def parse_salary(text: str) -> tuple[Optional[int], Optional[int], Optional[str]]:
    """Return (salary_min, salary_max, raw_snippet) or (None, None, None)."""
    if not text:
        return None, None, None

    m = _RANGE.search(text)
    if m:
        lo, hi = _clean(m.group(1)), _clean(m.group(2))
        lo, hi = min(lo, hi), max(lo, hi)
        # Annualize if values look like hourly rates (< $2,000)
        if hi < 2000 or _is_hourly(text, m.start(), m.end()):
            lo, hi = int(lo * 2080), int(hi * 2080)
        if hi > 50000:  # sanity: skip implausible ranges
            return lo, hi, m.group(0)

    m = _PER_HOUR.search(text)
    if m:
        hourly = float(m.group(1))
        annual = int(hourly * 2080)
        return annual, annual, m.group(0)

    m = _UP_TO.search(text)
    if m:
        hi = _clean(m.group(1))
        return None, hi, m.group(0)

    m = _SHORTHAND.search(text)
    if m:
        val = int(m.group(1)) * 1000
        return val, val, m.group(0)

    m = _SINGLE.search(text)
    if m:
        val = _clean(m.group(1))
        if val > 10000:
            return val, val, m.group(0)

    return None, None, None
