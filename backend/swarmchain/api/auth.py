"""API key authentication middleware.

In dev mode (api_key=""), all requests are allowed.
In production, the caller must provide a valid key via the X-API-Key header.
"""

from fastapi import Request, HTTPException

from swarmchain.config import get_settings


async def require_api_key(request: Request) -> None:
    """FastAPI dependency — rejects requests without a valid API key.

    Attach to any route with ``Depends(require_api_key)``.
    """
    settings = get_settings()
    if not settings.api_key:
        return  # dev mode, no auth required

    key = request.headers.get("X-API-Key", "")
    if key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
