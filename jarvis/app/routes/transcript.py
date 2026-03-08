"""
python 1 – todo_from_transcript
POST /transcript

Odbiera JSON Transcript z Make 1, wysyła do Claude Sonnet,
wzbogaca wyniki i wywołuje webhook Make 2 z JSON TODO Array.
"""

import json
import logging

import anthropic
import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_bearer
from app.config import settings
from app.models import TranscriptInput

router = APIRouter(dependencies=[Depends(require_bearer)])
logger = logging.getLogger(__name__)

_claude = anthropic.Anthropic(api_key=settings.anthropic_api_key)

# System prompt – ephemeral cache (oszczędność tokenów przy wielu wywołaniach)
_SYSTEM = """Jesteś asystentem ekstrakcji zadań ze spotkań biznesowych.
Z podanej transkrypcji wyciągnij WSZYSTKIE TODO i działania do podjęcia.

Dla każdego zadania zwróć:
- title: krótki tytuł (max 100 znaków)
- description: kontekst z transkrypcji – kto zlecił, cel, dodatkowe info (max 300 znaków)
- duedate: termin ISO 8601 (YYYY-MM-DDTHH:MM:SS) jeśli wymieniony, null jeśli nie
- assignee_id: imię lub email osoby jeśli wymienione, null jeśli nie

Zwróć TYLKO poprawny JSON array. Bez żadnego tekstu przed ani po.
Przykład: [{"title": "Raport Q4", "description": "Prośba Anny na zarząd", "duedate": null, "assignee_id": null}]
Jeśli nie ma TODO, zwróć pustą tablicę: []"""


@router.post("/transcript")
async def todo_from_transcript(data: TranscriptInput):
    # 1. Walidacja: transkrypcja niepusta
    if not data.transcript.strip():
        raise HTTPException(status_code=400, detail="Transkrypcja jest pusta")

    # 2. Claude Sonnet z prompt cachingiem
    try:
        response = _claude.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=4096,
            system=[{"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{
                "role": "user",
                "content": (
                    f"Tytuł spotkania: {data.title}\n"
                    f"Uczestnicy: {', '.join(data.attendees)}\n"
                    f"Data: {data.date or 'nieznana'}\n\n"
                    f"Transkrypcja:\n{data.transcript}"
                ),
            }],
        )
    except anthropic.APIError as exc:
        logger.error("Claude API error w todo_from_transcript: %s", exc)
        raise HTTPException(status_code=502, detail=f"Claude API error: {exc}")

    # 3. Parsuj odpowiedź jako JSON array
    raw = response.content[0].text.strip()
    try:
        todos: list[dict] = json.loads(raw)
        if not isinstance(todos, list):
            raise ValueError("Oczekiwano JSON array")
    except (json.JSONDecodeError, ValueError):
        logger.error("Nie można sparsować odpowiedzi Claude: %s", raw[:500])
        raise HTTPException(status_code=500, detail="Claude zwrócił niepoprawny JSON")

    if not todos:
        logger.info("Brak TODO w transkrypcji meeting_id=%s", data.meeting_id)
        return {"status": "ok", "todo_count": 0}

    # 4. Wzbogać każde TODO o metadane źródła
    attendees_str = json.dumps(data.attendees, ensure_ascii=False)
    for todo in todos:
        todo["source"] = "transcript"
        todo["source_id"] = data.meeting_id
        todo["meeting_title"] = data.title
        todo["attendees"] = attendees_str

    # 5. HTTP POST → webhook Make 2
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(settings.make2_webhook_url, json=todos)
            resp.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        logger.error("Make 2 webhook error: %s", exc)
        raise HTTPException(status_code=502, detail=f"Make 2 webhook error: {exc}")

    logger.info("todo_from_transcript OK: %d TODO, meeting_id=%s", len(todos), data.meeting_id)
    return {"status": "ok", "todo_count": len(todos)}
