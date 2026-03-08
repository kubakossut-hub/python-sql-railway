"""
python 4 – todo_from_email
POST /email/todo

Przetwarza tablicę maili, dla każdego ekstrahuje TODO przez Claude Sonnet,
wstawia do tabela_todo. Błędy per-email nie przerywają pętli.
"""

import json
import logging
import uuid

import anthropic
from fastapi import APIRouter, Depends

from app.auth import require_bearer
from app.config import settings
from app.db import get_db
from app.models import EmailArrayInput
from app.utils import clean_body

router = APIRouter(dependencies=[Depends(require_bearer)])
logger = logging.getLogger(__name__)

_claude = anthropic.Anthropic(api_key=settings.anthropic_api_key)

_SYSTEM = """Jesteś asystentem ekstrakcji zadań z maili biznesowych.
Z treści maila wyciągnij TODO do wykonania.

Dla każdego zadania zwróć:
- title: krótki tytuł (max 100 znaków)
- description: kontekst – co trzeba zrobić, z jakiego maila (max 300 znaków)
- duedate: termin ISO 8601 jeśli wymieniony, null jeśli nie

Zwróć TYLKO poprawny JSON array. Bez żadnego tekstu przed ani po.
Jeśli nie ma TODO, zwróć pustą tablicę: []"""


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/email/todo")
def todo_from_email(data: EmailArrayInput, conn=Depends(get_db)):
    """
    Dla każdego maila:
      a) Oczyść treść (clean_email)
      b) Claude Sonnet → lista TODO
      c) INSERT do tabela_todo
    Błąd per-email trafia do failed[], nie przerywa pętli.
    """
    processed = 0
    failed: list[dict] = []
    cur = conn.cursor()

    for email in data.emails:
        try:
            # a. Oczyść mail
            cleaned = clean_body(email.body or "")

            # b. Claude Sonnet
            try:
                response = _claude.messages.create(
                    model="claude-sonnet-4-5",
                    max_tokens=2048,
                    system=[{"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}],
                    messages=[{
                        "role": "user",
                        "content": (
                            f"Od: {email.from_address}\n"
                            f"Temat: {email.subject}\n"
                            f"Data: {email.date}\n\n"
                            f"Treść:\n{cleaned[:4000]}"
                        ),
                    }],
                )
                raw = response.content[0].text.strip()
                todos: list[dict] = json.loads(raw)
                if not isinstance(todos, list):
                    todos = []
            except (anthropic.APIError, json.JSONDecodeError) as exc:
                logger.warning("Claude error email %s: %s", email.email_id, exc)
                failed.append({"email_id": email.email_id, "error": f"Claude: {exc}"})
                continue

            if not todos:
                processed += 1
                continue

            # c. INSERT do tabela_todo
            try:
                for todo in todos:
                    description = (
                        (todo.get("description") or "")
                        + f"\n[Email: {email.subject} od {email.from_address}]"
                    )[:500]

                    cur.execute(
                        """
                        INSERT INTO tabela_todo (
                            id, title, description, source, source_id, duedate
                        ) VALUES (%s, %s, %s, %s::source_type, %s, %s)
                        """,
                        (
                            str(uuid.uuid4()),
                            (todo.get("title") or "")[:200],
                            description,
                            "email",
                            email.thread_id or email.email_id,
                            todo.get("duedate"),
                        ),
                    )
                conn.commit()
            except Exception as exc:
                conn.rollback()
                logger.error("DB error email %s: %s", email.email_id, exc)
                failed.append({"email_id": email.email_id, "error": f"DB: {exc}"})
                continue

            processed += 1

        except Exception as exc:
            logger.error("Nieoczekiwany błąd email %s: %s", email.email_id, exc)
            failed.append({"email_id": email.email_id, "error": str(exc)})

    logger.info("todo_from_email: processed=%d, failed=%d", processed, len(failed))
    return {"processed": processed, "failed": failed}
