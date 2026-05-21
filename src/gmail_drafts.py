"""
Gmail draft creator — OAuth2, never auto-sends.
"""
import os
import base64
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from src.logger import get_logger

load_dotenv()
log = get_logger(__name__)

CREDS_FILE = os.getenv("GMAIL_CREDENTIALS_FILE", "credentials.json")
TOKEN_FILE = os.getenv("GMAIL_TOKEN_FILE", "token.json")
SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]
TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "job_email_draft.txt"


def _get_service():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None
    if Path(TOKEN_FILE).exists():
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(CREDS_FILE).exists():
                raise FileNotFoundError(
                    f"Gmail credentials not found at {CREDS_FILE}. "
                    "Download from Google Cloud Console → APIs → Gmail API → OAuth 2.0 credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        Path(TOKEN_FILE).write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def _render_template(job: dict) -> str:
    if not TEMPLATE_PATH.exists():
        return _default_template(job)
    template = TEMPLATE_PATH.read_text()
    for key, val in job.items():
        template = template.replace(f"{{{key}}}", str(val or ""))
    template = template.replace("{candidate_name}", os.getenv("CANDIDATE_NAME", "[Candidate Name]"))
    template = template.replace("{sender_name}", os.getenv("SENDER_NAME", "[Sender]"))
    return template


def _default_template(job: dict) -> str:
    return f"""Dear Hiring Team,

I am writing to express my interest in the {job.get('title', 'Physician')} position at {job.get('employer', 'your institution')} in {job.get('city', '')}, {job.get('state', '')}.

[Candidate Name] is a board-eligible Internal Medicine physician completing residency training, actively seeking opportunities in your region.

[Add personalized content here]

We would welcome the opportunity to discuss this position further.

Best regards,
{os.getenv('SENDER_NAME', '[Your Name]')}
{os.getenv('SENDER_EMAIL', '[Your Email]')}

---
Position: {job.get('title', '')}
Employer: {job.get('employer', '')}
Location: {job.get('city', '')}, {job.get('state', '')}
Apply URL: {job.get('apply_url', job.get('source_url', ''))}
"""


def create_draft(job: dict, recipient_email: str = "", subject: str = "") -> Optional[str]:
    """Create a Gmail draft for a job. Returns draft ID or None on failure."""
    if not recipient_email:
        recipient_email = os.getenv("SENDER_EMAIL", "")
    if not subject:
        subject = f"Interest in {job.get('title', 'Physician Position')} – {job.get('employer', '')}"

    body = _render_template(job)

    try:
        service = _get_service()
        msg = MIMEText(body)
        msg["to"] = recipient_email
        msg["subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        draft = service.users().drafts().create(
            userId="me", body={"message": {"raw": raw}}
        ).execute()
        draft_id = draft["id"]
        log.info(f"Draft created: {subject} (id={draft_id})")
        return draft_id
    except FileNotFoundError as e:
        log.error(str(e))
        return None
    except Exception as e:
        log.error(f"Gmail draft error: {e}")
        return None


def create_drafts_for_jobs(jobs: list[dict], recipient_email: str = "") -> int:
    """Create Gmail drafts for a list of jobs. Returns count created."""
    count = 0
    from src.db import save_gmail_draft
    for job in jobs:
        draft_id = create_draft(job, recipient_email)
        if draft_id:
            save_gmail_draft(
                job_id=job["id"],
                recipient=recipient_email,
                subject=f"Interest in {job.get('title', '')} – {job.get('employer', '')}",
                body=_render_template(job),
                gmail_id=draft_id,
            )
            count += 1
    return count
