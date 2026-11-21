"""Public open/click tracking endpoints.

These are the only mail endpoints without user authentication: a recipient's
mail client fetches the pixel and follows wrapped links with no session. A
signed token is the credential, and only it decides which draft and tenant an
event is attributed to.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse, Response

from app.db import SessionLocal
from app.services.tracking import PIXEL_GIF, record_click, record_open

logger = logging.getLogger(__name__)

router = APIRouter()

# Never let a proxy or the recipient's client cache the pixel: a cached image
# would suppress subsequent opens.
_NO_STORE = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
}


@router.get("/open/{token}", include_in_schema=False)
def track_open(token: str):
    """Return a 1x1 GIF and record one open for the token's draft."""
    db = SessionLocal()
    try:
        record_open(db, token)
    except Exception:  # tracking must never break the image response
        logger.warning("Could not record open for token %s", token, exc_info=True)
    finally:
        db.close()
    return Response(content=PIXEL_GIF, media_type="image/gif", headers=_NO_STORE)


@router.get("/click/{token}", include_in_schema=False)
def track_click(token: str, url: Optional[str] = Query(default=None)):
    """Record the click and redirect to the original target.

    Only an absolute http(s) target is followed; anything else falls back to the
    application root so the endpoint cannot be used as an open redirect.
    """
    db = SessionLocal()
    try:
        target = record_click(db, token, url)
    except Exception:
        logger.warning("Could not record click for token %s", token, exc_info=True)
        target = None
    finally:
        db.close()

    if not target:
        from app.services.tracking import base_url

        target = base_url() or "/"
    return RedirectResponse(url=target, status_code=302)
