import re
from datetime import date, datetime, timedelta
from typing import Optional

_RELATIVE = re.compile(r'(\d+)\s+(day|week|month|hour)s?\s+ago', re.IGNORECASE)
_ISO = re.compile(r'(\d{4})-(\d{2})-(\d{2})')
_MDY = re.compile(r'(\w+ \d{1,2},?\s+\d{4})', re.IGNORECASE)

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_posted_date(text: str) -> Optional[date]:
    if not text:
        return None

    m = _RELATIVE.search(text)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        delta = {
            "hour": timedelta(hours=n),
            "day": timedelta(days=n),
            "week": timedelta(weeks=n),
            "month": timedelta(days=n * 30),
        }.get(unit, timedelta(days=0))
        return (datetime.utcnow() - delta).date()

    m = _ISO.search(text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    m = _MDY.search(text)
    if m:
        try:
            return datetime.strptime(m.group(1).replace(",", "").strip(), "%B %d %Y").date()
        except ValueError:
            pass
        try:
            return datetime.strptime(m.group(1).replace(",", "").strip(), "%b %d %Y").date()
        except ValueError:
            pass

    return None
