import time
import urllib.robotparser
from abc import ABC, abstractmethod
from typing import Optional
from urllib.parse import urlparse

import httpx

from src.logger import get_logger
from src.models import RawJob

BLOCKED_SIGNALS = [
    "just a moment", "checking your browser", "cloudflare",
    "captcha", "access denied", "403 forbidden", "please verify",
    "sign in to continue", "login required",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_robots_cache: dict[str, bool] = {}


def check_robots(url: str, user_agent: str = "*") -> bool:
    """Returns True if scraping is allowed."""
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    if robots_url in _robots_cache:
        return _robots_cache[robots_url]

    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
        allowed = rp.can_fetch(user_agent, url)
    except Exception:
        allowed = True  # if robots.txt unreachable, assume allowed

    _robots_cache[robots_url] = allowed
    return allowed


def is_blocked_response(html: str) -> bool:
    lower = html.lower()
    return any(signal in lower for signal in BLOCKED_SIGNALS)


class BaseScraper(ABC):
    source_name: str = ""
    source_type: str = "job_board"
    scrape_method: str = "httpx"
    enabled: bool = True

    def __init__(self):
        self.log = get_logger(self.__class__.__name__)

    @abstractmethod
    def fetch(self, states: list[str], terms: list[str]) -> list[RawJob]:
        ...

    def get(self, url: str, params: dict | None = None, retries: int = 2) -> Optional[str]:
        if not check_robots(url):
            self.log.warning(f"robots.txt disallows: {url}")
            return None

        for attempt in range(retries + 1):
            try:
                with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
                    resp = client.get(url, params=params)
                    resp.raise_for_status()
                    html = resp.text
                    if is_blocked_response(html):
                        self.log.warning(f"Blocked response detected: {url}")
                        return None
                    return html
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (403, 429):
                    self.log.warning(f"HTTP {e.response.status_code} on {url}")
                    return None
                if attempt < retries:
                    time.sleep(2 ** attempt)
            except Exception as e:
                if attempt < retries:
                    time.sleep(2 ** attempt)
                else:
                    self.log.error(f"Failed to fetch {url}: {e}")
        return None
