"""
python 3 – add_email_labels
POST /email/labels

Klasyfikacja maili na podstawie reguł (bez Claude).
Zwraca JSON Labels: lista etykiet + primary_category.
"""

import logging
import re

from fastapi import APIRouter, Depends

from app.auth import require_bearer
from app.models import EmailInput, LabelsOutput

router = APIRouter(dependencies=[Depends(require_bearer)])
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reguły newsletter – nagłówki HTTP
# ---------------------------------------------------------------------------
_NEWSLETTER_HEADER_KEYS = frozenset({
    "list-unsubscribe",
    "list-unsubscribe-post",
    "x-campaign-id",
    "x-mailchimp-id",
    "x-mailer",
})
_NEWSLETTER_PRECEDENCE = frozenset({"bulk", "list", "junk"})

# ---------------------------------------------------------------------------
# Reguły na treść – regex
# ---------------------------------------------------------------------------
_SIGNATURE_RE = re.compile(
    r"docusign|adobe\s*sign|#ceosign|please\s+sign|signature\s+required|do\s+podpisu",
    re.IGNORECASE,
)
_TODO_RE = re.compile(
    r"\btodo\b|action\s+required|please\s+review|do\s+zrobienia"
    r"|can\s+you\s+please|could\s+you\s+please|prosimy\s+o|proszę\s+o",
    re.IGNORECASE,
)
_LONG_BODY_THRESHOLD = 3_000  # znaków


@router.post("/email/labels", response_model=LabelsOutput)
def add_email_labels(data: EmailInput):
    """
    Klasyfikuje mail rule-based (bez Claude):
    1. Nagłówki → 'newsletter' (stop, nie sprawdzaj dalej)
    2. Regex treść/temat → 'signatures', 'TODO', '-long'
    """
    labels: list[str] = []

    # --- 1. Sprawdź nagłówki newsletterowe ---
    header_keys_lower = {k.lower() for k in data.headers.keys()}
    precedence = data.headers.get("Precedence", "").lower().strip()

    if _NEWSLETTER_HEADER_KEYS & header_keys_lower or precedence in _NEWSLETTER_PRECEDENCE:
        return LabelsOutput(
            labels=["newsletter"],
            primary_category="newsletter",
            confidence=1.0,
            reasoning="Newsletter header wykryty (List-Unsubscribe / Precedence)",
        )

    # --- 2. Regex na temat + treść ---
    subject = data.subject or ""
    body = data.body or ""
    text = subject + "\n" + body

    if _SIGNATURE_RE.search(text):
        labels.append("signatures")

    if _TODO_RE.search(text):
        labels.append("TODO")

    if len(body) > _LONG_BODY_THRESHOLD:
        labels.append("-long")

    primary = labels[0] if labels else "other"

    return LabelsOutput(
        labels=labels,
        primary_category=primary,
        confidence=1.0,
        reasoning="Klasyfikacja rule-based (regex)",
    )
