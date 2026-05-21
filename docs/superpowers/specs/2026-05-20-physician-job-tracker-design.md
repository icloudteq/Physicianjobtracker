# Physician Job Intelligence Tool — Design Spec
**Date:** 2026-05-20  
**Status:** Approved  
**Purpose:** Private daily job intelligence tool for Internal Medicine and Family Medicine physician job search across all 50 US states. Collects every available posting into one unified table showing salary, contact info (name/email/phone), and visa sponsorship status.

---

## 1. Overview

A local Python application that:
1. Scrapes 20–30+ public physician job boards and hospital career pages across all 50 states
2. Enriches every job with historical salary data from the DOL H1B LCA public database
3. Stores jobs in SQLite (deduped, enriched, ranked) with full salary history per employer
4. Extracts salary, contact info (name/email/phone), and posting date from every job
5. Classifies visa sponsorship signals (H1B/J1/none/unknown)
6. Runs automatically every 2 hours via APScheduler — no manual trigger needed
7. Sends desktop notifications when new jobs are found
8. Exports a daily master CSV — one row per job, all fields in one place
9. Creates Gmail draft emails for selected jobs
10. Provides a Streamlit dashboard with live auto-refresh

**Primary output:** One unified table/CSV with every job across all states — title, employer, city/state, salary (posted + historical DOL data), contact name, contact email, contact phone, H1B status, J1 status, posting date, source URL.

**Live updates:** Pipeline runs automatically every 2 hours via APScheduler. Streamlit dashboard auto-refreshes. Desktop notification on new jobs found.

**Legal constraints (hard rules, never bypass):**
- No login walls, CAPTCHA bypass, paywalls, Cloudflare bypass, or robots-restricted pages
- No scraping hidden recruiter emails or private contact data
- No fake accounts
- Store short summaries only — never full job descriptions
- Always store and display original source URL
- If a source blocks scraping: skip, log reason, continue
- Gmail drafts only — never auto-send

---

## 2. Architecture

```
Streamlit UI (src/dashboard.py)
        │
        ▼
    src/main.py  ←── CLI: python -m src.main --states TX NM --run
        │
   ┌────┴──────────────────────────────────────┐
   │           Pipeline Orchestrator            │
   │  1. state_search      → discover URLs      │
   │  2. scrapers          → raw job dicts      │
   │  3. db.py             → upsert jobs        │
   │  4. dedupe            → mark duplicates    │
   │  5. salary_parser     → enrich posted $   │
   │  6. dol_salary        → enrich hist. $    │
   │  7. contact_extractor → enrich contact    │
   │  8. visa_classifier   → enrich visa       │
   │  9. ranker            → priority score    │
   │  10. exporters        → master CSV        │
   │  11. notifier         → desktop alert     │
   │  12. gmail_drafts     → create drafts     │
   └────────────────────────────────────────────┘
        ↑
   APScheduler (runs every 2h, configurable)
   └────────────────────────────────────────────┘
        │
   SQLite (data/jobs.db via SQLAlchemy ORM)
```

Each stage is a pure function or class. No shared global state. The orchestrator calls stages in sequence. The Streamlit UI calls the orchestrator with user-selected params. Pipeline can also run headless (scheduled task).

---

## 3. Folder Structure

```
physician_job_tracker/
  .env.example
  .env                        # gitignored
  requirements.txt
  README.md
  config/
    sources.yaml              # enabled sources, hospital career URLs
    search_terms.yaml         # specialty terms, visa terms, candidate info
    states.yaml               # state configs with preferred cities
    email_templates.yaml      # email subject/body config
  data/
    jobs.db
    exports/                  # YYYY-MM-DD/ subdirs per run
    manual_imports/           # CSV files for gated sources
    logs/                     # per-run scrape logs
  docs/
    superpowers/
      specs/                  # this file
  src/
    __init__.py
    main.py                   # pipeline orchestrator + CLI entrypoint
    db.py                     # SQLAlchemy models + init_db()
    models.py                 # Pydantic models: RawJob, Job, ScrapeRun
    logger.py                 # structured logging to file + console
    dedupe.py                 # exact hash + RapidFuzz fuzzy dedup
    salary_parser.py          # regex salary extraction + normalization
    contact_extractor.py      # extract contact name/email/phone from public posting text
    visa_classifier.py        # strict regex visa signal classification
    ranker.py                 # priority scoring (0-100)
    state_search.py           # generate search queries per state+term
    source_discovery.py       # DuckDuckGo search → discover employer URLs
    dol_salary.py             # DOL H1B LCA public database salary lookup
    scheduler.py              # APScheduler background auto-run (every 2h)
    notifier.py               # Windows desktop notifications (new jobs found)
    gmail_drafts.py           # Gmail API v1 OAuth2 draft creation
    exporters.py              # master CSV + Jinja2 summary report
    dashboard.py              # Streamlit UI
    scrapers/
      __init__.py
      base.py                 # BaseScraper ABC
      doccafe.py
      practicelink.py
      practicematch_public.py # placeholder + CSV import path
      nejm.py
      health_ecareers.py
      jama_career.py
      hospital_recruiting.py
      generic_hospital.py     # reusable for any hospital career page
      google_search_import.py # manual search result CSV importer
      csv_importer.py         # generic CSV import for any gated source
  templates/
    daily_summary.txt         # Jinja2
    job_email_draft.txt       # Jinja2
```

---

## 4. Configuration Files

### config/states.yaml

All 50 US states configured. Each entry:
```yaml
states:
  TX:
    name: Texas
    search_enabled: true
  CA:
    name: California
    search_enabled: true
  NY:
    name: New York
    search_enabled: true
  # ... all 50 states follow the same pattern
  # search_enabled: false to pause a state without deleting config
```

Default: all 50 states enabled. User can toggle individual states off in the Streamlit Sources tab.

### config/search_terms.yaml
```yaml
specialty_terms:
  # Internal Medicine
  - Internal Medicine Physician
  - Hospitalist
  - Nocturnist
  - Primary Care Physician
  - Outpatient Internal Medicine
  - Academic Internal Medicine
  - Internal Medicine Faculty
  - IM Hospitalist
  - PCP Internal Medicine
  # Family Medicine
  - Family Medicine Physician
  - Family Practice Physician
  - Family Medicine Doctor
  - Family Physician
  - Family Medicine Faculty
  - Academic Family Medicine
  - Outpatient Family Medicine

visa_terms:
  h1b:
    - H1B
    - H-1B
    - H1-B
    - H-1B sponsorship
  j1:
    - J1
    - J-1
    - J1 waiver
    - J-1 waiver
    - Conrad 30
  possible:
    - visa sponsorship
    - immigration assistance
    - sponsorship available
  no:
    - no visa sponsorship
    - unable to sponsor
    - must be authorized to work without sponsorship

candidate:
  candidate_name: "[Candidate Name]"
  sender_name: "[Your Name]"
  sender_email: "[Your Email]"
  preferred_states: [NC, SC]
```

### config/sources.yaml
Contains:
- Per-source enable/disable flags and scrape method (`httpx` | `playwright` | `csv_only`)
- Pre-curated national employer career URLs (major health systems, academic medical centers, VA portals, FQHC networks across all 50 states)
  **NC/SC priority employers (pre-loaded):**
  - Duke Health, UNC Health, Atrium Health (Carolinas Medical), Novant Health, WakeMed, ECU Health (Vidant), Cone Health, CaroMont Health, Cape Fear Valley Health, FirstHealth of the Carolinas
  - MUSC (Medical University of SC), Prisma Health, Tidelands Health, Roper St. Francis, AnMed Health, Conway Medical Center, McLeod Health, Palmetto Health
  - VA medical centers: Durham VA, Fayetteville VA, Asheville VA, Salisbury VA, Columbia SC VA, Charleston SC VA
  - UNC School of Medicine, Duke School of Medicine, Wake Forest School of Medicine, MUSC faculty positions
  - National systems with large NC/SC presence: HCA Healthcare, Novant, Tenet, CommonSpirit
- Manual employer URL additions via Streamlit UI or direct YAML edit

---

## 5. Database Schema (SQLAlchemy ORM, SQLite)

### jobs
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| source_name | TEXT | |
| source_type | TEXT | job_board \| hospital \| academic \| fqhc \| va |
| source_url | TEXT | original listing URL (always stored) |
| apply_url | TEXT | direct apply link if different |
| title | TEXT | |
| employer | TEXT | |
| employer_type | TEXT | direct \| recruiter |
| city | TEXT | |
| state | TEXT | |
| specialty | TEXT | matched specialty term |
| job_type | TEXT | full_time \| part_time \| locum \| unknown |
| salary_text | TEXT | raw extracted salary snippet from posting |
| salary_min | INTEGER | annualized, from posting |
| salary_max | INTEGER | annualized, from posting |
| dol_salary_min | INTEGER | historical min wage from DOL LCA data |
| dol_salary_max | INTEGER | historical max wage from DOL LCA data |
| dol_salary_year | INTEGER | most recent DOL LCA year available |
| dol_case_count | INTEGER | number of LCA filings found for this employer+title |
| visa_text | TEXT | raw extracted visa snippet |
| h1b_status | TEXT | confirmed \| possible \| no \| unknown |
| j1_status | TEXT | confirmed \| possible \| no \| unknown |
| waiver_status | TEXT | likely \| unknown |
| contact_name | TEXT | only if publicly listed in posting |
| contact_email | TEXT | only if publicly listed in posting |
| contact_phone | TEXT | only if publicly listed in posting |
| posted_date | DATE | date job was posted, extracted from listing |
| posted_date_raw | TEXT | raw date string from source before parsing |
| short_summary | TEXT | ≤500 chars, no full description copy |
| full_text_hash | TEXT | SHA256(title+employer+city+state) |
| first_seen_at | DATETIME UTC | |
| last_seen_at | DATETIME UTC | |
| status | TEXT | new \| reviewed \| applied \| rejected \| expired |
| duplicate_group_id | TEXT | UUID linking near-duplicates |
| priority_score | REAL | 0.0–100.0 |
| priority_label | TEXT | HIGH \| MEDIUM \| LOW |
| manual_review_required | BOOLEAN | set if extraction uncertain |
| created_at | DATETIME UTC | |
| updated_at | DATETIME UTC | |

### employers
| Column | Type |
|---|---|
| id | INTEGER PK |
| employer_name | TEXT |
| website | TEXT |
| careers_url | TEXT |
| city | TEXT |
| state | TEXT |
| employer_type | TEXT |
| notes | TEXT |

### scrape_runs
| Column | Type |
|---|---|
| id | INTEGER PK |
| selected_states | TEXT (JSON) |
| selected_terms | TEXT (JSON) |
| source_name | TEXT |
| started_at | DATETIME UTC |
| finished_at | DATETIME UTC |
| jobs_found | INTEGER |
| new_jobs | INTEGER |
| duplicates_found | INTEGER |
| errors | TEXT |
| status | TEXT |

### gmail_drafts
| Column | Type |
|---|---|
| id | INTEGER PK |
| job_id | INTEGER FK |
| recipient_email | TEXT |
| subject | TEXT |
| draft_body | TEXT |
| gmail_draft_id | TEXT |
| created_at | DATETIME UTC |
| status | TEXT |

### dol_lca_cache
Local cache of downloaded DOL LCA records — avoids re-downloading on every run.

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| employer_name | TEXT | normalized |
| job_title | TEXT | normalized |
| state | TEXT | |
| wage_min | INTEGER | annualized |
| wage_max | INTEGER | annualized |
| lca_year | INTEGER | fiscal year of filing |
| case_count | INTEGER | filings found |
| fetched_at | DATETIME UTC | when this cache entry was built |

### manual_reviews
| Column | Type |
|---|---|
| id | INTEGER PK |
| job_id | INTEGER FK |
| reason | TEXT |
| reviewed | BOOLEAN |
| notes | TEXT |
| created_at | DATETIME UTC |

---

## 6. Scraper Design

### BaseScraper ABC (src/scrapers/base.py)
```python
class BaseScraper(ABC):
    source_name: str
    source_type: str
    scrape_method: str  # "httpx" | "playwright" | "csv_only"
    enabled: bool

    @abstractmethod
    def fetch(self, state: str, terms: list[str]) -> list[RawJob]: ...

    def is_blocked(self, response) -> bool:
        # Checks for CAPTCHA, Cloudflare challenge, login redirect
        ...

    def check_robots(self, url: str) -> bool:
        # Returns True if scraping allowed
        ...
```

### Source Coverage

| Source | Method | Fallback |
|---|---|---|
| DocCafe | HTTPX + BS4 | skip + log |
| NEJM CareerCenter | HTTPX + BS4 | skip + log |
| Health eCareers | HTTPX + BS4 | skip + log |
| JAMA Career Center | HTTPX + BS4 | skip + log |
| HospitalRecruiting.com | HTTPX + BS4 | skip + log |
| MDJobSite | HTTPX + BS4 | skip + log |
| PracticeLink | Playwright | CSV importer |
| PracticeMatch | Placeholder | CSV importer |
| LinkedIn/Indeed/ZipRecruiter | CSV importer only | — |
| Hospital career pages | generic_hospital.py | mark needs_manual_review |

### Generic Hospital Scraper
Handles:
- Career pages with job card lists
- Search pages with `?q=` or `?keyword=` params
- Location filter params
- Pagination (public pages only)
- Extracts: title, location, apply link, employer
- On failure: logs, marks `manual_review_required=True`, continues

---

## 7. State-Based Discovery

`state_search.py` generates search queries per state+term combination:
```
"Internal Medicine Physician jobs Texas hospital careers"
"Hospitalist jobs Texas health system careers"
"J1 waiver internal medicine physician Texas"
"H1B internal medicine physician Texas hospital"
"Internal Medicine faculty jobs Texas university"
"Nocturnist Internal Medicine Texas hospital"
```

`source_discovery.py`:
1. Runs queries via `duckduckgo-search` Python package (free, no API key)
2. Filters results: checks `robots.txt` for each new domain
3. Skips domains already in `employers` table
4. Saves new employer career URLs to `employers` table
5. Passes to `generic_hospital.py` for scraping

---

## 8. Deduplication (src/dedupe.py)

Two-pass:

**Pass 1 — Exact hash**
- Hash = SHA256(`title.lower() + employer.lower() + city.lower() + state`)
- O(1) lookup against `full_text_hash` in DB
- Exact match → skip insert, update `last_seen_at`

**Pass 2 — Fuzzy**
- RapidFuzz `token_sort_ratio` on `(title + " " + employer)`
- Threshold: 88
- Match → assign same `duplicate_group_id` (UUID)
- Only earliest-seen job in group shown by default in UI/exports

---

## 9. Visa Classification (src/visa_classifier.py)

Strict regex on extracted `visa_text` snippet (≤300 chars pulled from posting):

```python
H1B_CONFIRMED  = r'\bH[-\s]?1[-\s]?B\b'
J1_CONFIRMED   = r'\bJ[-\s]?1\b|\bConrad\s*30\b'
VISA_POSSIBLE  = r'visa sponsorship|immigration assistance|sponsorship available'
VISA_NO        = r'no visa sponsorship|unable to sponsor|must be authorized to work without sponsorship'
```

Rules (applied in order):
1. If H1B pattern → `h1b_status = confirmed`
2. If J1/Conrad pattern → `j1_status = confirmed`; if Conrad 30 → `waiver_status = likely`
3. If possible pattern (no specific type) → `h1b_status = possible`, `j1_status = possible`
4. If no pattern → `h1b_status = no`, `j1_status = no`
5. If no visa text found → all `unknown`

Never assume sponsorship. No inference beyond the text.

---

## 10. Salary Parser (src/salary_parser.py)

Regex patterns:
```python
r'\$(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(?:–|-|to)\s*\$(\d{1,3}(?:,\d{3})*)'  # range
r'\$(\d{1,3}(?:,\d{3})+)'   # single value
r'\$(\d{2,3})[kK]\b'        # shorthand (180k → 180,000)
r'up to \$(\d{1,3}(?:,\d{3})*)'  # up to X
```

Outputs:
- `salary_text`: raw matched snippet
- `salary_min`: integer (annualized)
- `salary_max`: integer (annualized, or same as min if single value)

---

## 11. Ranker (src/ranker.py)

Score 0–100, assigned at upsert time and recalculated on each scrape:

| Signal | Points |
|---|---|
| Salary posted | +15 |
| H1B confirmed | +20 |
| J1 confirmed | +15 |
| Direct employer (not recruiter) | +10 |
| Job in NC or SC (preferred states) | +20 |
| Contact info present (name/email/phone) | +10 |
| Academic / university employer | +8 |
| FQHC / rural / underserved | +8 |
| VA hospital | +5 |
| Title matches Hospitalist or Nocturnist | +5 |
| First seen today | +4 |

`priority_label`:
- HIGH: score ≥ 60
- MEDIUM: score 30–59
- LOW: score < 30

---

## 12. DOL Historical Salary Lookup (src/dol_salary.py)

**Source:** US Department of Labor H1B LCA (Labor Condition Application) Disclosure Data  
**URL:** `https://www.dol.gov/agencies/eta/foreign-labor/performance` (public, free, legally required to be disclosed)  
**Format:** Quarterly Excel/CSV downloads, also queryable via OFLC API

**What it provides:**
- Exact wage ranges employers offered H1B workers
- Searchable by employer name, job title, state, year
- Updated quarterly — most accurate public salary benchmark for physician H1B roles
- Shows if an employer has a history of H1B filings (strong sponsorship signal)

**How it works in our pipeline:**
1. On first run: download the most recent DOL LCA dataset (Excel, ~150MB) → store in `data/dol_lca/`
2. Parse into `dol_lca_cache` SQLite table (one-time import, ~5 min)
3. On each job upsert: lookup by normalized `(employer_name, state, specialty_group)` → fuzzy match employer name (RapidFuzz threshold 85)
4. Write `dol_salary_min`, `dol_salary_max`, `dol_salary_year`, `dol_case_count` to job record
5. Refresh DOL dataset monthly (configurable)

**Specialty group mapping:**
```python
IM_GROUP = ["Physician", "Internal Medicine", "Hospitalist", "Primary Care"]
FM_GROUP = ["Family Medicine", "Family Practice", "Family Physician"]
```
Lookup uses the broadest matching group to maximize cache hits.

**Output in master CSV:**
- `salary_posted` — from job posting text (current)
- `dol_salary_min` / `dol_salary_max` — from DOL LCA (historical)
- `dol_year` — year of DOL data
- `dol_filings` — number of H1B filings found (high count = reliable sponsor)

---

## 13. Live Updates & Scheduler (src/scheduler.py)

**APScheduler** runs the pipeline automatically in the background.

**Schedule:** Every 2 hours (configurable in `.env` as `POLL_INTERVAL_HOURS=2`)

**Modes:**
1. **Background mode** — `python -m src.scheduler` starts APScheduler as a background process; Streamlit dashboard connects to the same SQLite DB and auto-refreshes
2. **Integrated mode** — Streamlit app launches the scheduler on startup (single process)

**Streamlit auto-refresh:**
- `st.rerun()` called every 60 seconds via `streamlit-autorefresh` component
- Badge shows "Last updated: 4 min ago" and "Next run in: 1h 56m"
- New jobs since last page load highlighted in yellow

**Run log:** Every scheduled run writes a `scrape_runs` entry. Dashboard shows run history with timestamps and new-job counts.

---

## 15. Contact Extractor (src/contact_extractor.py)

Extracts publicly listed contact info from the job posting text only. Never fetches hidden data.

Regex patterns:
```python
EMAIL = r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'
PHONE = r'(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}'
NAME  = r'(?:contact|recruiter|reach out to|send.*to)[:\s]+([A-Z][a-z]+ [A-Z][a-z]+)'
```

Rules:
- Only extract from text that was publicly visible on the posting page
- Store raw matched values only — no inference
- If no contact info in posting, all three fields remain NULL

---

## 16. Posting Date Extraction

Every scraper attempts to extract `posted_date` from:
- Structured `datetime` attributes (ISO 8601 preferred)
- Text like "Posted 3 days ago" → calculated back from run date
- Text like "Posted May 15, 2026" → parsed to DATE
- JSON-LD schema.org `datePosted` field (common on modern career pages)

If extraction fails: `posted_date = NULL`, `posted_date_raw = NULL`. Never guess.

---

## 17. Notifications (src/notifier.py)

Windows desktop toast notification after each pipeline run:
```
"Physician Job Tracker: 47 new jobs found (12 HIGH priority)"
```

Uses `plyer` library (cross-platform, no external service needed). Triggered at end of pipeline run, both from CLI and Streamlit. If 0 new jobs found, no notification sent.

---

## 18. Exports (src/exporters.py)

Output dir: `data/exports/YYYY-MM-DD/`

| File | Contents |
|---|---|
| `master_jobs.csv` | **Primary output.** All deduped jobs, all fields: title, employer, city, state, salary_min, salary_max, dol_salary_min, dol_salary_max, dol_year, dol_filings, contact_name, contact_email, contact_phone, h1b_status, j1_status, posted_date, source_url, priority_label |
| `jobs_high_priority.csv` | HIGH priority only, same columns |
| `daily_summary.txt` | Jinja2 rendered from `templates/daily_summary.txt` |
| `scrape_report.txt` | Per-source: found / new / dupes / errors / blocked |

---

## 19. Gmail Drafts (src/gmail_drafts.py)

- Gmail API v1, OAuth2 flow
- `credentials.json` from Google Cloud Console (stored in `.env` path)
- `token.json` cached after first auth
- Draft created per selected job using Jinja2 `templates/job_email_draft.txt`
- Draft ID stored in `gmail_drafts` table
- Triggered manually from Streamlit "Browse Jobs" tab
- Never auto-sent

---

## 20. Streamlit Dashboard (src/dashboard.py)

Four tabs:

**Tab 1 — Run Pipeline**
- Multi-select: states (all 50; NC and SC checked by default, others opt-in)
- Multi-select: specialty terms (IM + FM terms pre-selected)
- "Run Now" button → calls `main.run_pipeline(states, terms)`
- Live log output in text area showing per-source progress

**Tab 2 — Browse Jobs**
- Master table: all jobs — title, employer, city, state, salary (posted), DOL salary (historical), DOL filings count, contact name, contact email, contact phone, H1B, J1, posted date, source URL, priority
- Filter bar: state, visa status (H1B/J1), priority label, employer type, specialty (IM/FM), posting date range, salary range
- Click row → side panel: full detail + "Create Gmail Draft" button
- "Mark Reviewed / Applied / Rejected" status buttons
- "Download filtered view as CSV" button
- New jobs (since last refresh) highlighted in yellow
- "Last updated" timestamp + "Next auto-run in Xh Xm" counter

**Tab 3 — Exports**
- List past export run directories with job counts
- Download `master_jobs.csv` and `jobs_high_priority.csv` per run
- Show daily summary text

**Tab 4 — Sources**
- Table of all 20–30 sources with last run stats (found/new/dupes/errors/blocked)
- Toggle enable/disable per source
- "Add employer URL" form → saves to `employers` table + `sources.yaml`
- Manual CSV import upload for gated sources (LinkedIn exports, etc.)

---

## 21. Error Handling

- Every scraper wrapped in `try/except`; failure logged to `data/logs/YYYY-MM-DD.log` and `scrape_runs` table; pipeline continues
- `robots.txt` checked via `urllib.robotparser` before every new domain; disallowed → skip + log
- Playwright: detect Cloudflare/CAPTCHA by checking for known challenge page text patterns; if detected → mark source `blocked_auto`, skip, log
- All blocked/errored sources surfaced in Streamlit Sources tab
- Manual CSV import path available for any source that proves unreliable

---

## 22. Tech Stack

| Component | Library |
|---|---|
| HTTP (static) | `httpx` |
| HTML parsing | `beautifulsoup4` + `lxml` |
| Dynamic pages | `playwright` |
| Database ORM | `sqlalchemy` |
| Database | SQLite |
| Deduplication | `rapidfuzz` |
| Data models | `pydantic` |
| Data processing | `pandas` |
| Config | `pyyaml` |
| Secrets | `python-dotenv` |
| Web search | `duckduckgo-search` |
| Email | Gmail API v1 (`google-api-python-client`) |
| Templates | `jinja2` |
| Dashboard | `streamlit` |
| Scheduler | `apscheduler` |
| Dashboard refresh | `streamlit-autorefresh` |
| Notifications | `plyer` |
| Regex | stdlib `re` |
| Hashing | stdlib `hashlib` |
| robots.txt | stdlib `urllib.robotparser` |

Python 3.11+. All dependencies pinned in `requirements.txt`.

---

## 23. Environment Variables (.env)

```
GMAIL_CREDENTIALS_PATH=config/credentials.json
GMAIL_TOKEN_PATH=config/token.json
GMAIL_SENDER_EMAIL=your@gmail.com
DB_PATH=data/jobs.db
LOG_DIR=data/logs
EXPORT_DIR=data/exports
POLL_INTERVAL_HOURS=2
DOL_DATA_DIR=data/dol_lca
DOL_REFRESH_DAYS=30
```

---

## 24. Out of Scope (MVP)

- Cloud hosting / remote access
- Multi-user support
- Email auto-sending
- Paid search APIs (SerpAPI, etc.)
- Async/parallel scraping
- Docker container
- Automated scheduling (Windows Task Scheduler setup is documented in README but not automated)
