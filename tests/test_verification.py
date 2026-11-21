"""Email verification classification tests."""
from app.services import verification


def test_dns_timeout_is_inconclusive(monkeypatch):
    monkeypatch.setattr(
        verification,
        "check_mx_records",
        lambda domain: (False, [], "DNS timeout"),
    )

    result = verification.verify_email("person@example.com")

    assert result.status == "inconclusive"
    assert result.mx_check == "unreachable"


def test_missing_mx_records_are_undeliverable(monkeypatch):
    monkeypatch.setattr(
        verification,
        "check_mx_records",
        lambda domain: (False, [], "No MX records found"),
    )

    result = verification.verify_email("person@example.com")

    assert result.status == "undeliverable"
    assert result.mx_check == "failed"
