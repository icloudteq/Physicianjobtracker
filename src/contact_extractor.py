import re
from typing import Optional

_EMAIL = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
_PHONE = re.compile(
    r'(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}'
)
_NAME_CONTEXT = re.compile(
    r'(?:contact|recruiter|reach\s+out\s+to|send\s+(?:resume|cv|application)\s+to'
    r'|questions\s+(?:contact|to)|for\s+more\s+information\s+contact)'
    r'[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})',
    re.IGNORECASE
)


def extract_contact(text: str) -> dict:
    """Extract publicly listed contact info from posting text only."""
    if not text:
        return {"contact_name": None, "contact_email": None, "contact_phone": None}

    email_m = _EMAIL.search(text)
    phone_m = _PHONE.search(text)
    name_m = _NAME_CONTEXT.search(text)

    email = email_m.group(0) if email_m else None
    phone = phone_m.group(0) if phone_m else None
    name = name_m.group(1) if name_m else None

    # Skip generic domain emails that aren't likely real contacts
    if email and any(d in email for d in ["example.com", "domain.com", "test.com"]):
        email = None

    return {
        "contact_name": name,
        "contact_email": email,
        "contact_phone": phone,
    }
