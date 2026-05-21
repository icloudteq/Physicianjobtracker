# Physician Job Tracker

Private daily job intelligence tool for Internal Medicine and Family Medicine physician job search across all 50 US states.

## Features
- Searches 20+ physician job boards and hospital career pages
- Extracts salary, contact info, visa sponsorship signals
- Historical salary data from DOL H1B LCA public database
- NC/SC priority scoring
- Auto-runs every 2 hours
- Streamlit dashboard with live updates
- Gmail draft creation

## Setup

### 1. Create virtual environment

```
python -m venv venv
venv\Scripts\activate
```

### 2. Install dependencies

```
pip install -r requirements.txt
playwright install chromium
```

### 3. Configure environment

```
copy .env.example .env
```
Edit `.env` with your settings.

### 4. Set up Gmail (optional)

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project → Enable Gmail API
3. Create OAuth 2.0 credentials → Download as `config/credentials.json`

### 5. Seed employer database

```
python -m src.seed_employers
```

### 6. Run the app

```
streamlit run src/dashboard.py
```

Open browser at `http://localhost:8501`

## First run

1. Open the app → **Run Pipeline** tab
2. NC and SC are pre-selected — click **Run Now**
3. Wait for pipeline to complete (~5-10 min first run, downloads DOL salary data)
4. Go to **Browse Jobs** tab to see results

## Updating config

- Add hospital career pages in the **Sources** tab of the app
- Edit `config/states.yaml` to enable/disable states
- Edit `config/search_terms.yaml` to add specialty terms

## Legal notes
- Only scrapes public job pages that allow access
- Respects robots.txt on every domain
- Stores summaries only (no full job descriptions)
- Gmail creates DRAFTS only — never auto-sends
- DOL salary data is publicly required by law (LCA disclosures)
