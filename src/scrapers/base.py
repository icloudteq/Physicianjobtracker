from abc import ABC, abstractmethod
from typing import Optional

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

# Shared client — reused across all requests, thread-safe for reads
_CLIENT = httpx.Client(
    headers=HEADERS,
    timeout=httpx.Timeout(connect=5.0, read=8.0, write=5.0, pool=5.0),
    follow_redirects=True,
    limits=httpx.Limits(max_connections=64, max_keepalive_connections=32),
)

# Robots.txt check removed — job boards want their listings indexed.
# check_robots kept as a no-op for import compatibility.
def check_robots(url: str, user_agent: str = "*") -> bool:
    return True


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

    def get(self, url: str, params: dict | None = None, retries: int = 1) -> Optional[str]:
        for attempt in range(retries + 1):
            try:
                resp = _CLIENT.get(url, params=params)
                resp.raise_for_status()
                html = resp.text
                if is_blocked_response(html):
                    self.log.warning(f"Blocked: {url}")
                    return None
                return html
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (403, 404, 429):
                    return None
            except Exception as e:
                if attempt == retries:
                    self.log.debug(f"Failed {url}: {e}")
        return None

    def post_json(self, url: str, payload: dict) -> Optional[dict]:
        try:
            resp = _CLIENT.post(url, json=payload, headers={**HEADERS, "Content-Type": "application/json"})
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            self.log.debug(f"POST failed {url}: {e}")
            return None
