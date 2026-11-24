"""Main API router that includes all sub-routers.

Resource routers are mounted with a router-level ``get_current_user``
dependency so a new endpoint cannot be added unprotected by omission.
``/api/auth/*`` stays public because register/login must work before a token
exists.
"""
from fastapi import APIRouter, Depends

from app.deps import get_current_user

router = APIRouter()

protected = [Depends(get_current_user)]

# Import and include sub-routers
from app.routers import contacts, drafts, templates, smtp, settings, queue, replies, verifications, inbox, tracking, agents, lists, tenants, scheduling, ab_tests, campaigns

router.include_router(contacts.router, prefix="/contacts", tags=["contacts"], dependencies=protected)
router.include_router(drafts.router, prefix="/drafts", tags=["drafts"], dependencies=protected)
router.include_router(templates.router, prefix="/templates", tags=["templates"], dependencies=protected)
router.include_router(smtp.router, prefix="/smtp", tags=["smtp"], dependencies=protected)
router.include_router(settings.router, prefix="/settings", tags=["settings"], dependencies=protected)
router.include_router(queue.router, prefix="/queue", tags=["queue"], dependencies=protected)
router.include_router(replies.router, prefix="/replies", tags=["replies"], dependencies=protected)
router.include_router(verifications.router, prefix="/verifications", tags=["verifications"], dependencies=protected)
router.include_router(inbox.router, prefix="/inbox", tags=["inbox"], dependencies=protected)
router.include_router(tracking.router, prefix="/tracking", tags=["tracking"], dependencies=protected)
router.include_router(agents.router, prefix="/agents", tags=["agents"], dependencies=protected)
router.include_router(lists.router, prefix="/lists", tags=["lists"], dependencies=protected)
router.include_router(tenants.router, prefix="/tenants", tags=["tenants"], dependencies=protected)
router.include_router(scheduling.router, prefix="/scheduling", tags=["scheduling"], dependencies=protected)
router.include_router(ab_tests.router, prefix="/ab-tests", tags=["ab-tests"], dependencies=protected)
router.include_router(campaigns.router, prefix="/campaigns", tags=["campaigns"], dependencies=protected)

# Import and include auth router for SaaS authentication (public)
from app.routers import auth as auth_router
router.include_router(auth_router.router, prefix="/auth", tags=["auth"])

# External cron entrypoint. Public at the router level because an external
# scheduler has no bearer token; the route authenticates with CRON_SECRET and
# answers 404 when that secret is unset.
from app.routers import cron as cron_router
router.include_router(cron_router.router, prefix="/cron", tags=["cron"])

# Public engagement tracking: a recipient's mail client has no bearer token, so
# these endpoints authenticate the request through a signed token instead.
from app.routers import track as track_router
router.include_router(track_router.router, prefix="/track", tags=["track"])
