"""
python 5 – deduplicate_todo
POST /todo/deduplicate

Strategia dwuetapowa:
  1. rapidfuzz WRatio >= 90%  → auto-delete (starszy rekord)
  2. rapidfuzz 50-89%         → Claude Sonnet decyduje czy to duplikat
Zwraca {removed_count, remaining_count}.
"""

import json
import logging
from itertools import combinations

import anthropic
import psycopg2.extras
from fastapi import APIRouter, Depends
from rapidfuzz import fuzz
import re

from app.auth import require_bearer
from app.config import settings
from app.db import get_db

router = APIRouter(dependencies=[Depends(require_bearer)])
logger = logging.getLogger(__name__)

_claude = anthropic.Anthropic(api_key=settings.anthropic_api_key)

_DEDUP_SYSTEM = """Masz listę par tytułów zadań TODO. Oceń dla każdej pary czy to duplikaty
(to samo zadanie wyrażone inaczej lub z drobnymi różnicami).

Zwróć TYLKO JSON array: [{"id_a": "...", "id_b": "...", "is_dup": true}]
Uwzględniaj tylko pary, które SĄ duplikatami. Pary które nie są duplikatami pomiń.
Bez żadnego tekstu przed ani po. Jeśli żadna para nie jest duplikatem, zwróć: []"""

_AUTO_THRESHOLD = 90    # >= tego → auto usuń
_MAYBE_THRESHOLD = 50   # >= tego i < AUTO → daj Claude


def _normalize(title: str) -> str:
    """Normalizuj tytuł do porównywania fuzzy."""
    title = title.lower()
    title = re.sub(r"[^\w\s]", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


@router.post("/todo/deduplicate")
def deduplicate_todo(conn=Depends(get_db)):
    """
    Deduplikacja TODO z ostatnich 7 dni.
    Wywołuje Claude tylko dla 'trudnych' par (50-89% podobieństwa).
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # 1. Pobierz TODO z ostatnich 7 dni (posortowane od najstarszego)
    cur.execute("""
        SELECT id::text, title, created_at
        FROM tabela_todo
        WHERE created_at > NOW() - INTERVAL '7 days'
        ORDER BY created_at ASC
    """)
    rows = cur.fetchall()

    if len(rows) < 2:
        cur.execute("SELECT COUNT(*) AS cnt FROM tabela_todo")
        remaining = cur.fetchone()["cnt"]
        return {"removed_count": 0, "remaining_count": remaining}

    auto_remove: set[str] = set()
    maybe_pairs: list[tuple[str, str, str, str]] = []  # (id_a, title_a, id_b, title_b)

    # 2. Porównaj wszystkie pary
    for row_a, row_b in combinations(rows, 2):
        id_a, id_b = row_a["id"], row_b["id"]
        if id_a in auto_remove or id_b in auto_remove:
            continue

        sim = fuzz.WRatio(_normalize(row_a["title"]), _normalize(row_b["title"]))

        if sim >= _AUTO_THRESHOLD:
            # row_a jest starszy (ORDER BY created_at ASC) → usuń row_a
            auto_remove.add(id_a)
            logger.debug("Auto-dedup: '%s' ≈ '%s' (%.0f%%)", row_a["title"], row_b["title"], sim)
        elif sim >= _MAYBE_THRESHOLD:
            maybe_pairs.append((id_a, row_a["title"], id_b, row_b["title"]))

    # 3. Usuń automatyczne duplikaty
    auto_removed = 0
    if auto_remove:
        cur2 = conn.cursor()
        cur2.execute(
            "DELETE FROM tabela_todo WHERE id::text = ANY(%s)",
            (list(auto_remove),),
        )
        auto_removed = cur2.rowcount
        logger.info("Auto-dedup: usunięto %d rekordów", auto_removed)

    # 4. Claude dla par 50-89% (max 50 par na jedno wywołanie)
    claude_removed = 0
    if maybe_pairs:
        batch = maybe_pairs[:50]
        pairs_text = "\n".join(
            f'id_a: "{id_a}" | tytuł_a: "{ta}" || id_b: "{id_b}" | tytuł_b: "{tb}"'
            for id_a, ta, id_b, tb in batch
        )
        try:
            response = _claude.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=2048,
                system=_DEDUP_SYSTEM,
                messages=[{"role": "user", "content": f"Pary do oceny:\n{pairs_text}"}],
            )
            results: list[dict] = json.loads(response.content[0].text.strip())
            dup_ids = [r["id_a"] for r in results if r.get("is_dup")]
            if dup_ids:
                cur3 = conn.cursor()
                cur3.execute(
                    "DELETE FROM tabela_todo WHERE id::text = ANY(%s)",
                    (dup_ids,),
                )
                claude_removed = cur3.rowcount
                logger.info("Claude dedup: usunięto %d rekordów", claude_removed)
        except (anthropic.APIError, json.JSONDecodeError) as exc:
            # Błąd Claude → zachowaj 'trudne' rekordy, zaloguj
            logger.error("Claude dedup error (zachowuję rekordy): %s", exc)

    conn.commit()

    # 5. Policz pozostałe
    cur.execute("SELECT COUNT(*) AS cnt FROM tabela_todo")
    remaining = cur.fetchone()["cnt"]

    total_removed = auto_removed + claude_removed
    logger.info("deduplicate_todo: usunięto %d, pozostało %d", total_removed, remaining)
    return {"removed_count": total_removed, "remaining_count": remaining}
