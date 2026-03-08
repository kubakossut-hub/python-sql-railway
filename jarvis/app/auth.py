from fastapi import Header, HTTPException
from app.config import settings


async def require_bearer(authorization: str = Header(...)) -> None:
    """
    FastAPI dependency – weryfikuje Bearer token w nagłówku Authorization.
    Token jest wstrzykiwany przez nginx (proxy_set_header Authorization),
    więc przeglądarka nigdy nie widzi jego wartości.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Wymagany nagłówek: Authorization: Bearer <token>")

    token = authorization.removeprefix("Bearer ").strip()
    if token != settings.jarvis_api_token:
        raise HTTPException(status_code=403, detail="Nieprawidłowy token")
