"""Main API router that includes all sub-routers."""
from fastapi import APIRouter

router = APIRouter()

# Import and include sub-routers
from app.routers import contacts, drafts, templates, smtp, settings, queue, replies, verifications, inbox

router.include_router(contacts.router, prefix="/contacts", tags=["contacts"])
router.include_router(drafts.router, prefix="/drafts", tags=["drafts"])
router.include_router(templates.router, prefix="/templates", tags=["templates"])
router.include_router(smtp.router, prefix="/smtp", tags=["smtp"])
router.include_router(settings.router, prefix="/settings", tags=["settings"])
router.include_router(queue.router, prefix="/queue", tags=["queue"])
router.include_router(replies.router, prefix="/replies", tags=["replies"])
router.include_router(verifications.router, prefix="/verifications", tags=["verifications"])
router.include_router(inbox.router, prefix="/inbox", tags=["inbox"])

# Import and include agents router
from app.routers import agents as agents_router
router.include_router(agents_router.router, prefix="/agents", tags=["agents"])