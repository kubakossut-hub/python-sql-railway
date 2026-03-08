import logging
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

from app.config import settings

logger = logging.getLogger(__name__)

_pool: ThreadedConnectionPool | None = None


def init_pool() -> None:
    """Inicjalizuje connection pool. Wywołuj raz przy starcie aplikacji."""
    global _pool
    _pool = ThreadedConnectionPool(
        minconn=2,
        maxconn=10,
        dsn=settings.database_url,
        sslmode="require",
    )
    logger.info("Pool PostgreSQL zainicjalizowany (min=2, max=10)")


def get_db():
    """
    FastAPI dependency – pobiera połączenie z puli, commituje po sukcesie,
    robi rollback po błędzie, zwraca połączenie do puli po zakończeniu.
    """
    if _pool is None:
        raise RuntimeError("Pool nie zainicjalizowany – wywołaj init_pool()")

    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)
