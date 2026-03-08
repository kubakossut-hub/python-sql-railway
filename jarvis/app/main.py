import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import init_pool
from app.routes import transcript, todo, email_labels, email_todo, deduplicate, email_clean

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s – %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicjalizuje pool DB przy starcie, sprząta przy wyłączeniu."""
    init_pool()
    logger.info("JARVIS API uruchomiony")
    yield
    logger.info("JARVIS API zatrzymany")


app = FastAPI(
    title="JARVIS API",
    version="1.0.0",
    description="Backend dla systemu JARVIS – automatyzacja zadań i emaili",
    lifespan=lifespan,
)

# Rejestracja routerów
app.include_router(transcript.router, tags=["transcript"])
app.include_router(todo.router,       tags=["todo"])
app.include_router(email_labels.router, tags=["email"])
app.include_router(email_todo.router,   tags=["email"])
app.include_router(deduplicate.router,  tags=["todo"])
app.include_router(email_clean.router,  tags=["email"])


@app.get("/health", tags=["system"])
def health():
    """Endpoint healthcheck dla Railway."""
    return {"status": "ok"}
