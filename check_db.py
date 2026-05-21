import sys, os
sys.path.insert(0, r'C:\Users\NickG\source\repos\physician_job_tracker')
os.chdir(r'C:\Users\NickG\source\repos\physician_job_tracker')
from src.db import get_session, Job
from src.ranker import score_job
from src.models import RawJob
from sqlalchemy import text

s = get_session()
jobs = s.query(Job).all()
updated = 0
for j in jobs:
    raw = RawJob(source_name=j.source_name, source_type=j.source_type,
                 source_url=j.source_url or "", title=j.title, employer=j.employer,
                 city=j.city or "", state=j.state, raw_text=j.short_summary or "")
    enriched = {"salary_min": j.salary_min, "salary_max": j.salary_max,
                "h1b_status": j.h1b_status, "j1_status": j.j1_status,
                "contact_email": j.contact_email, "contact_name": j.contact_name}
    score, label = score_job(raw, enriched)
    j.priority_score = score
    j.priority_label = label
    updated += 1
s.commit()
hi = s.query(Job).filter_by(priority_label="HIGH").count()
med = s.query(Job).filter_by(priority_label="MEDIUM").count()
nc_hi = s.execute(text("SELECT COUNT(*) FROM jobs WHERE priority_label='HIGH' AND state='NC'")).scalar()
sc_hi = s.execute(text("SELECT COUNT(*) FROM jobs WHERE priority_label='HIGH' AND state='SC'")).scalar()
print(f"Re-scored {updated} jobs. HIGH={hi} (NC={nc_hi}, SC={sc_hi}) MEDIUM={med}")
s.close()
