"""Opt-in open and click tracking for outbound mail.

Tracking is a per-tenant privacy toggle (``Settings.tracking_enabled``), default
off. When it is off nothing here runs and mail stays plain text, exactly as the
README promises. When a tenant turns it on, each tracked draft is turned into a
multipart message: the plain-text part is unchanged and the HTML part carries a
1x1 open pixel and wrapped links.

Tokens are HMAC-signed with the application secret and encode only the draft and
tenant ids, so no schema change is needed and a forged token cannot attribute
engagement to another tenant.
"""
import base64
import hashlib
import hmac
import html as html_module
import logging
import re
from typing import Optional, Tuple
from urllib.parse import quote, urlparse

from app.db import Draft, Event, Settings

logger = logging.getLogger(__name__)

# A transparent 1x1 GIF. Served inline so opening the message never depends on
# a second request to a static host.
PIXEL_GIF = base64.b64decode(
    b"R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)

LINK_PATTERN = re.compile(r"https?://[^\s<>\"']+")


def _secret() -> bytes:
    """Application signing secret, imported lazily to avoid an import cycle."""
    from app.auth import SECRET_KEY

    return SECRET_KEY.encode("utf-8")


def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def make_token(draft_id: int, tenant_id: int) -> str:
    """Return an opaque, signed token for one draft."""
    raw = f"{int(draft_id)}:{int(tenant_id)}"
    payload = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{payload}.{_sign(payload)}"


def parse_token(token: str) -> Optional[Tuple[int, int]]:
    """Return ``(draft_id, tenant_id)`` for a valid token, else ``None``."""
    if not token or "." not in token:
        return None
    payload, _, signature = token.partition(".")
    if not payload or not signature:
        return None
    if not hmac.compare_digest(signature, _sign(payload)):
        return None
    padded = payload + "=" * (-len(payload) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        draft_id, tenant_id = raw.split(":", 1)
        return int(draft_id), int(tenant_id)
    except (ValueError, UnicodeDecodeError):
        return None


def tracking_enabled(db, tenant_id: Optional[int]) -> bool:
    """True when this tenant has opted into engagement tracking."""
    if tenant_id is None:
        return False
    row = db.query(Settings.tracking_enabled).filter(
        Settings.tenant_id == tenant_id
    ).first()
    return bool(row[0]) if row else False


def base_url() -> str:
    from app.config import settings as app_settings

    return (app_settings.PUBLIC_BASE_URL or "").rstrip("/")


def open_url(token: str) -> str:
    return f"{base_url()}/api/track/open/{token}"


def click_url(token: str, target: str) -> str:
    return f"{base_url()}/api/track/click/{token}?url={quote(target, safe='')}"


def _linkify(text: str) -> str:
    """Escape ``text`` and turn bare URLs into anchors."""
    escaped = html_module.escape(text)
    return LINK_PATTERN.sub(
        lambda match: f'<a href="{match.group(0)}">{match.group(0)}</a>',
        escaped,
    )


def body_to_html(body: str) -> str:
    """Render a plain-text body as minimal HTML, preserving paragraph breaks."""
    paragraphs = [part for part in (body or "").split("\n\n")]
    rendered = []
    for paragraph in paragraphs:
        lines = [_linkify(line) for line in paragraph.split("\n")]
        rendered.append("<p>" + "<br>".join(lines) + "</p>")
    return "<div>" + "".join(rendered) + "</div>"


def _wrap_anchors(html_body: str, token: str) -> str:
    """Rewrite every anchor href to go through the signed click endpoint."""

    def replace(match: re.Match) -> str:
        target = match.group(2)
        if target.startswith(("mailto:", "tel:", "#")):
            return match.group(0)
        if not target.lower().startswith(("http://", "https://")):
            return match.group(0)
        return f'{match.group(1)}{click_url(token, target)}"'

    return re.sub(r'(<a\s[^>]*href=")([^"]*)"', replace, html_body)


def build_html_body(body: str, draft_id: int, tenant_id: int) -> str:
    """HTML alternative for one draft: wrapped links plus the open pixel."""
    token = make_token(draft_id, tenant_id)
    html_body = _wrap_anchors(body_to_html(body), token)
    pixel = (
        f'<img src="{open_url(token)}" width="1" height="1" alt="" '
        'style="border:0;display:block" />'
    )
    return html_body + pixel


def record_event(
    db,
    event_type: str,
    draft_id: int,
    tenant_id: int,
    extra: Optional[dict] = None,
) -> None:
    """Persist one engagement event for the draft's contact."""
    contact_id = (
        db.query(Draft.contact_id).filter(
            Draft.id == draft_id, Draft.tenant_id == tenant_id
        ).scalar()
    )
    data = {"draft_id": draft_id}
    if extra:
        data.update(extra)
    db.add(
        Event(
            tenant_id=tenant_id,
            contact_id=contact_id,
            event_type=event_type,
            data=data,
        )
    )
    db.commit()


def record_open(db, token: str) -> bool:
    parsed = parse_token(token)
    if not parsed:
        return False
    draft_id, tenant_id = parsed
    record_event(db, "email_opened", draft_id, tenant_id)
    return True


def record_click(db, token: str, target: Optional[str]) -> Optional[str]:
    """Record the click and return the validated redirect target."""
    parsed = parse_token(token)
    if not parsed:
        return None
    draft_id, tenant_id = parsed
    safe_target = None
    if target:
        parsed_url = urlparse(target)
        if parsed_url.scheme in {"http", "https"} and parsed_url.netloc:
            safe_target = target
    record_event(
        db,
        "link_clicked",
        draft_id,
        tenant_id,
        {"url": safe_target} if safe_target else None,
    )
    return safe_target or base_url()


def send_html_for_draft(db, draft, tenant_id: int) -> Optional[str]:
    """Return the tracked HTML part for ``draft`` when tracking applies."""
    if not tracking_enabled(db, tenant_id):
        return None
    if (draft.variables or {}).get("message_kind") == "auto_reply":
        return None
    return build_html_body(draft.body or "", draft.id, tenant_id)
