"""
Workday ATS scraper — covers Duke, UNC, Atrium, MUSC, Prisma and any Workday tenant.
Uses Playwright since Workday renders via React.
"""
import asyncio
from typing import List, Optional
from src.models import Job
from src.logger import get_logger

log = get_logger(__name__)

PHYSICIAN_KEYWORDS = [
    "internal medicine", "hospitalist", "nocturnist", "primary care physician",
    "internist", "im physician", "general internist",
]


class WorkdayScraper:
    name = "Workday ATS"
    source_type = "direct_employer"
    rate_limit = 5.0

    def make_hash(self, title: str, employer: str, state: str, city: str = "") -> str:
        import hashlib
        raw = f"{title.lower().strip()}|{employer.lower().strip()}|{state.lower()}|{city.lower()}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def scrape_tenant(self, tenant: str, employer_name: str, state: str, city: str = "") -> List[Job]:
        """Scrape a single Workday tenant for physician jobs."""
        try:
            return asyncio.run(self._async_scrape(tenant, employer_name, state, city))
        except Exception as e:
            log.error(f"Workday {employer_name}: {e}")
            return []

    async def _async_scrape(self, tenant: str, employer_name: str, state: str, city: str) -> List[Job]:
        from playwright.async_api import async_playwright
        jobs = []
        url = f"https://{tenant}.wd1.myworkdayjobs.com/en-US/External_Career_Site"
        search_terms = ["internal medicine", "hospitalist", "physician"]

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()

            for term in search_terms:
                try:
                    await page.goto(url, timeout=30000, wait_until="networkidle")
                    await asyncio.sleep(2)

                    search_box = page.locator("input[type='text'], input[placeholder*='search' i], input[aria-label*='search' i]").first
                    if await search_box.count() > 0:
                        await search_box.fill(term)
                        await search_box.press("Enter")
                        await asyncio.sleep(3)

                    job_links = await page.locator("a[href*='job/'], li[class*='job'], [data-automation-id*='jobTitle']").all()
                    for link in job_links[:50]:
                        try:
                            title = await link.inner_text()
                            href = await link.get_attribute("href") or ""
                            if not title or not any(kw in title.lower() for kw in PHYSICIAN_KEYWORDS):
                                continue
                            apply_url = href if href.startswith("http") else f"https://{tenant}.wd1.myworkdayjobs.com{href}"
                            full_text = await page.locator("body").inner_text()
                            jobs.append(Job(
                                source_name=f"{employer_name} (Workday)",
                                source_type=self.source_type,
                                source_url=url,
                                apply_url=apply_url,
                                title=title.strip(),
                                employer=employer_name,
                                city=city,
                                state=state,
                                visa_text="",
                                short_summary=title.strip(),
                                full_text_hash=self.make_hash(title.strip(), employer_name, state, city),
                            ))
                        except Exception:
                            continue
                except Exception as e:
                    log.debug(f"Workday {employer_name} term '{term}': {e}")
                    continue

            await browser.close()
        return jobs

    def scrape(self, state: str, terms: List[str]) -> List[Job]:
        """Scrape all Workday tenants configured for the given state."""
        import yaml
        from pathlib import Path
        cfg_path = Path(__file__).parent.parent.parent / "config" / "states.yaml"
        with open(cfg_path) as f:
            states_cfg = yaml.safe_load(f)

        jobs = []
        state_data = states_cfg.get("states", {}).get(state, {})
        for employer in state_data.get("key_employers", []):
            if employer.get("ats") == "workday" and employer.get("workday_tenant"):
                tenant = employer["workday_tenant"]
                name = employer["name"]
                log.info(f"Scraping Workday: {name} ({tenant})")
                jobs.extend(self.scrape_tenant(tenant, name, state))
        return jobs
