import re
from typing import Optional, Tuple


_SALARY_PATTERNS = [
    r"\$\s*([\d,]+)\s*[–\-to]+\s*\$?\s*([\d,]+)\s*[kK]?",
    r"\$\s*([\d,]+)[kK]\s*[–\-to]+\s*\$?\s*([\d,]+)[kK]",
    r"([\d,]+)\s*[–\-to]+\s*([\d,]+)\s*(?:thousand|k)\b",
    r"\$\s*([\d,]+)\s*(?:per year|annually|\/yr|\/year)",
    r"([\d]{3},[\d]{3})\s*[–\-to]+\s*([\d]{3},[\d]{3})",
]

_EXTRACT_PATTERN = re.compile(
    r"(?:salary|compensation|pay|income|earning)[^$\d]*"
    r"(\$[\d,\.]+[kKmM]?\s*(?:[–\-to]+\s*\$?[\d,\.]+[kKmM]?)?)",
    re.IGNORECASE,
)


def _parse_num(s: str) -> float:
    s = s.replace(",", "").strip()
    val = float(s)
    if val < 1000:
        val *= 1000
    return val


def parse_salary(text: str) -> Tuple[Optional[float], Optional[float], str]:
    """Returns (salary_min, salary_max, salary_text_snippet)."""
    if not text:
        return None, None, ""

    for pattern in _SALARY_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            groups = m.groups()
            try:
                low = _parse_num(groups[0])
                if len(groups) > 1 and groups[1]:
                    high = _parse_num(groups[1])
                    snippet = m.group(0).strip()
                    return min(low, high), max(low, high), snippet
                return low, low, m.group(0).strip()
            except (ValueError, IndexError):
                continue

    snippet_match = _EXTRACT_PATTERN.search(text)
    snippet = snippet_match.group(1) if snippet_match else ""
    return None, None, snippet
