"""Smoke-check the serverless configuration end to end.

Runs the real app against the local database with the environment a Vercel
deployment uses: no scheduler, no startup DDL, no WebSocket, Basic auth on.
Nothing here sends mail.
"""
import base64
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ["ENABLE_BACKGROUND_JOBS"] = "false"
os.environ["AUTO_INIT_DB"] = "false"
os.environ["ENABLE_LIVE_LOGS"] = "false"
os.environ["BASIC_AUTH_USER"] = "admin"
os.environ["BASIC_AUTH_PASSWORD"] = "smoke-secret"
os.environ["MAIL_SUPPRESS_SEND"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402

assert settings.ENABLE_BACKGROUND_JOBS is False
assert settings.AUTO_INIT_DB is False
assert settings.ENABLE_LIVE_LOGS is False

token = base64.b64encode(b"admin:smoke-secret").decode()
auth = {"Authorization": f"Basic {token}"}

with TestClient(app) as client:
    anon = client.get("/api/state")
    print("anonymous /api/state ->", anon.status_code)
    assert anon.status_code == 401, anon.status_code

    health = client.get("/health")
    print("anonymous /health ->", health.status_code, health.json()["status"])
    assert health.status_code == 200

    state = client.get("/api/state", headers=auth)
    print("authenticated /api/state ->", state.status_code)
    assert state.status_code == 200, state.text
    print("  live_logs flag:", state.json().get("live_logs"))
    assert state.json().get("live_logs") is False

    track = client.get("/api/track/open/smoke-token")
    print("anonymous /api/track/open ->", track.status_code)
    assert track.status_code in (200, 404)

    ws = client.get("/ws/live-logs")
    print("websocket route ->", ws.status_code)
    # The route is not registered; the gate answers first, and without the gate
    # this path would fall through to the SPA fallback.
    assert ws.status_code in (401, 403, 404, 426), ws.status_code

    ws_auth = client.get("/ws/live-logs", headers=auth)
    print("authenticated websocket route ->", ws_auth.status_code)
    assert ws_auth.status_code != 101

print("serverless smoke check passed")