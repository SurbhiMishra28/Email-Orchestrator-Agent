"""Calendar link support and unavailable provider behavior."""
from datetime import datetime

import pytest

from app.agents import CalendarAgent


def test_calendly_booking_link_is_returned_when_configured():
    url = "https://calendly.com/example/intro"
    calendar = CalendarAgent(provider="calendly", booking_url=url)

    assert calendar.available()
    assert calendar.generate_meeting_link() == url
    assert calendar.list_calendars()[0]["url"] == url


def test_unconfigured_and_stub_calendar_providers_are_not_reported_available():
    for calendar in (
        CalendarAgent(provider="calendly"),
        CalendarAgent(provider="google"),
        CalendarAgent(provider="microsoft"),
        CalendarAgent(provider="manual"),
    ):
        assert not calendar.available()
        assert calendar.list_calendars() == []
        assert calendar.generate_meeting_link() == ""


def test_invalid_or_non_calendly_booking_urls_are_unavailable():
    for url in ("not-a-url", "http://calendly.com/example", "https://example.com/book"):
        assert not CalendarAgent(provider="calendly", booking_url=url).available()


def test_calendly_booking_link_does_not_claim_to_create_an_event():
    calendar = CalendarAgent(
        provider="calendly",
        booking_url="https://calendly.com/example/intro",
    )

    with pytest.raises(ValueError, match="invitees book"):
        calendar.create_event("Intro", datetime.now())
