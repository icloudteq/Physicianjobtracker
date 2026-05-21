"""
Run once to seed employer career pages from sources.yaml into the DB.
python -m src.seed_employers
"""
from pathlib import Path

import yaml

from src.db import Employer, get_session
from src.logger import get_logger

log = get_logger("seed_employers")


def seed():
    cfg = yaml.safe_load(Path("config/sources.yaml").read_text())
    session = get_session()
    added = 0
    for emp in cfg.get("employers", []):
        name = emp["name"]
        url = emp.get("careers_url", "")
        state = emp.get("state", "ALL")
        etype = emp.get("employer_type", "hospital")

        if not url:
            continue

        existing = session.query(Employer).filter_by(employer_name=name).first()
        if not existing:
            session.add(Employer(
                employer_name=name,
                careers_url=url,
                state=state,
                employer_type=etype,
            ))
            added += 1

    session.commit()
    session.close()
    log.info(f"Seeded {added} employers")
    print(f"Seeded {added} employers into DB")


if __name__ == "__main__":
    seed()
