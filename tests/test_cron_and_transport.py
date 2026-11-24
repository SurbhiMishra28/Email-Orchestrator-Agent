"""The external cron entrypoint and the transport selector.

These are the two pieces that let the app run on a host that cannot keep
APScheduler alive, so they are covered directly rather than only through the
dashboard.
"""
import pytest


def _enable_cron(monkeypatch, secret="cron-test-secret"):
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "CRON_SECRET", secret)
    return secret


def test_cron_route_is_disabled_without_a_secret(client, monkeypatch):
    """No secret means no route: an unset variable must not open the pipeline."""
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "CRON_SECRET", "")
    response = client.post("/api/cron/tick")
    assert response.status_code == 404


def test_cron_rejects_a_wrong_secret(client, monkeypatch):
    _enable_cron(monkeypatch)
    assert client.post("/api/cron/tick").status_code == 401
    assert (
        client.post(
            "/api/cron/tick", headers={"X-Cron-Secret": "not-the-secret"}
        ).status_code
        == 401
    )


def test_cron_tick_runs_and_reports_without_sending(client, monkeypatch):
    """A tick with the right secret runs the automation and stays dry-run."""
    secret = _enable_cron(monkeypatch)

    calls = []

    async def fake_poll():
        calls.append("inbox")

    from app.main import app as _app  # noqa: F401  (ensures module import order)
    import app.main as main_module

    monkeypatch.setattr(main_module, "_poll_inbox_job", fake_poll)

    response = client.post("/api/cron/tick", headers={"X-Cron-Secret": secret})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["inbox"] == "ok"
    assert calls == ["inbox"]
    # MAIL_SUPPRESS_SEND is on in tests, so a tick may report sends but must not
    # need a relay to answer.
    assert "send" in body or "sending" in body


def test_cron_status_requires_the_secret(client, monkeypatch):
    secret = _enable_cron(monkeypatch)
    assert client.get("/api/cron/status").status_code == 401

    response = client.get("/api/cron/status", headers={"X-Cron-Secret": secret})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["enabled"] is True
    assert body["transport"] in {"smtp", "resend", "gmail_api"}


def test_tick_only_sends_for_tenants_that_opted_into_autopilot(client, monkeypatch):
    """A queued draft is not enough: autopilot must be on for that tenant.

    Without this gate a leftover test tenant -- one that inherited the
    operator's mailbox during signup but never enabled automation -- would be
    drained by the external cron and mail real recipients.
    """
    from app.db import Contact, Draft, SessionLocal, Settings, Template, Tenant
    from app.routers import cron

    db = SessionLocal()
    try:
        opted_out = Tenant(name="Cron Opted Out")
        opted_in = Tenant(name="Cron Opted In")
        db.add_all([opted_out, opted_in])
        db.flush()

        contacts = {}
        for tenant, autopilot in ((opted_out, False), (opted_in, True)):
            db.add(Settings(tenant_id=tenant.id, AUTOPILOT=autopilot))
            db.add(
                Template(
                    tenant_id=tenant.id,
                    name=f"Tpl {tenant.id}",
                    category="intro",
                    subject_template="Hi",
                    body_template="Body",
                )
            )
            contact = Contact(
                tenant_id=tenant.id,
                email=f"cron-{tenant.id}@example.com",
                name=f"Cron {tenant.id}",
            )
            db.add(contact)
            db.flush()
            contacts[tenant.id] = contact.id
        db.commit()

        db.add_all(
            [
                Draft(
                    tenant_id=opted_out.id,
                    contact_id=contacts[opted_out.id],
                    subject="Blocked send",
                    body="Body",
                    status="draft",
                ),
                Draft(
                    tenant_id=opted_in.id,
                    contact_id=contacts[opted_in.id],
                    subject="Allowed send",
                    body="Body",
                    status="draft",
                ),
            ]
        )
        db.commit()

        # Only autopilot-enabled tenants are picked up. The opted-in one still
        # needs a resolvable mailbox, so assert on the flag, not the outcome.
        selected = cron._tenants_with_work()
        assert opted_out.id not in selected
    finally:
        db.rollback()
        db.close()


def test_transport_selection_honours_the_setting(monkeypatch):
    """An explicit MAIL_TRANSPORT wins over the presence of a Resend key."""
    from app.config import settings as app_settings
    from app.services import mailer

    monkeypatch.setattr(app_settings, "RESEND_API_KEY", "re_test_key")

    monkeypatch.setattr(app_settings, "MAIL_TRANSPORT", "auto")
    assert mailer.active_transport() == "resend"

    monkeypatch.setattr(app_settings, "MAIL_TRANSPORT", "smtp")
    assert mailer.active_transport() == "smtp"

    monkeypatch.setattr(app_settings, "MAIL_TRANSPORT", "resend")
    assert mailer.active_transport() == "resend"

    monkeypatch.setattr(app_settings, "MAIL_TRANSPORT", "gmail_api")
    assert mailer.active_transport() == "gmail_api"

    # Resend selected in configuration but no key present falls back to SMTP
    # instead of failing every send.
    monkeypatch.setattr(app_settings, "MAIL_TRANSPORT", "resend")
    monkeypatch.setattr(app_settings, "RESEND_API_KEY", None)
    assert mailer.active_transport() == "smtp"


def test_resend_sender_prefers_the_verified_identity(monkeypatch):
    """RESEND_FROM is what Resend accepts; the SMTP mailbox is only a fallback."""
    from app.config import settings as app_settings
    from app.services import mailer
    from app.services.mailer import SMTPConfigView

    smtp = SMTPConfigView(
        host="smtp.gmail.com",
        port=587,
        user="person@gmail.com",
        password="x",
        sender="person@gmail.com",
    )

    monkeypatch.setattr(app_settings, "RESEND_FROM", "Person <person@verified.test>")
    assert mailer.resend_sender(smtp) == "person@verified.test"

    monkeypatch.setattr(app_settings, "RESEND_FROM", "")
    assert mailer.resend_sender(smtp) == "person@gmail.com"


@pytest.mark.parametrize("transport", ["smtp"])
def test_smtp_transport_reaches_smtp_when_resend_is_configured(
    monkeypatch, transport
):
    """A configured Resend key must not hijack SMTP when SMTP is selected."""
    from types import SimpleNamespace

    from app.config import settings as app_settings
    from app.services import mailer

    monkeypatch.setattr(app_settings, "RESEND_API_KEY", "re_test_key")
    monkeypatch.setattr(app_settings, "MAIL_TRANSPORT", transport)
    monkeypatch.setattr(app_settings, "MAIL_SUPPRESS_SEND", False)

    captured = []

    class FakeServer:
        def login(self, *_args):
            return None

        def send_message(self, message):
            captured.append(message)

        def quit(self):
            return None

    monkeypatch.setattr(mailer, "_open_server", lambda *a, **k: FakeServer())

    def fail_resend(**_kwargs):
        raise AssertionError("Resend must not be used when SMTP is selected")

    monkeypatch.setattr(mailer, "_send_via_resend", fail_resend)

    config = SimpleNamespace(
        host="smtp.example.com",
        port=587,
        user="user@example.com",
        password="secret",
        sender="user@example.com",
        configured=True,
    )

    message_id = mailer.send_email(config, "lead@example.com", "Hi", "Body")
    assert message_id
    assert len(captured) == 1
