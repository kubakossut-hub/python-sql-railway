"""
python 2 – insert_TODO         →  POST /todo
python 6 – read_TODO           →  GET  /todo
           update TODO         →  PATCH /todo/{id}
           accept TODO (inbox) →  POST /inbox/accept  (wywołuje Make 9 webhook)
"""

import logging
import uuid

import httpx
import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional

from app.auth import require_bearer
from app.config import settings
from app.db import get_db
from app.models import AcceptTodosRequest, TodoItem, TodoUpdate

router = APIRouter(dependencies=[Depends(require_bearer)])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# POST /todo  – python 2: insert_TODO
# ---------------------------------------------------------------------------

@router.post("/todo")
def insert_todo(
    items: list[TodoItem] | TodoItem,
    conn=Depends(get_db),
):
    """
    Przyjmuje pojedynczy TodoItem lub array. Robi batch INSERT do tabela_todo.
    Zwraca listę UUID nowo utworzonych rekordów.
    """
    # Normalizuj do listy
    if not isinstance(items, list):
        items = [items]

    # Walidacja
    errors: list[str] = []
    for i, item in enumerate(items):
        missing = []
        if not item.title:
            missing.append("title")
        if not item.source:
            missing.append("source")
        if missing:
            errors.append(f"item[{i}]: brakujące pola: {missing}")

    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    # Batch INSERT
    cur = conn.cursor()
    inserted_ids: list[str] = []

    try:
        for item in items:
            new_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO tabela_todo (
                    id, title, description, source, source_id,
                    duedate, duration, project_id, assignee_id,
                    meeting_title, attendees
                ) VALUES (
                    %s, %s, %s, %s::source_type, %s,
                    %s, %s, %s, %s,
                    %s, %s
                )
                """,
                (
                    new_id,
                    item.title,
                    item.description,
                    item.source.value,
                    item.source_id,
                    item.duedate,
                    item.duration,
                    item.project_id,
                    item.assignee_id,
                    item.meeting_title,
                    item.attendees,
                ),
            )
            inserted_ids.append(new_id)
    except Exception as exc:
        logger.error("DB insert_todo error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Błąd bazy danych: {exc}")

    logger.info("insert_todo: wstawiono %d rekordów", len(inserted_ids))
    return {"status": "ok", "inserted_ids": inserted_ids}


# ---------------------------------------------------------------------------
# GET /todo  – python 6: read_TODO
# ---------------------------------------------------------------------------

@router.get("/todo")
def read_todo(
    reviewed: Optional[bool] = None,
    added_to_motion: Optional[bool] = None,
    conn=Depends(get_db),
):
    """
    Zwraca JSON TODO Array filtrowany po reviewed i/lub added_to_motion.
    Używane przez Make 9 (przez python 6) oraz przez HTML_inbox.
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    conditions: list[str] = []
    params: list = []

    if reviewed is not None:
        conditions.append("reviewed = %s")
        params.append(reviewed)
    if added_to_motion is not None:
        conditions.append("added_to_motion = %s")
        params.append(added_to_motion)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    cur.execute(
        f"SELECT * FROM tabela_todo {where} ORDER BY created_at DESC",
        params,
    )
    rows = cur.fetchall()

    # Konwertuj datetime na string dla JSON
    result = []
    for row in rows:
        d = dict(row)
        for key, val in d.items():
            if hasattr(val, "isoformat"):
                d[key] = val.isoformat()
        result.append(d)

    return result


# ---------------------------------------------------------------------------
# PATCH /todo/{todo_id}  – aktualizacja pól TODO (inline edit w HTML_inbox)
# ---------------------------------------------------------------------------

@router.patch("/todo/{todo_id}")
def update_todo(
    todo_id: str,
    data: TodoUpdate,
    conn=Depends(get_db),
):
    """
    Częściowa aktualizacja rekordu TODO.
    Używane przez HTML_inbox do zapisywania zmian przed zatwierdzeniem.
    """
    cur = conn.cursor()

    updates: dict = {}
    if data.title is not None:
        updates["title"] = data.title
    if data.description is not None:
        updates["description"] = data.description
    if data.duedate is not None:
        updates["duedate"] = data.duedate
    if data.duration is not None:
        updates["duration"] = data.duration
    if data.project_id is not None:
        updates["project_id"] = data.project_id
    if data.assignee_id is not None:
        updates["assignee_id"] = data.assignee_id
    if data.reviewed is not None:
        updates["reviewed"] = data.reviewed

    if not updates:
        raise HTTPException(status_code=400, detail="Brak pól do aktualizacji")

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    params = list(updates.values()) + [todo_id]

    try:
        cur.execute(
            f"UPDATE tabela_todo SET {set_clause} WHERE id = %s::uuid",
            params,
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="TODO nie znalezione")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("DB update_todo error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Błąd bazy danych: {exc}")

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# POST /inbox/accept  – zbiorczy accept z HTML_inbox + wyzwolenie Make 9
# ---------------------------------------------------------------------------

@router.post("/inbox/accept")
async def accept_todos(
    data: AcceptTodosRequest,
    conn=Depends(get_db),
):
    """
    Ustawia reviewed=TRUE dla wskazanych TODO, a następnie wywołuje webhook Make 9
    (Make 9 zajmuje się dodaniem do Motion i aktualizacją added_to_motion).
    """
    if not data.todo_ids:
        raise HTTPException(status_code=400, detail="Brak todo_ids")

    cur = conn.cursor()

    # Ustaw reviewed=TRUE
    try:
        cur.execute(
            "UPDATE tabela_todo SET reviewed = TRUE WHERE id = ANY(%s::uuid[])",
            (data.todo_ids,),
        )
        updated_count = cur.rowcount
    except Exception as exc:
        logger.error("DB accept_todos error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Błąd bazy danych: {exc}")

    # Wywołaj webhook Make 9
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                settings.make9_webhook_url,
                json={"accepted_ids": data.todo_ids},
            )
            resp.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        logger.error("Make 9 webhook error: %s", exc)
        raise HTTPException(status_code=502, detail=f"Make 9 webhook error: {exc}")

    logger.info("inbox/accept: zatwierdzono %d TODO", updated_count)
    return {"status": "ok", "updated": updated_count}
