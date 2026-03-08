"""
python 7 – clean_email
POST /email/clean

Usuwa cytowane odpowiedzi i stopki z treści maila.
Zwraca CleanedEmailOutput z oczyszczonym polem body.
"""

import logging

from fastapi import APIRouter, Depends

from app.auth import require_bearer
from app.models import CleanedEmailOutput, EmailInput
from app.utils import clean_body

router = APIRouter(dependencies=[Depends(require_bearer)])
logger = logging.getLogger(__name__)


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
