"""Contacts API router (tenant-scoped)."""
import csv
from io import StringIO
from typing import List

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Body
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app.db import (
    Contact,
    ContactListMember,
    Draft,
    EmailVerification,
    Event,
    Log,
    SessionLocal,
    Settings,
)
from app.deps import current_tenant_id
from app.models.schemas import ContactCreate, ContactOut, ContactUpdate, CSVImport

router = APIRouter()


class EligibilityUpdate(BaseModel):
    eligible_to_email: bool


class TagPayload(BaseModel):
    tag: str | None = None
    tags: List[str] | None = None


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============ LIST & CREATE (index routes, no path parameters) ============

@router.get("", response_model=List[ContactOut])
def list_contacts(
    skip: int = 0,
    limit: int = 1000,
    list_id: int = Query(None),
    tenant_id: int = Depends(current_tenant_id),
):
    """List the tenant's contacts, optionally limited to one segment."""
    db = SessionLocal()
    try:
        query = db.query(Contact).filter(Contact.tenant_id == tenant_id)
        if list_id is not None:
            from app.db import ContactListMember

            query = query.join(
                ContactListMember, ContactListMember.contact_id == Contact.id
            ).filter(
                ContactListMember.list_id == list_id,
                ContactListMember.tenant_id == tenant_id,
            )
        contacts = (
            query.order_by(Contact.id.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return contacts
    finally:
        db.close()


@router.post("", response_model=ContactOut)
def create_contact(contact: ContactCreate, tenant_id: int = Depends(current_tenant_id)):
    db = SessionLocal()
    try:
        # Check if email already exists for this tenant
        existing = (
            db.query(Contact)
            .filter(Contact.tenant_id == tenant_id, Contact.email == contact.email)
            .first()
        )
        if existing:
            raise HTTPException(status_code=400, detail=f"Contact with email {contact.email} already exists")
        
        db_contact = Contact(**contact.model_dump(), tenant_id=tenant_id)
        db.add(db_contact)
        try:
            db.commit()
        except IntegrityError:
            # The email column is globally unique on legacy databases.
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="A contact with this email address already exists.",
            )
        db.refresh(db_contact)
        
        log = Log(message=f"Created contact: {contact.email}", level="info", tenant_id=tenant_id)
        db.add(log)
        db.commit()
        
        # Convert to dict to avoid detached instance issues
        return ContactOut.model_validate(db_contact)
    finally:
        db.close()


@router.post("/import")
def import_csv(
    csv_data: CSVImport,
    background_tasks: BackgroundTasks,
    tenant_id: int = Depends(current_tenant_id),
):
    db = SessionLocal()
    try:
        file_obj = StringIO(csv_data.csv)
        reader = csv.DictReader(file_obj)
        
        imported = 0
        updated = 0
        skipped = 0
        errors = []
        eligible_emails = set()
        
        for row in reader:
            try:
                email = row.get("email", row.get("Email", "")).strip()
                if not email:
                    skipped += 1
                    continue

                try:
                    email = validate_email(
                        email, check_deliverability=False
                    ).normalized
                except EmailNotValidError as exc:
                    errors.append(f"{email}: {exc}")
                    continue
                
                permission_raw = (
                    row.get("email_permission")
                    or row.get("Email_Permission")
                    or ""
                ).strip().lower()
                permission_known = permission_raw in {
                    "true", "1", "yes", "y", "false", "0", "no", "n",
                }
                permission = permission_raw in {"true", "1", "yes", "y"}
                if not permission_known:
                    # No permission column: fall back to the request's default
                    # rather than silently importing unusable contacts.
                    permission = csv_data.default_eligible
                existing = (
                    db.query(Contact)
                    .filter(Contact.tenant_id == tenant_id, Contact.email == email)
                    .first()
                )
                if existing:
                    # Existing contacts are refreshed in place, not duplicated.
                    for field in ["name", "company", "role", "phone", "linkedin", "notes"]:
                        if field in row:
                            setattr(existing, field, row[field])
                    if permission_known:
                        existing.eligible_to_email = permission
                    if existing.eligible_to_email:
                        eligible_emails.add(email)
                    updated += 1
                else:
                    # Create new
                    contact_data = {
                        "email": email,
                        "name": row.get("name", row.get("Name", "")),
                        "company": row.get("company", row.get("Company", "")),
                        "role": row.get("role", row.get("Role", "")),
                        "phone": row.get("phone", row.get("Phone", "")),
                        "linkedin": row.get("linkedin", row.get("LinkedIn", "")),
                        "notes": row.get("notes", row.get("Notes", "")),
                    }
                    if permission_known:
                        contact_data["eligible_to_email"] = permission
                    else:
                        # No permission column: use the request default so the
                        # imported row is actually mailable.
                        contact_data["eligible_to_email"] = csv_data.default_eligible
                    if permission:
                        eligible_emails.add(email)
                    db_contact = Contact(
                        **{k: v for k, v in contact_data.items() if v},
                        tenant_id=tenant_id,
                    )
                    db.add(db_contact)
                    imported += 1
            except Exception as e:
                errors.append(str(e))
        
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="One or more contacts already exist for another tenant.",
            )

        eligible_ids = [
            row[0]
            for row in db.query(Contact.id)
            .filter(
                Contact.tenant_id == tenant_id,
                Contact.email.in_(eligible_emails),
            )
            .all()
        ] if eligible_emails else []
        settings = (
            db.query(Settings).filter(Settings.tenant_id == tenant_id).first()
        )
        automation_enabled = bool(settings and settings.AUTOPILOT and settings.AUTO_APPROVE)
        if eligible_ids and automation_enabled:
            from app.services.outreach import send_intro_to_imported_contacts

            background_tasks.add_task(
                send_intro_to_imported_contacts, eligible_ids, tenant_id
            )
        
        log = Log(message=f"Imported {imported} contacts from CSV ({updated} updated)", level="info", tenant_id=tenant_id)
        db.add(log)
        db.commit()
        
        return {
            "imported": imported,
            "updated": updated,
            "skipped": skipped,
            "automatic_outreach_queued": len(eligible_ids) if automation_enabled else 0,
            "errors": errors[:10] if errors else []
        }
    finally:
        db.close()


# ============ TAG ENDPOINTS (placed before parameterized routes) ============

@router.get("/tags")
def get_all_tags(tenant_id: int = Depends(current_tenant_id)):
    """Get all unique tags across the tenant's contacts."""
    db = SessionLocal()
    try:
        contacts = (
            db.query(Contact)
            .filter(Contact.tenant_id == tenant_id, Contact.tags != None)
            .all()
        )
        all_tags = set()
        for contact in contacts:
            if contact.tags:
                all_tags.update(contact.tags)
        return {"tags": sorted(list(all_tags))}
    finally:
        db.close()


def _get_tenant_contact(db, contact_id: int, tenant_id: int) -> Contact:
    contact = (
        db.query(Contact)
        .filter(Contact.id == contact_id, Contact.tenant_id == tenant_id)
        .first()
    )
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


@router.post("/{contact_id}/tags")
def add_tag(
    contact_id: int,
    payload: TagPayload | None = Body(None),
    tag: str = Query(None, alias="tag"),
    tenant_id: int = Depends(current_tenant_id),
):
    """Add one or more tags to a contact."""

    incoming: List[str] = []
    if tag:
        incoming.append(tag)
    if payload is not None:
        if payload.tag:
            incoming.append(payload.tag)
        if payload.tags:
            incoming.extend(payload.tags)

    tags_to_add = [t.strip() for t in incoming if t and t.strip()]
    if not tags_to_add:
        raise HTTPException(status_code=400, detail="tag parameter is required")

    db = SessionLocal()
    try:
        db_contact = _get_tenant_contact(db, contact_id, tenant_id)

        current = list(db_contact.tags or [])
        changed = False
        for candidate in tags_to_add:
            if candidate not in current:
                current.append(candidate)
                changed = True
        if changed:
            db_contact.tags = current
            db.commit()
            db.refresh(db_contact)

        return {
            "message": f"Tag(s) {', '.join(tags_to_add)} added to contact",
            "tags": db_contact.tags or [],
        }
    finally:
        db.close()


@router.delete("/{contact_id}/tags/{tag}")
def remove_tag(
    contact_id: int,
    tag: str,
    tenant_id: int = Depends(current_tenant_id),
):
    """Remove a tag from a contact."""
    db = SessionLocal()
    try:
        db_contact = _get_tenant_contact(db, contact_id, tenant_id)
        
        # Remove tag if present
        if db_contact.tags and tag in db_contact.tags:
            db_contact.tags = [t for t in db_contact.tags if t != tag]
            db.commit()
            db.refresh(db_contact)
            return {"message": f"Tag '{tag}' removed from contact", "tags": db_contact.tags}
        else:
            return {"message": f"Tag '{tag}' not found on contact", "tags": db_contact.tags or []}
    finally:
        db.close()


# ============ CONTACT CRUD (parameterized routes) ============

@router.get("/{contact_id:int}", response_model=ContactOut)
def get_contact(contact_id: int, tenant_id: int = Depends(current_tenant_id)):
    db = SessionLocal()
    try:
        return _get_tenant_contact(db, contact_id, tenant_id)
    finally:
        db.close()


@router.patch("/{contact_id:int}", response_model=ContactOut)
def update_contact(
    contact_id: int,
    contact: ContactUpdate,
    tenant_id: int = Depends(current_tenant_id),
):
    db = SessionLocal()
    try:
        db_contact = _get_tenant_contact(db, contact_id, tenant_id)
        
        for field, value in contact.model_dump(exclude_unset=True).items():
            setattr(db_contact, field, value)
        
        db.commit()
        db.refresh(db_contact)
        return db_contact
    finally:
        db.close()


def _purge_contact_rows(db, contact_ids: List[int], tenant_id: int) -> dict:
    """Remove the rows that hang off the contacts being deleted.

    Drafts and events are deleted outright; verifications keep their history and
    only lose the contact link. List membership is removed explicitly so the
    cleanup also works where the FK cascade is not enforced (SQLite).
    """
    if not contact_ids:
        return {"drafts_removed": 0, "events_removed": 0}

    drafts_removed = (
        db.query(Draft)
        .filter(Draft.contact_id.in_(contact_ids), Draft.tenant_id == tenant_id)
        .delete(synchronize_session=False)
    )
    events_removed = (
        db.query(Event)
        .filter(Event.contact_id.in_(contact_ids), Event.tenant_id == tenant_id)
        .delete(synchronize_session=False)
    )
    db.query(ContactListMember).filter(
        ContactListMember.contact_id.in_(contact_ids),
        ContactListMember.tenant_id == tenant_id,
    ).delete(synchronize_session=False)
    db.query(EmailVerification).filter(
        EmailVerification.contact_id.in_(contact_ids),
        EmailVerification.tenant_id == tenant_id,
    ).update({EmailVerification.contact_id: None}, synchronize_session=False)

    return {"drafts_removed": drafts_removed, "events_removed": events_removed}


@router.delete("/bulk")
def delete_contacts_bulk(
    contact_ids: List[int] = Body(..., embed=True),
    tenant_id: int = Depends(current_tenant_id),
):
    """Delete multiple contacts by their IDs."""
    if not contact_ids:
        raise HTTPException(status_code=400, detail="contact_ids array is required")

    db = SessionLocal()
    try:
        contacts = (
            db.query(Contact)
            .filter(Contact.id.in_(contact_ids), Contact.tenant_id == tenant_id)
            .all()
        )
        if not contacts:
            raise HTTPException(status_code=404, detail="No contacts found")

        ids = [contact.id for contact in contacts]
        removed = _purge_contact_rows(db, ids, tenant_id)
        deleted_count = (
            db.query(Contact)
            .filter(Contact.id.in_(ids), Contact.tenant_id == tenant_id)
            .delete(synchronize_session=False)
        )

        db.add(
            Log(
                message=f"Deleted {deleted_count} contacts",
                level="warning",
                tenant_id=tenant_id,
            )
        )
        db.commit()
        return {
            "message": f"{deleted_count} contacts deleted",
            "total_deleted": deleted_count,
            **removed,
        }
    finally:
        db.close()


@router.delete("/all")
def delete_all_contacts(
    confirm: bool = Query(
        False,
        description=(
            "Must be true. Guards against an accidental or scripted call wiping "
            "every contact in the tenant."
        ),
    ),
    tenant_id: int = Depends(current_tenant_id),
):
    """Delete every contact in the caller's tenant.

    Destructive and irreversible, so it requires an explicit ``?confirm=true``.
    Operation ids are read first so the response can report real counts, and
    the same cleanup helper as the bulk route removes drafts, events, list
    memberships and verification links in one statement each.
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Refusing to delete every contact. Repeat with ?confirm=true.",
        )
    db = SessionLocal()
    try:
        ids = [
            row[0]
            for row in db.query(Contact.id)
            .filter(Contact.tenant_id == tenant_id)
            .all()
        ]
        if not ids:
            return {
                "message": "No contacts to delete",
                "total_deleted": 0,
                "drafts_removed": 0,
                "events_removed": 0,
            }

        removed = _purge_contact_rows(db, ids, tenant_id)
        deleted_count = (
            db.query(Contact)
            .filter(Contact.id.in_(ids), Contact.tenant_id == tenant_id)
            .delete(synchronize_session=False)
        )
        db.add(
            Log(
                message=(
                    f"Deleted all {deleted_count} contacts ({removed['drafts_removed']} "
                    f"draft(s), {removed['events_removed']} event(s))"
                ),
                level="warning",
                tenant_id=tenant_id,
            )
        )
        db.commit()
        return {
            "message": f"{deleted_count} contacts deleted",
            "total_deleted": deleted_count,
            **removed,
        }
    finally:
        db.close()


@router.delete("/{contact_id:int}")
def delete_contact(contact_id: int, tenant_id: int = Depends(current_tenant_id)):
    """Delete a contact together with the rows that reference it."""
    db = SessionLocal()
    try:
        db_contact = _get_tenant_contact(db, contact_id, tenant_id)

        removed = _purge_contact_rows(db, [contact_id], tenant_id)

        db.delete(db_contact)
        db.add(
            Log(
                message=(
                    f"Deleted contact {contact_id} with "
                    f"{removed['drafts_removed']} draft(s) "
                    f"and {removed['events_removed']} event(s)"
                ),
                level="warning",
                tenant_id=tenant_id,
            )
        )
        db.commit()
        return {
            "message": "Contact deleted",
            "drafts_removed": removed["drafts_removed"],
            "events_removed": removed["events_removed"],
        }
    finally:
        db.close()


@router.post("/{contact_id:int}/eligibility")
def update_eligibility(
    contact_id: int,
    payload: EligibilityUpdate = None,
    eligible: bool = Query(None),
    tenant_id: int = Depends(current_tenant_id),
):
    """Set email permission, accepting either a JSON body or a query parameter."""
    value = payload.eligible_to_email if payload is not None else eligible
    if value is None:
        raise HTTPException(status_code=422, detail="eligible_to_email is required")

    db = SessionLocal()
    try:
        db_contact = _get_tenant_contact(db, contact_id, tenant_id)

        db_contact.eligible_to_email = bool(value)
        db.commit()

        db.add(
            Log(
                message=f"Contact {contact_id} eligibility set to {bool(value)}",
                level="info",
                tenant_id=tenant_id,
            )
        )
        db.commit()

        return {"message": f"Eligibility updated to {bool(value)}", "eligible_to_email": bool(value)}
    finally:
        db.close()
