"""
DOL H1B LCA Disclosure Data salary lookup.
Public data required by law: https://www.dol.gov/agencies/eta/foreign-labor/performance
SOC codes: 29-1215 (Family Medicine), 29-1216 (Internal Medicine), 29-1229 (Physicians All Other)
"""
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
import pandas as pd
from bs4 import BeautifulSoup
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from src.db import DolLcaCache, get_session
from src.logger import get_logger

log = get_logger("dol_salary")

DOL_PERFORMANCE_URL = "https://www.dol.gov/agencies/eta/foreign-labor/performance"
SOC_CODES = ["29-1215", "29-1216", "29-1229", "29-1228"]
_WAGE_UNITS = {"year": 1, "annual": 1, "month": 12, "bi-weekly": 26, "week": 52, "hour": 2080}


def _find_latest_lca_url() -> Optional[str]:
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(DOL_PERFORMANCE_URL)
            resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "LCA_Disclosure_Data" in href and href.endswith(".xlsx"):
                return href if href.startswith("http") else f"https://www.dol.gov{href}"
    except Exception as e:
        log.error(f"Could not find LCA URL: {e}")
    return None


def _download_lca(url: str, dest_dir: str) -> Optional[str]:
    filename = url.split("/")[-1]
    dest = Path(dest_dir) / filename
    if dest.exists():
        log.info(f"LCA file already cached: {dest}")
        return str(dest)
    log.info(f"Downloading LCA data from {url} ...")
    try:
        with httpx.Client(timeout=300, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
        log.info(f"Downloaded {dest}")
        return str(dest)
    except Exception as e:
        log.error(f"LCA download failed: {e}")
        return None


def _annualize(wage: float, unit: str) -> int:
    multiplier = _WAGE_UNITS.get(unit.lower().strip(), 1)
    return int(wage * multiplier)


def load_lca_into_db(xlsx_path: str, session: Session) -> int:
    log.info(f"Loading LCA data from {xlsx_path}")
    try:
        df = pd.read_excel(xlsx_path, engine="openpyxl", dtype=str)
        df.columns = [c.strip().upper() for c in df.columns]

        soc_col = next((c for c in df.columns if "SOC" in c and "CODE" in c), None)
        emp_col = next((c for c in df.columns if "EMPLOYER" in c and "NAME" in c), None)
        state_col = next((c for c in df.columns if "EMPLOYER_STATE" in c or "WORKSITE_STATE" in c), None)
        title_col = next((c for c in df.columns if "JOB_TITLE" in c), None)
        wage_from_col = next((c for c in df.columns if "WAGE_RATE_OF_PAY_FROM" in c or "WAGE_FROM" in c), None)
        wage_to_col = next((c for c in df.columns if "WAGE_RATE_OF_PAY_TO" in c or "WAGE_TO" in c), None)
        wage_unit_col = next((c for c in df.columns if "WAGE_UNIT" in c), None)
        status_col = next((c for c in df.columns if "CASE_STATUS" in c), None)

        if not all([soc_col, emp_col, wage_from_col]):
            log.error(f"Missing expected columns. Found: {list(df.columns[:20])}")
            return 0

        year = int(xlsx_path.split("FY")[1][:4]) if "FY" in xlsx_path else datetime.utcnow().year

        # Filter to physician SOC codes and certified cases
        mask = df[soc_col].str.startswith(tuple(SOC_CODES), na=False)
        if status_col:
            mask &= df[status_col].str.upper().str.contains("CERTIFIED", na=False)
        df_phys = df[mask].copy()

        log.info(f"Found {len(df_phys)} physician LCA records")
        count = 0
        for _, row in df_phys.iterrows():
            try:
                wage_from = float(str(row[wage_from_col]).replace(",", "").replace("$", "") or 0)
                wage_to = float(str(row.get(wage_to_col, 0) or wage_from).replace(",", "").replace("$", "") or wage_from)
                unit = str(row.get(wage_unit_col, "Year") or "Year")
                annual_min = _annualize(wage_from, unit)
                annual_max = _annualize(wage_to, unit)

                if annual_min < 50000 or annual_min > 1500000:
                    continue

                employer = str(row[emp_col] or "").strip()[:200]
                state = str(row[state_col] or "").strip().upper()[:2] if state_col else ""
                title = str(row[title_col] or "").strip()[:200] if title_col else ""

                entry = DolLcaCache(
                    employer_name=employer,
                    job_title=title,
                    state=state,
                    wage_min=annual_min,
                    wage_max=annual_max,
                    lca_year=year,
                )
                session.add(entry)
                count += 1
                if count % 1000 == 0:
                    session.commit()
            except Exception:
                continue

        session.commit()
        log.info(f"Loaded {count} LCA records into DB")
        return count
    except Exception as e:
        log.error(f"Failed to load LCA data: {e}")
        return 0


def ensure_lca_loaded(refresh_days: int = 30) -> bool:
    dol_dir = os.getenv("DOL_DATA_DIR", "data/dol_lca")
    Path(dol_dir).mkdir(parents=True, exist_ok=True)

    session = get_session()
    count = session.query(DolLcaCache).count()
    session.close()

    if count > 0:
        log.info(f"LCA cache has {count} records, skipping download")
        return True

    url = _find_latest_lca_url()
    if not url:
        log.warning("Could not find LCA download URL")
        return False

    path = _download_lca(url, dol_dir)
    if not path:
        return False

    session = get_session()
    load_lca_into_db(path, session)
    session.close()
    return True


def lookup_salary(employer: str, state: str, session: Session) -> dict:
    """Fuzzy match employer name in DOL cache. Returns salary dict."""
    candidates = (
        session.query(DolLcaCache)
        .filter(DolLcaCache.state == state.upper())
        .all()
    )

    best_score = 0
    best_match = None
    for c in candidates:
        score = fuzz.token_set_ratio(employer.lower(), c.employer_name.lower())
        if score > best_score:
            best_score = score
            best_match = c

    if best_match and best_score >= 80:
        return {
            "dol_salary_min": best_match.wage_min,
            "dol_salary_max": best_match.wage_max,
            "dol_salary_year": best_match.lca_year,
            "dol_case_count": best_match.case_count,
        }
    return {}

