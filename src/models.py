from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import date, datetime


class RawJob(BaseModel):
    source_name: str
    source_type: str
    source_url: str
    apply_url: Optional[str] = None
    title: str
    employer: str
    employer_type: str = "unknown"
    city: Optional[str] = None
    state: Optional[str] = None
    specialty: Optional[str] = None
    job_type: str = "unknown"
    raw_text: str = ""
    salary_text: Optional[str] = None
    visa_text: Optional[str] = None
    posted_date_raw: Optional[str] = None
    short_summary: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None

    @field_validator("state")
    @classmethod
    def normalize_state(cls, v):
        return v.strip().upper() if v else v

    @field_validator("title", "employer")
    @classmethod
    def strip_whitespace(cls, v):
        return v.strip() if v else v


class ScrapeRunResult(BaseModel):
    source_name: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    jobs_found: int = 0
    new_jobs: int = 0
    duplicates_found: int = 0
    errors: str = ""
    status: str = "running"
    selected_states: list[str] = []
    selected_terms: list[str] = []
