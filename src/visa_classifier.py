import re
import yaml
from pathlib import Path

_cfg_path = Path(__file__).parent.parent / "config" / "search_terms.yaml"
with open(_cfg_path) as f:
    _cfg = yaml.safe_load(f)

_TERMS = _cfg["visa_terms"]


def _matches(text: str, terms: list[str]) -> bool:
    t = text.lower()
    return any(term.lower() in t for term in terms)


def classify_h1b(text: str) -> str:
    """Returns: confirmed | possible | no | unknown"""
    if not text:
        return "unknown"
    if _matches(text, _TERMS["no"]):
        return "no"
    if _matches(text, _TERMS["h1b"]):
        return "confirmed"
    if _matches(text, _TERMS["possible"]):
        return "possible"
    return "unknown"


def classify_j1(text: str) -> str:
    """Returns: confirmed | possible | no | unknown"""
    if not text:
        return "unknown"
    if _matches(text, _TERMS["no"]):
        return "no"
    if _matches(text, _TERMS["j1"]):
        return "confirmed"
    if _matches(text, _TERMS["possible"]):
        return "possible"
    return "unknown"


def classify_waiver(text: str) -> str:
    """Returns: likely | unknown"""
    if not text:
        return "unknown"
    waiver_terms = ["j1 waiver", "j-1 waiver", "conrad 30", "conrad 20", "waiver sponsor"]
    if any(t in text.lower() for t in waiver_terms):
        return "likely"
    return "unknown"


def classify_all(visa_text: str) -> dict:
    return {
        "h1b_status": classify_h1b(visa_text),
        "j1_status": classify_j1(visa_text),
        "waiver_status": classify_waiver(visa_text),
    }
