"""
python 7 – clean_email
POST /email/clean

Usuwa cytowane odpowiedzi i stopki z treści maila.
Zwraca CleanedEmailOutput z oczyszczonym polem body.
"""

import logging
import re

from fastapi import APIRouter, Depends

from app.auth import require_bearer
from app.models import CleanedEmailOutput, EmailInput

router = APIRouter(dependencies=[Depends(require_bearer)])
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Wzorce do usunięcia – cytowane odpowiedzi
# ---------------------------------------------------------------------------
_QUOTED = [
    re.compile(r"On .+? wrote:.*",                re.DOTALL),
    re.compile(r"^>.*$",                           re.MULTILINE),
    re.compile(r"-{5,}Original Message-{5,}.*",   re.DOTALL | re.IGNORECASE),
    re.compile(r"_{5,}.*",                         re.DOTALL),
    re.compile(r"From:.*?Sent:.*?To:.*?Subject:.*?(?=\n\n)", re.DOTALL | re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# Wzorce do usunięcia – stopki
# ---------------------------------------------------------------------------
_FOOTERS = [
    re.compile(r"Sent from (my|the) .+",           re.IGNORECASE),
    re.compile(
        r"(Best regards|Kind regards|Regards|Pozdrawiam|Z poważaniem"
        r"|Dziękuję|Thank you|Thanks)[,.\s].*",
        re.DOTALL | re.IGNORECASE,
    ),
    re.compile(r"\n--\s*\n.*",                     re.DOTALL),
    re.compile(r"\n_{3,}\s*$",                     re.DOTALL),
]


def clean_body(body: str) -> str:
    """Czyści treść maila – usuwa cytaty i stopki."""
    for pat in _QUOTED:
        body = pat.sub("", body)
    for pat in _FOOTERS:
        body = pat.sub("", body)
    # Usuń nadmiarowe puste linie i whitespace
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return body


@router.post("/email/clean", response_model=CleanedEmailOutput)
def clean_email(data: EmailInput):
    """
    Przyjmuje JSON Email, zwraca JSON Cleaned Email
    (wszystkie pola bez zmian oprócz body).
    """
    cleaned = clean_body(data.body or "")
    logger.debug(
        "clean_email: email_id=%s, oryginał=%d znaków → %d znaków",
        data.email_id, len(data.body or ""), len(cleaned),
    )
    result = data.model_dump(by_alias=True)
    result["body"] = cleaned
    return CleanedEmailOutput(**result)
