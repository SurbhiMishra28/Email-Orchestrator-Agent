"""Normalise contact CSV files the way real exports arrive.

Brevo, Mailchimp, Google Contacts and Excel all produce different headers for
the same data: ``Email`` vs ``email`` vs ``E-mail``, ``First Name``/``Last Name``
instead of ``name``, commas vs semicolons, and often a UTF-8 BOM at the front of
the file. Reading those with a bare ``csv.DictReader`` and ``row.get("email")``
silently imports nothing, which is what "import does not work" looked like.

This module turns any of those shapes into a list of dicts with stable keys so
both import endpoints share one parser.
"""
import csv
import io
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

# Canonical field -> header spellings seen in the wild.
HEADER_ALIASES: Dict[str, set] = {
    "email": {
        "email",
        "e-mail",
        "email address",
        "emailaddress",
        "email id",
        "mail",
        "work email",
        "e mail",
    },
    "name": {"name", "full name", "fullname", "contact name", "display name"},
    "first_name": {"first name", "firstname", "given name", "forename"},
    "last_name": {"last name", "lastname", "surname", "family name"},
    "company": {
        "company",
        "company name",
        "organization",
        "organisation",
        "org",
        "business",
    },
    "role": {"role", "job title", "title", "position", "designation"},
    "phone": {
        "phone",
        "phone number",
        "mobile",
        "mobile number",
        "telephone",
        "tel",
        "cell",
    },
    "linkedin": {"linkedin", "linkedin url", "linkedin profile", "linkedin profile url"},
    "notes": {"notes", "note", "comments", "comment", "remarks"},
    "tags": {"tags", "tag", "labels", "label", "groups"},
    "email_permission": {
        "email_permission",
        "email permission",
        "permission",
        "opt-in",
        "opt in",
        "opted in",
        "subscribed",
    },
    "industry": {"industry", "sector", "vertical"},
}

_ALIAS_LOOKUP = {
    alias: field for field, aliases in HEADER_ALIASES.items() for alias in aliases
}


class CsvImportError(ValueError):
    """Raised when the file cannot be understood at all."""


def _clean(value) -> str:
    return (value or "").strip().strip('"').strip()


def normalise_header(header: str) -> str:
    """Map a raw CSV header to a canonical field name (or ``""``)."""
    text = _clean(header).lstrip("\ufeff")
    # Excel and Brevo sometimes append markers such as "Email *" or "Email [1]".
    text = text.replace("*", " ").replace("[", " ").replace("]", " ")
    text = " ".join(text.split()).lower()
    if text in _ALIAS_LOOKUP:
        return _ALIAS_LOOKUP[text]
    # Fall back to a separator-insensitive match: "email_address" -> "email address".
    collapsed = text.replace("_", " ").replace("-", " ").strip()
    collapsed = " ".join(collapsed.split())
    if collapsed in _ALIAS_LOOKUP:
        return _ALIAS_LOOKUP[collapsed]
    return ""


def _sniff_delimiter(sample: str) -> str:
    """Pick the delimiter exports actually use, defaulting to a comma."""
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        first_line = sample.splitlines()[0] if sample.splitlines() else ""
        for candidate in (";", "\t", "|"):
            if candidate in first_line:
                return candidate
        return ","


def split_tags(raw) -> List[str]:
    """Split a tags cell written with commas, semicolons or pipes."""
    text = _clean(raw)
    if not text:
        return []
    for separator in (";", "|"):
        if separator in text:
            parts = text.split(separator)
            break
    else:
        parts = text.split(",")
    seen, tags = set(), []
    for part in parts:
        tag = part.strip()
        if tag and tag.lower() not in seen:
            seen.add(tag.lower())
            tags.append(tag)
    return tags


def parse_contacts_csv(text: str) -> Tuple[List[Dict[str, object]], List[str]]:
    """Parse ``text`` into normalised rows plus a list of row-level errors.

    Raises :class:`CsvImportError` when no email column can be found, so the
    caller can answer with a useful message instead of "imported 0".
    """
    if not text or not text.strip():
        raise CsvImportError("The CSV is empty.")

    # A BOM turns the first header into "\ufeffemail", which matches no alias.
    cleaned = text.lstrip("\ufeff")
    delimiter = _sniff_delimiter(cleaned[:4096])

    reader = csv.reader(io.StringIO(cleaned), delimiter=delimiter)
    try:
        raw_headers = next(reader)
    except StopIteration:
        raise CsvImportError("The CSV has no header row.")

    headers = [normalise_header(header) for header in raw_headers]
    if "email" not in headers:
        found = ", ".join(_clean(h) for h in raw_headers) or "(none)"
        raise CsvImportError(
            "The CSV needs an email column. Columns found: " + found
        )

    rows: List[Dict[str, object]] = []
    errors: List[str] = []
    for line_number, values in enumerate(reader, start=2):
        if not any(_clean(value) for value in values):
            continue  # blank line

        row: Dict[str, object] = {}
        for index, field in enumerate(headers):
            if not field:
                continue
            value = values[index] if index < len(values) else ""
            if field == "tags":
                row["tags"] = split_tags(value)
            elif field == "email_permission":
                row["email_permission"] = _clean(value).lower()
            elif field not in row:
                row[field] = _clean(value)

        email = str(row.get("email") or "")
        if not email:
            errors.append(f"Line {line_number}: missing email")
            continue

        first = str(row.get("first_name") or "")
        last = str(row.get("last_name") or "")
        if not row.get("name"):
            combined = " ".join(part for part in (first, last) if part).strip()
            if combined:
                row["name"] = combined
        row.pop("first_name", None)
        row.pop("last_name", None)
        if not row.get("name"):
            row.pop("name", None)
        rows.append(row)

    return rows, errors
