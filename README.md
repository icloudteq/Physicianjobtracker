# Physician Job Intelligence Tool

Private daily physician job search tool for Internal Medicine position tracking.

## Quick Start

### 1. Install dependencies
```bash
cd physician_job_tracker
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure
```bash
cp .env.example .env
# Edit .env with your name/email
```

### 3. Launch the Web Dashboard
```bash
streamlit run src/dashboard.py
```
Opens at http://localhost:8501

### 4. Or run from command line
```bash
python -m src.main --states NC SC --terms "Internal Medicine Physician" "Hospitalist"
```

---

## Features

| Feature | Status |
|---------|--------|
| DocCafe scraper | ✅ Active |
| HospitalRecruiting scraper | ✅ Active |
| NEJM CareerCenter scraper | ✅ Active |
| Health eCareers scraper | ✅ Active |
| JAMA Career Center scraper | ✅ Active |
| ACP Career Connection scraper | ✅ Active |
| Workday ATS (Duke, UNC, Atrium, MUSC, Prisma) | ✅ Active |
| iCIMS ATS (Novant, Cone, Roper) | ✅ Active |
| Generic hospital career pages | ✅ Active |
| PracticeLink | ⚠️ Manual CSV import only |
| PracticeMatch | ⚠️ Manual CSV import only |
| LinkedIn / Indeed | ⚠️ Manual CSV import only |
| Visa classification (H1B/J1) | ✅ Active |
| Salary parsing | ✅ Active |
| Priority scoring | ✅ Active |
| Daily CSV export | ✅ Active |
| Gmail draft creation | ✅ Active |
| Streamlit web dashboard | ✅ Active |

## Priority States
- **NC (North Carolina)** — High priority, bonus score
- **SC (South Carolina)** — High priority, bonus score

## Manual CSV Import (PracticeLink, PracticeMatch, etc.)

1. Export jobs from PracticeLink/PracticeMatch to CSV
2. Drop the file in `data/manual_imports/`
3. Run search — importer processes automatically

Required columns: `title`, `employer`, `state`
Optional: `city`, `salary_text`, `visa_text`, `apply_url`

## Gmail Setup

1. Go to Google Cloud Console → Enable Gmail API
2. Create OAuth 2.0 credentials (Desktop app type)
3. Download as `credentials.json` in project root
4. First run will open browser for auth

Drafts are NEVER auto-sent.

## Exports

All exports saved to `data/exports/`:
- `physician_jobs_YYYY-MM-DD.csv` — All jobs
- `high_priority_jobs_YYYY-MM-DD.csv` — High/medium priority
- `daily_summary_YYYY-MM-DD.txt` — Text summary report

## Daily Automation (Windows Task Scheduler)

Create a scheduled task:
```
Action: python -m src.main --states NC SC
Trigger: Daily at 7:00 AM
Working dir: C:\Users\NickG\physician_job_tracker
```

## Legal / Safe Use

- Only public job listings scraped
- No login walls, CAPTCHAs, or paywalls bypassed
- Short summaries only stored (not full job descriptions)
- Original source URL always preserved
- Gmail drafts only — never auto-sent
- Blocked sources are logged and skipped
