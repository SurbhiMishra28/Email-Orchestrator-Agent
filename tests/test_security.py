"""The HTTP Basic auth gate.

The app has no login screen, so on a public URL this middleware is the only
thing between the address book and the internet. These tests pin down both
directions: that it enforces when configured, and that it stays out of the way
when it is not.
"""
import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings as app_settings

USER = "admin"
PASSWORD = "correct horse battery staple"


def _header(user: str = USER, password: str = PASSWORD) -> dict:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _build_app() -> FastAPI:
    """A minimal app carrying one route from each exemption category."""
    app = FastAPI()

    @app.get("/api/state")
    def state():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/")
    def index():
        return {"ok": True}

    @app.get("/index.html")
    def index_html():
        return {"ok": True}

    @app.get("/assets/{asset}")
    def asset(asset: str):
        return {"ok": True, "asset": asset}

    @app.get("/login")
    def login_page():
        return {"ok": True}

    @app.get("/app")
    def app_page():
        return {"ok": True}

    @app.post("/api/auth/demo")
    def demo():
        return {"access_token": "demo-token"}

    @app.get("/api/track/open/{token}")
    def track_open(token: str):
        return {"ok": True, "token": token}

    @app.get("/api/track/click/{token}")
    def track_click(token: str):
        return {"ok": True, "token": token}

    @app.post("/api/cron/tick")
    def cron_tick():
        return {"ok": True}

    return app


def _client(monkeypatch, user=USER, password=PASSWORD) -> TestClient:
    from app import security

    monkeypatch.setattr(app_settings, "BASIC_AUTH_USER", user)
    monkeypatch.setattr(app_settings, "BASIC_AUTH_PASSWORD", password)

    app = _build_app()
    assert security.install(app) is True
    return TestClient(app)


def test_gate_is_disabled_when_credentials_are_blank(monkeypatch):
    from app import security

    monkeypatch.setattr(app_settings, "BASIC_AUTH_USER", "")
    monkeypatch.setattr(app_settings, "BASIC_AUTH_PASSWORD", "")

    app = _build_app()
    assert security.install(app) is False

    response = TestClient(app).get("/api/state")
    assert response.status_code == 200


def test_gate_is_disabled_when_only_one_value_is_set(monkeypatch):
    """A half-configured gate must not lock everyone out."""
    from app import security

    monkeypatch.setattr(app_settings, "BASIC_AUTH_USER", USER)
    monkeypatch.setattr(app_settings, "BASIC_AUTH_PASSWORD", "")

    app = _build_app()
    assert security.install(app) is False
    assert TestClient(app).get("/api/state").status_code == 200


def test_missing_credentials_are_rejected_with_a_challenge(monkeypatch):
    response = _client(monkeypatch).get("/api/state")

    assert response.status_code == 401
    assert "Basic" in response.headers.get("WWW-Authenticate", "")


def test_correct_credentials_are_accepted(monkeypatch):
    response = _client(monkeypatch).get("/api/state", headers=_header())

    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.parametrize(
    "user,password",
    [(USER, "wrong"), ("wrong", PASSWORD), ("wrong", "wrong")],
)
def test_wrong_credentials_are_rejected(monkeypatch, user, password):
    response = _client(monkeypatch).get(
        "/api/state", headers=_header(user=user, password=password)
    )

    assert response.status_code == 401


def test_malformed_authorization_header_is_rejected(monkeypatch):
    client = _client(monkeypatch)

    for value in ("", "Basic", "Bearer abc", "Basic !!!not-base64!!!"):
        response = client.get("/api/state", headers={"Authorization": value})
        assert response.status_code == 401, value


def test_health_is_exempt(monkeypatch):
    """The platform probe must not need credentials, or every deploy looks dead."""
    response = _client(monkeypatch).get("/health")

    assert response.status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/api/track/open/abc123",
        "/api/track/click/abc123",
    ],
)
def test_recipient_tracking_routes_are_exempt(monkeypatch, path):
    """Recipients' mail clients and browsers hold no credentials."""
    response = _client(monkeypatch).get(path)

    assert response.status_code == 200, path


def test_cron_route_is_exempt(monkeypatch):
    """The external scheduler authenticates with X-Cron-Secret, not Basic."""
    response = _client(monkeypatch).post("/api/cron/tick")

    assert response.status_code == 200


@pytest.mark.parametrize(
    "path",
    ["/", "/index.html", "/assets/index-abc123.js", "/assets/index-abc123.css"],
)
def test_static_shell_is_exempt(monkeypatch, path):
    """The sign-in page must load before any credentials exist.

    The bundle contains no tenant data — every value it renders comes from the
    gated API — so serving it openly is what makes a custom login possible.
    """
    response = _client(monkeypatch).get(path)

    assert response.status_code == 200, path


def test_static_exemption_does_not_open_the_api(monkeypatch):
    """Exempting the shell must not exempt the data behind it."""
    client = _client(monkeypatch)

    assert client.get("/").status_code == 200
    assert client.get("/api/state").status_code == 401


def test_exemption_does_not_leak_to_lookalike_paths(monkeypatch):
    """``/api/trackery`` must not be treated as ``/api/track``."""
    app = FastAPI()

    @app.get("/api/trackery")
    def lookalike():
        return {"ok": True}

    from app import security

    monkeypatch.setattr(app_settings, "BASIC_AUTH_USER", USER)
    monkeypatch.setattr(app_settings, "BASIC_AUTH_PASSWORD", PASSWORD)
    security.install(app)

    assert TestClient(app).get("/api/trackery").status_code == 401


def test_trailing_slash_still_matches_an_exempt_prefix(monkeypatch):
    """FastAPI redirects ``/health/``; the gate must not 401 the redirect target."""
    assert _client(monkeypatch).get("/health/").status_code in (200, 307)

@pytest.mark.parametrize("path", ["/login", "/app", "/assets/index-abc.js"])
def test_spa_routes_are_exempt(monkeypatch, path):
    """The marketing page, sign-in page and bundle load before credentials."""
    assert _client(monkeypatch).get(path).status_code == 200, path


def test_demo_endpoint_is_exempt(monkeypatch):
    """The demo button has to work for a visitor with no account."""
    assert _client(monkeypatch).post("/api/auth/demo").status_code == 200


def test_valid_bearer_token_is_accepted(monkeypatch):
    """The sign-in page exchanges credentials for a JWT."""
    from app.auth import create_access_token

    token = create_access_token({"sub": 1, "tenant_id": 1})
    response = _client(monkeypatch).get(
        "/api/state", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    "header",
    ["Bearer nonsense", "Bearer", "Basic !!!not-base64!!!"],
)
def test_invalid_bearer_token_is_rejected(monkeypatch, header):
    assert _client(monkeypatch).get("/api/state", headers={"Authorization": header}).status_code == 401
