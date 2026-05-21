import base64
import json
import os
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Template
from sqlalchemy.orm import Session

from src.db import GmailDraft, Job
from src.logger import get_logger

log = get_logger("gmail_drafts")

_EMAIL_TEMPLATE = """Dear Hiring Manager,

I am writing to express my strong interest in the {{ title }} position at {{ employer }}{% if city %} in {{ city }}, {{ state }}{% endif %}.

I am a board-eligible physician completing residency training in Internal Medicine/Family Medicine and am actively seeking positions{% if state %} in {{ state }}{% endif %}.
{% if salary_text %}
The posted compensation of {{ salary_text }} aligns well with my expectations.
{% endif %}
I would welcome the opportunity to discuss this role further.

Sincerely,
{{ candidate_name }}
{{ sender_email }}
"""


def _get_gmail_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]
    creds_path = os.getenv("GMAIL_CREDENTIALS_PATH", "config/credentials.json")
    token_path = os.getenv("GMAIL_TOKEN_PATH", "config/token.json")

    creds = None
    if Path(token_path).exists():
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(creds_path).exists():
                raise FileNotFoundError(
                    f"Gmail credentials not found at {creds_path}. "
                    "Download credentials.json from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        Path(token_path).write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def create_draft(session: Session, job_id: int, recipient_email: str | None = None) -> dict:
    import yaml
    config = yaml.safe_load(Path("config/search_terms.yaml").read_text())
    candidate = config.get("candidate", {})

    job = session.query(Job).filter_by(id=job_id).first()
    if not job:
        return {"error": f"Job {job_id} not found"}

    to_email = recipient_email or job.contact_email or candidate.get("sender_email", "")
    if not to_email:
        return {"error": "No recipient email available"}

    subject = f"Interest in {job.title} – {job.employer}"
    body = Template(_EMAIL_TEMPLATE).render(
        title=job.title,
        employer=job.employer,
        city=job.city,
        state=job.state,
        salary_text=job.salary_text,
        candidate_name=candidate.get("candidate_name", "[Your Name]"),
        sender_email=candidate.get("sender_email", ""),
    )

    try:
        service = _get_gmail_service()
        msg = MIMEText(body)
        msg["to"] = to_email
        msg["subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        draft = service.users().drafts().create(
            userId="me", body={"message": {"raw": raw}}
        ).execute()

        record = GmailDraft(
            job_id=job_id,
            recipient_email=to_email,
            subject=subject,
            draft_body=body,
            gmail_draft_id=draft["id"],
        )
        session.add(record)
        session.commit()
        log.info(f"Draft created for job {job_id}: {draft['id']}")
        return {"success": True, "draft_id": draft["id"], "to": to_email}
    except Exception as e:
        log.error(f"Gmail draft failed for job {job_id}: {e}")
        return {"error": str(e)}
