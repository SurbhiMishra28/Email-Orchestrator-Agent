"""Template rendering: footers must be expanded, not shipped as placeholders."""
import asyncio
from types import SimpleNamespace

import pytest

from app.agents import _render_footer, expand_template_variables

VARIABLES = {
    "first_name": "Ada",
    "company": "Acme",
    "business_name": "Skora Infotech",
    "sender_name": "Surbhi Mishra",
    "sender_role": "Sales Manager",
    "company_website": "https://example.org",
    "footer_text": "Global footer text",
}

FOOTER = (
    "This is from {{sender_name}} from {{business_name}}'s team.\n"
    "---\n{{sender_name}} | {{sender_role}}\n{{company_website}}"
)


def test_render_footer_expands_placeholders():
    template = SimpleNamespace(footer_template=FOOTER)

    footer = _render_footer(template, VARIABLES)

    assert "{{" not in footer
    assert "Surbhi Mishra | Sales Manager" in footer
    assert "https://example.org" in footer
    assert "Skora Infotech" in footer


def test_render_footer_falls_back_to_settings_footer_text():
    template = SimpleNamespace(footer_template="")

    assert _render_footer(template, VARIABLES) == "Global footer text"


def test_render_footer_handles_missing_template():
    assert _render_footer(SimpleNamespace(), VARIABLES) == "Global footer text"


def test_render_footer_empty_when_nothing_configured():
    assert _render_footer(SimpleNamespace(footer_template=""), {}) == ""


def test_expand_does_not_leave_placeholders():
    body = expand_template_variables("Hi {{first_name}} at {{company}}", VARIABLES)

    assert body == "Hi Ada at Acme"
