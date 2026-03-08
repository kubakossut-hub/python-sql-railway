"""
python 3 – add_email_labels
POST /email/labels

Klasyfikacja maili w dwóch krokach:
  1. Newsletter check (rule-based, nagłówki) → stop natychmiast
  2. Claude Haiku → klasyfikacja: signatures | TODO | -long | other
     Fallback na regex jeśli Claude niedostępny.
"""

import json
import logging
import re

import anthropic
from fastapi import APIRouter, Depends

from app.auth import require_bearer
from app.config import settings
from app.models import EmailInput, LabelsOutput
from app.utils import clean_body

router = APIRouter(dependencies=[Depends(require_bearer)])
logger = logging.getLogger(__name__)

_claude = anthropic.Anthropic(api_key=settings.anthropic_api_key)

# ---------------------------------------------------------------------------
# Newsletter detection – zawsze rule-based (natychmiastowe, bez kosztów API)
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
# System prompt dla Claude Haiku
# Haiku wystarczy do klasyfikacji – tańszy i szybszy niż Sonnet
# ---------------------------------------------------------------------------
_SYSTEM = """Klasyfikujesz maile biznesowe. Na podstawie tematu i treści przypisz odpowiednie etykiety.

Dostępne etykiety:
- "signatures" – mail zawiera prośbę o podpis dokumentu (DocuSign, Adobe Sign, #CEOsign, "please sign", "do podpisania")
- "TODO"        – mail zawiera zadanie do wykonania, prośbę o działanie, "action required", "please review", coś wymaga reakcji
- "-long"       – treść jest długa i wymaga więcej niż 2 minut czytania / jest to raport lub brief
- "other"       – żadna z powyższych (np. FYI, potwierdzenie, newsletter bez nagłówka)

Zasady:
- Mail może mieć jednocześnie kilka etykiet (np. ["signatures", "TODO"])
- Jeśli nie pasuje żadna, użyj ["other"]
- "other" nie może być połączone z innymi etykietami

Zwróć TYLKO poprawny JSON, bez żadnego tekstu przed ani po:
{"labels": ["..."], "primary_category": "...", "confidence": 0.95, "reasoning": "krótkie uzasadnienie po polsku"}"""

# ---------------------------------------------------------------------------
# Regex fallback (używany gdy Claude niedostępny)
# ---------------------------------------------------------------------------
_FALLBACK_SIG_RE = re.compile(
    r"docusign|adobe\s*sign|#ceosign|please\s+sign|do\s+podpisania|signature\s+required",
    re.IGNORECASE,
)
_FALLBACK_TODO_RE = re.compile(
    r"\btodo\b|action\s+required|please\s+review|do\s+zrobienia"
    r"|can\s+you\s+please|could\s+you\s+please|prosimy\s+o",
    re.IGNORECASE,
)
_LONG_THRESHOLD = 3_000


def _regex_fallback(subject: str, body: str, email_id: str) -> LabelsOutput:
    """Rule-based fallback na wypadek niedostępności Claude."""
    text = subject + "\n" + body
    labels: list[str] = []

    if _FALLBACK_SIG_RE.search(text):
        labels.append("signatures")
    if _FALLBACK_TODO_RE.search(text):
        labels.append("TODO")
    if len(body) > _LONG_THRESHOLD:
        labels.append("-long")
    if not labels:
        labels = ["other"]

    logger.info("email_labels fallback regex: email_id=%s labels=%s", email_id, labels)
    return LabelsOutput(
        labels=labels,
        primary_category=labels[0],
        confidence=0.7,
        reasoning="Fallback regex (Claude niedostępny)",
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/email/labels", response_model=LabelsOutput)
def add_email_labels(data: EmailInput):
    """
    1. Newsletter check (nagłówki) → jeśli newsletter, stop i zwróć od razu
    2. Oczyść treść maila (clean_body)
    3. Claude Haiku → JSON z etykietami
    4. Jeśli Claude zawiedzie → fallback regex (confidence=0.7)
    """

    # 1. Newsletter – sprawdź nagłówki, nie angażuj Claude
    header_keys_lower = {k.lower() for k in data.headers.keys()}
    precedence = data.headers.get("Precedence", "").lower().strip()

    if _NEWSLETTER_HEADER_KEYS & header_keys_lower or precedence in _NEWSLETTER_PRECEDENCE:
        logger.debug("email_labels newsletter header: email_id=%s", data.email_id)
        return LabelsOutput(
            labels=["newsletter"],
            primary_category="newsletter",
            confidence=1.0,
            reasoning="Newsletter header wykryty (List-Unsubscribe / Precedence)",
        )

    # 2. Oczyść treść maila przed wysłaniem do Claude
    cleaned = clean_body(data.body or "")
    subject = data.subject or ""

    # 3. Claude Haiku – klasyfikacja
    try:
        response = _claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=_SYSTEM,
            messages=[{
                "role": "user",
                "content": f"Temat: {subject}\n\nTreść:\n{cleaned[:3000]}",
            }],
        )
        raw = response.content[0].text.strip()
        result: dict = json.loads(raw)

        labels: list[str] = result.get("labels") or ["other"]
        primary: str = result.get("primary_category") or labels[0]
        confidence: float = float(result.get("confidence", 0.9))
        reasoning: str = result.get("reasoning", "")

        logger.debug("email_labels Claude OK: email_id=%s labels=%s conf=%.2f",
                     data.email_id, labels, confidence)

        return LabelsOutput(
            labels=labels,
            primary_category=primary,
            confidence=confidence,
            reasoning=reasoning,
        )

    except anthropic.APIError as exc:
        logger.warning("Claude API error w email_labels (fallback): email_id=%s err=%s",
                       data.email_id, exc)
        return _regex_fallback(subject, cleaned, data.email_id)

    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("Niepoprawny JSON od Claude (fallback): email_id=%s err=%s",
                       data.email_id, exc)
        return _regex_fallback(subject, cleaned, data.email_id)
