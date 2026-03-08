from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enum types (muszą odpowiadać typom PostgreSQL)
# ---------------------------------------------------------------------------

class SourceType(str, Enum):
    transcript = "transcript"
    email = "email"
    manual = "manual"


# ---------------------------------------------------------------------------
# JSON Transcript  (wejście dla python 1)
# ---------------------------------------------------------------------------

class TranscriptInput(BaseModel):
    meeting_id: str
    title: str
    attendees: list[str] = []
    transcript: str
    date: Optional[str] = None       # ISO 8601 date string
    summary: Optional[str] = None


# ---------------------------------------------------------------------------
# JSON TODO  (zwracane przez python 1 & 4, wejście dla python 2)
# ---------------------------------------------------------------------------

class TodoItem(BaseModel):
    title: str
    description: Optional[str] = None
    source: SourceType
    source_id: Optional[str] = None
    duedate: Optional[str] = None    # ISO 8601 datetime string
    duration: Optional[int] = None   # minuty
    project_id: Optional[str] = None
    assignee_id: Optional[str] = None
    meeting_title: Optional[str] = None
    attendees: Optional[str] = None  # JSON array jako string lub CSV


class TodoUpdate(BaseModel):
    """Częściowa aktualizacja rekordu TODO (PATCH)."""
    title: Optional[str] = None
    description: Optional[str] = None
    duedate: Optional[str] = None
    duration: Optional[int] = None
    project_id: Optional[str] = None
    assignee_id: Optional[str] = None
    reviewed: Optional[bool] = None


class AcceptTodosRequest(BaseModel):
    """Żądanie zbiorczego zatwierdzenia TODO z HTML_inbox."""
    todo_ids: list[str]


# ---------------------------------------------------------------------------
# JSON Email  (wejście dla python 3, 4, 7)
# ---------------------------------------------------------------------------

class EmailInput(BaseModel):
    email_id: str
    thread_id: Optional[str] = None
    subject: Optional[str] = None
    from_address: Optional[str] = Field(None, alias="from")
    to_address: Optional[str] = Field(None, alias="to")
    date: Optional[str] = None
    body: str
    headers: dict[str, Any] = {}

    model_config = {"populate_by_name": True}


class EmailArrayInput(BaseModel):
    emails: list[EmailInput]


# ---------------------------------------------------------------------------
# JSON Labels  (wyjście python 3)
# ---------------------------------------------------------------------------

class LabelsOutput(BaseModel):
    labels: list[str]
    primary_category: Optional[str] = None
    confidence: float = 1.0
    reasoning: Optional[str] = None


# ---------------------------------------------------------------------------
# JSON Cleaned Email  (wyjście python 7)
# ---------------------------------------------------------------------------

class CleanedEmailOutput(EmailInput):
    """Taka sama struktura jak EmailInput, ale body jest oczyszczone."""
    pass
