import base64
from email import message_from_bytes
import httpx
import pytest

from app.config import settings
from app.services import google_mail, inbox, mailer
from app.services.mailer import SMTPConfigView


@pytest.fixture
def gmail_oauth(monkeypatch):
    monkeypatch.setattr(settings, "MAIL_TRANSPORT", "gmail_api")
    monkeypatch.setattr(settings, "GMAIL_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setattr(settings, "GMAIL_OAUTH_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(settings, "GMAIL_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setattr(settings, "GMAIL_USER_EMAIL", "owner@gmail.com")
    monkeypatch.setattr(settings, "MAIL_SUPPRESS_SEND", False)
    google_mail._token_cache.clear()
    yield google_mail.config_from_settings()
    google_mail._token_cache.clear()


def test_gmail_api_refreshes_token_and_tests_the_authorized_account(
    gmail_oauth, monkeypatch
):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(("token", url, kwargs["data"]))
        return httpx.Response(200, json={"access_token": "access-token", "expires_in": 3600})

    def fake_request(method, url, **kwargs):
        calls.append(("api", method, url, kwargs["headers"]["Authorization"]))
        return httpx.Response(
            200,
            json={"emailAddress": "owner@gmail.com", "messagesTotal": 3},
        )

    monkeypatch.setattr(google_mail.httpx, "post", fake_post)
    monkeypatch.setattr(google_mail.httpx, "request", fake_request)

    result = google_mail.test_connection(gmail_oauth)

    assert result["ok"] is True
    assert result["email"] == "owner@gmail.com"
    assert [call[0] for call in calls] == ["token", "api"]
    assert calls[0][2]["refresh_token"] == "refresh-token"
    assert calls[1][3] == "Bearer access-token"


def test_gmail_status_endpoints_do_not_expose_oauth_secrets(client, gmail_oauth):
    smtp_response = client.get("/api/smtp/status")
    inbox_response = client.get("/api/inbox/status")

    assert smtp_response.status_code == 200
    assert inbox_response.status_code == 200
    assert smtp_response.json()["transport"] == "gmail_api"
    assert inbox_response.json()["transport"] == "gmail_api"
    assert smtp_response.json()["configured"] is False
    assert inbox_response.json()["configured"] is False
    assert gmail_oauth.refresh_token not in smtp_response.text
    assert gmail_oauth.client_secret not in inbox_response.text


def test_gmail_api_sends_a_mime_message_over_https(gmail_oauth, monkeypatch):
    captured = []

    def fake_send(config, raw_message):
        captured.append((config, raw_message))
        return {"id": "gmail-message-id"}

    monkeypatch.setattr(google_mail, "send_raw_message", fake_send)

    message_id = mailer.send_email(
        SMTPConfigView(
            host="gmail.googleapis.com",
            port=443,
            sender="owner@gmail.com",
            source="environment",
        ),
        "recipient@example.net",
        "Hello",
        "Plain text",
        from_name="Operator",
        html_body="<p>HTML</p>",
    )

    assert captured[0][0] == gmail_oauth
    raw_bytes = base64.urlsafe_b64decode(captured[0][1] + "===")
    message = message_from_bytes(raw_bytes)
    assert message["From"] == "Operator <owner@gmail.com>"
    assert message["To"] == "recipient@example.net"
    assert message["Subject"] == "Hello"
    assert message.is_multipart()
    assert message_id == message["Message-ID"]


def test_gmail_api_rejects_a_sender_that_is_not_the_authorized_account(
    gmail_oauth,
):
    with pytest.raises(mailer.MailDeliveryError, match="only send from"):
        mailer.send_email(
            SMTPConfigView(
                host="gmail.googleapis.com",
                port=443,
                sender="owner@gmail.com",
                source="environment",
            ),
            "recipient@example.net",
            "Hello",
            "Body",
            from_email="someone-else@gmail.com",
        )


def test_gmail_api_transport_requires_complete_oauth_credentials(monkeypatch):
    monkeypatch.setattr(settings, "MAIL_TRANSPORT", "gmail_api")
    monkeypatch.setattr(settings, "GMAIL_OAUTH_CLIENT_ID", "")

    with pytest.raises(mailer.MailNotConfigured, match="Gmail API"):
        mailer.send_email(
            SMTPConfigView(
                host="gmail.googleapis.com",
                port=443,
                sender="owner@gmail.com",
                source="environment",
            ),
            "recipient@example.net",
            "Hello",
            "Body",
        )


def test_gmail_inbox_fetch_uses_message_ids_and_stops_at_known_mail(
    gmail_oauth, monkeypatch
):
    seen = []
    metadata = {
        "new-old": {
            "payload": {
                "headers": [
                    {"name": "From", "value": "Sender <sender@example.net>"},
                    {"name": "Subject", "value": "Older reply"},
                ]
            },
            "snippet": "older reply",
            "internalDate": "1760000000000",
        },
        "new-new": {
            "payload": {
                "headers": [
                    {"name": "From", "value": "sender@example.net"},
                    {"name": "Subject", "value": "Newer reply"},
                ]
            },
            "snippet": "newer reply",
            "internalDate": "1760000060000",
        },
    }

    def fake_list(_config, *, max_results, page_token=None):
        seen.append((max_results, page_token))
        return {
            "messages": [
                {"id": "new-new"},
                {"id": "new-old"},
                {"id": "already-seen"},
            ]
        }

    monkeypatch.setattr(google_mail, "list_messages", fake_list)
    monkeypatch.setattr(
        google_mail,
        "get_message_metadata",
        lambda _config, message_id: metadata[message_id],
    )

    fetched = inbox.fetch_gmail_recent(2, {"already-seen"})

    assert [item["uid"] for item in fetched] == ["new-old", "new-new"]
    assert fetched[0]["subject"] == "Older reply"
    assert fetched[0]["snippet"] == "older reply"
    assert seen == [(500, None)]


def test_first_gmail_inbox_sync_fetches_only_the_latest_batch(
    gmail_oauth, monkeypatch
):
    seen = []
    details = {
        message_id: {
            "payload": {"headers": []},
            "snippet": message_id,
            "internalDate": "1760000000000",
        }
        for message_id in ("latest", "older")
    }

    def fake_list(_config, *, max_results, page_token=None):
        seen.append((max_results, page_token))
        return {"messages": [{"id": "latest"}, {"id": "older"}], "nextPageToken": "ignored"}

    monkeypatch.setattr(google_mail, "list_messages", fake_list)
    monkeypatch.setattr(
        google_mail,
        "get_message_metadata",
        lambda _config, message_id: details[message_id],
    )

    fetched = inbox.fetch_gmail_recent(2, set())

    assert [item["uid"] for item in fetched] == ["older", "latest"]
    assert seen == [(2, None)]
