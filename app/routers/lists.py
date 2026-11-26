"""Contact lists API, modelled on Brevo's Lists product.

Brevo organises contacts into folders, and each folder holds lists. A list is a
static collection of contacts with its own campaign settings (from name, from
email, reply-to, header, footer, description). The endpoints here mirror the
Brevo actions one-for-one:

* folders: create, list, rename, move, delete (deleting a folder deletes its
  lists but never the contacts)
* lists: create, list/search/sort/paginate, rename, move, duplicate, delete,
  per-list settings
* membership: add existing contacts, remove contacts, import a CSV straight
  into a list, list-level subscribe/unsubscribe, and the "clean up duplicates
  across lists" actions from Brevo's list settings page

Every row is tenant-scoped and a foreign id is reported as 404 so another
tenant's list can never be read or mutated.
"""
import csv
import logging
from datetime import datetime, timezone
from io import StringIO
from typing import Any, Dict, List, Optional

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.db import (
    Contact,
    ContactList,
    ContactListFolder,
    ContactListMember,
    SessionLocal,
)
from app.deps import current_tenant_id
from app.models.schemas import ContactOut

logger = logging.getLogger(__name__)

router = APIRouter()

# Brevo caps an account at 300 folders and 300 lists.
MAX_FOLDERS = 300
MAX_LISTS = 300


class ContactListCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    folderId: Optional[int] = None
    folder_id: Optional[int] = None
    from_name: Optional[str] = None
    from_email: Optional[str] = None
    reply_to: Optional[str] = None
    header: Optional[str] = None
    footer: Optional[str] = None


class ContactListUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    folderId: Optional[int] = None
    folder_id: Optional[int] = None
    from_name: Optional[str] = None
    from_email: Optional[str] = None
    reply_to: Optional[str] = None
    header: Optional[str] = None
    footer: Optional[str] = None


class ContactListSettings(BaseModel):
    description: Optional[str] = None
    from_name: Optional[str] = None
    from_email: Optional[str] = None
    reply_to: Optional[str] = None
    header: Optional[str] = None
    footer: Optional[str] = None


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class FolderUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class MembershipUpdate(BaseModel):
    contact_ids: List[int] = Field(default_factory=list)


class AddContactsRequest(BaseModel):
    """Brevo accepts any one of these three selectors."""

    ids: Optional[List[int]] = None
    emails: Optional[List[str]] = None
    extIds: Optional[List[str]] = None
    contact_ids: Optional[List[int]] = None


class RemoveContactsRequest(AddContactsRequest):
    pass


class DuplicateRequest(BaseModel):
    new_name: Optional[str] = Field(default=None, max_length=255)
    name: Optional[str] = Field(default=None, max_length=255)


class ListImportRequest(BaseModel):
    csv: str
    # Contacts arriving in a list you created are people you intend to mail.
    # Without this an import leaves every row ineligible, so the campaign built
    # from the list reports 0 recipients and sends nothing.
    mark_eligible: bool = True


class ContactListOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    folder_id: Optional[int] = None
    folderId: Optional[int] = None
    folder_name: Optional[str] = None
    member_count: int = 0
    total_subscribers: int = 0
    totalSubscribers: int = 0
    total_blacklisted: int = 0
    totalBlacklisted: int = 0
    unique_subscribers: int = 0
    uniqueSubscribers: int = 0
    unsubscribed_count: int = 0
    from_name: Optional[str] = None
    from_email: Optional[str] = None
    reply_to: Optional[str] = None
    header: Optional[str] = None
    footer: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------- helpers


def _get_list(db, list_id: int, tenant_id: int) -> ContactList:
    contact_list = (
        db.query(ContactList)
        .filter(ContactList.id == list_id, ContactList.tenant_id == tenant_id)
        .first()
    )
    if contact_list is None:
        raise HTTPException(status_code=404, detail="List not found")
    return contact_list


def _get_folder(db, folder_id: int, tenant_id: int) -> ContactListFolder:
    folder = (
        db.query(ContactListFolder)
        .filter(
            ContactListFolder.id == folder_id,
            ContactListFolder.tenant_id == tenant_id,
        )
        .first()
    )
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


def _folder_name(db, folder_id: Optional[int], tenant_id: int) -> Optional[str]:
    if folder_id is None:
        return None
    return (
        db.query(ContactListFolder.name)
        .filter(
            ContactListFolder.id == folder_id,
            ContactListFolder.tenant_id == tenant_id,
        )
        .scalar()
    )


def _resolve_folder_id(payload) -> Optional[int]:
    """Accept both Brevo's ``folderId`` and snake_case ``folder_id``."""
    if payload.folderId is not None:
        return payload.folderId
    return payload.folder_id


def _members_query(db, list_id: int, tenant_id: int):
    return db.query(ContactListMember).filter(
        ContactListMember.list_id == list_id,
        ContactListMember.tenant_id == tenant_id,
    )


def _counts(db, list_id: int, tenant_id: int) -> Dict[str, int]:
    """Subscriber, unique-subscriber and blacklist counts for one list.

    ``total_subscribers`` counts subscribed membership rows, matching the
    number Brevo shows in the list row. ``unique_subscribers`` counts distinct
    contact ids, and ``total_blacklisted`` counts members whose contact is
    blacklisted account-wide.
    """
    rows = (
        db.query(ContactListMember.contact_id, ContactListMember.unsubscribed)
        .filter(
            ContactListMember.list_id == list_id,
            ContactListMember.tenant_id == tenant_id,
        )
        .all()
    )
    subscribed = [contact_id for contact_id, unsub in rows if not unsub]
    unsubscribed = len(rows) - len(subscribed)
    blacklisted = 0
    if subscribed:
        blacklisted = (
            db.query(func.count(func.distinct(Contact.id)))
            .filter(
                Contact.tenant_id == tenant_id,
                Contact.id.in_(subscribed),
                Contact.email_blacklisted.is_(True),
            )
            .scalar()
            or 0
        )
    return {
        "member_count": len(subscribed),
        "total_subscribers": len(subscribed),
        "unique_subscribers": len(set(subscribed)),
        "total_blacklisted": blacklisted,
        "unsubscribed_count": unsubscribed,
    }


def _to_out(db, contact_list: ContactList, tenant_id: int) -> ContactListOut:
    counts = _counts(db, contact_list.id, tenant_id)
    folder_name = _folder_name(db, contact_list.folder_id, tenant_id)
    return ContactListOut(
        id=contact_list.id,
        name=contact_list.name,
        description=contact_list.description,
        folder_id=contact_list.folder_id,
        folderId=contact_list.folder_id,
        folder_name=folder_name,
        member_count=counts["member_count"],
        total_subscribers=counts["total_subscribers"],
        totalSubscribers=counts["total_subscribers"],
        total_blacklisted=counts["total_blacklisted"],
        totalBlacklisted=counts["total_blacklisted"],
        unique_subscribers=counts["unique_subscribers"],
        uniqueSubscribers=counts["unique_subscribers"],
        unsubscribed_count=counts["unsubscribed_count"],
        from_name=contact_list.from_name,
        from_email=contact_list.from_email,
        reply_to=contact_list.reply_to,
        header=contact_list.header,
        footer=contact_list.footer,
        created_at=contact_list.created_at,
        updated_at=contact_list.updated_at,
    )


def _resolve_contacts(db, tenant_id: int, payload: AddContactsRequest):
    """Turn a Brevo selector (ids/emails/extIds) into owned contact rows.

    Returns ``(found, failed)`` where ``found`` is a list of Contact objects
    and ``failed`` holds the original selectors that matched nothing.
    """
    selectors = payload.ids or payload.contact_ids or []
    emails = [email.strip().lower() for email in (payload.emails or []) if email]
    failed: List[Any] = list(payload.extIds or [])

    found: List[Contact] = []
    if selectors:
        found.extend(
            db.query(Contact)
            .filter(
                Contact.tenant_id == tenant_id,
                Contact.id.in_(selectors),
            )
            .all()
        )
        owned = {contact.id for contact in found}
        failed.extend([cid for cid in selectors if cid not in owned])

    if emails:
        matched = (
            db.query(Contact)
            .filter(
                Contact.tenant_id == tenant_id,
                func.lower(Contact.email).in_(emails),
            )
            .all()
        )
        found.extend(matched)
        seen = {contact.email.lower() for contact in matched}
        failed.extend([email for email in emails if email not in seen])

    # De-duplicate while preserving order so success counts are exact.
    deduped: List[Contact] = []
    seen_ids = set()
    for contact in found:
        if contact.id in seen_ids:
            continue
        seen_ids.add(contact.id)
        deduped.append(contact)
    return deduped, failed


def _unique_list_name(db, tenant_id: int, base: str) -> str:
    """Return a name that does not clash with an existing list in the tenant."""
    candidate = base
    suffix = 2
    while (
        db.query(ContactList.id)
        .filter(
            ContactList.tenant_id == tenant_id,
            ContactList.name == candidate,
        )
        .first()
    ):
        candidate = f"{base} ({suffix})"
        suffix += 1
    return candidate


def _merge_tags(existing, incoming) -> List[str]:
    """Union two tag lists, keeping the original order and case of each tag."""
    merged: List[str] = []
    seen = set()
    for tag in list(existing or []) + list(incoming or []):
        text = str(tag).strip()
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        merged.append(text)
    return merged


def _insert_members(db, tenant_id: int, list_id: int, contact_ids) -> int:
    """Insert missing membership rows; idempotent, returns the new count."""
    existing = {
        row[0]
        for row in _members_query(db, list_id, tenant_id).with_entities(
            ContactListMember.contact_id
        )
    }
    now = datetime.now(timezone.utc)
    added = 0
    for contact_id in contact_ids:
        if contact_id in existing:
            continue
        db.add(
            ContactListMember(
                tenant_id=tenant_id,
                list_id=list_id,
                contact_id=contact_id,
                added_at=now,
            )
        )
        existing.add(contact_id)
        added += 1
    return added


# ------------------------------------------------------------- folders


@router.get("/folders")
def list_folders(tenant_id: int = Depends(current_tenant_id)):
    """List the tenant's folders with Brevo's subscriber totals."""
    db = SessionLocal()
    try:
        folders = (
            db.query(ContactListFolder)
            .filter(ContactListFolder.tenant_id == tenant_id)
            .order_by(ContactListFolder.name.asc())
            .all()
        )
        out = []
        for folder in folders:
            list_ids = [
                row[0]
                for row in db.query(ContactList.id).filter(
                    ContactList.tenant_id == tenant_id,
                    ContactList.folder_id == folder.id,
                )
            ]
            subscribers = 0
            blacklisted = 0
            for list_id in list_ids:
                counts = _counts(db, list_id, tenant_id)
                subscribers += counts["total_subscribers"]
                blacklisted += counts["total_blacklisted"]
            out.append(
                {
                    "id": folder.id,
                    "name": folder.name,
                    "listCount": len(list_ids),
                    "totalSubscribers": subscribers,
                    "totalBlacklisted": blacklisted,
                    "uniqueSubscribers": subscribers,
                    "created_at": folder.created_at,
                }
            )
        return {"count": len(out), "folders": out}
    finally:
        db.close()


@router.post("/folders", status_code=201)
def create_folder(
    payload: FolderCreate, tenant_id: int = Depends(current_tenant_id)
):
    db = SessionLocal()
    try:
        existing_count = (
            db.query(ContactListFolder)
            .filter(ContactListFolder.tenant_id == tenant_id)
            .count()
        )
        if existing_count >= MAX_FOLDERS:
            raise HTTPException(
                status_code=422,
                detail=f"Folder limit reached ({MAX_FOLDERS} per account).",
            )

        folder = ContactListFolder(
            tenant_id=tenant_id, name=payload.name.strip()
        )
        db.add(folder)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409, detail="A folder with that name already exists."
            )
        db.refresh(folder)
        return {"id": folder.id, "name": folder.name}
    finally:
        db.close()


@router.put("/folders/{folder_id}")
@router.patch("/folders/{folder_id}")
def update_folder(
    folder_id: int,
    payload: FolderUpdate,
    tenant_id: int = Depends(current_tenant_id),
):
    db = SessionLocal()
    try:
        folder = _get_folder(db, folder_id, tenant_id)
        folder.name = payload.name.strip()
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409, detail="A folder with that name already exists."
            )
        db.refresh(folder)
        return {"id": folder.id, "name": folder.name}
    finally:
        db.close()


@router.delete("/folders/{folder_id}")
def delete_folder(folder_id: int, tenant_id: int = Depends(current_tenant_id)):
    """Delete a folder and its lists; contacts stay in the account."""
    db = SessionLocal()
    try:
        _get_folder(db, folder_id, tenant_id)
        list_ids = [
            row[0]
            for row in db.query(ContactList.id).filter(
                ContactList.tenant_id == tenant_id,
                ContactList.folder_id == folder_id,
            )
        ]
        if list_ids:
            _members_query_ids = db.query(ContactListMember).filter(
                ContactListMember.tenant_id == tenant_id,
                ContactListMember.list_id.in_(list_ids),
            )
            _members_query_ids.delete(synchronize_session=False)
            db.query(ContactList).filter(
                ContactList.tenant_id == tenant_id,
                ContactList.id.in_(list_ids),
            ).delete(synchronize_session=False)
        db.query(ContactListFolder).filter(
            ContactListFolder.id == folder_id,
            ContactListFolder.tenant_id == tenant_id,
        ).delete(synchronize_session=False)
        db.commit()
        return {
            "message": "Folder deleted",
            "deleted_lists": len(list_ids),
        }
    finally:
        db.close()


# --------------------------------------------------------------- lists


@router.get("", response_model=List[ContactListOut])
def list_contact_lists(
    search: Optional[str] = Query(None),
    folder_id: Optional[int] = Query(None),
    folderId: Optional[int] = Query(None),
    limit: int = Query(300, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: str = Query("desc", pattern="^(asc|desc)$"),
    tenant_id: int = Depends(current_tenant_id),
):
    """List the tenant's lists with Brevo's counts, search, sort and paging.

    Brevo orders by record creation, newest first, so a list you just created
    sits at the top of the page. ``sort=asc`` flips that to oldest first.
    """
    db = SessionLocal()
    try:
        query = db.query(ContactList).filter(ContactList.tenant_id == tenant_id)

        resolved_folder = folder_id if folder_id is not None else folderId
        if resolved_folder is not None:
            query = query.filter(ContactList.folder_id == resolved_folder)
        if search:
            query = query.filter(ContactList.name.ilike(f"%{search.strip()}%"))

        if sort == "desc":
            query = query.order_by(ContactList.created_at.desc(), ContactList.id.desc())
        else:
            query = query.order_by(ContactList.created_at.asc(), ContactList.id.asc())

        rows = query.offset(offset).limit(limit).all()
        return [_to_out(db, row, tenant_id) for row in rows]
    finally:
        db.close()


@router.post("", response_model=ContactListOut, status_code=201)
def create_contact_list(
    payload: ContactListCreate, tenant_id: int = Depends(current_tenant_id)
):
    """Create a list, optionally inside a folder, as Brevo requires."""
    db = SessionLocal()
    try:
        existing_count = (
            db.query(ContactList)
            .filter(ContactList.tenant_id == tenant_id)
            .count()
        )
        if existing_count >= MAX_LISTS:
            raise HTTPException(
                status_code=422,
                detail=f"List limit reached ({MAX_LISTS} per account).",
            )

        folder_id = _resolve_folder_id(payload)
        if folder_id is not None:
            _get_folder(db, folder_id, tenant_id)

        contact_list = ContactList(
            tenant_id=tenant_id,
            folder_id=folder_id,
            name=payload.name.strip(),
            description=payload.description,
            from_name=payload.from_name,
            from_email=payload.from_email,
            reply_to=payload.reply_to,
            header=payload.header,
            footer=payload.footer,
        )
        db.add(contact_list)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409, detail="A list with that name already exists."
            )
        db.refresh(contact_list)
        return _to_out(db, contact_list, tenant_id)
    finally:
        db.close()


@router.get("/{list_id}", response_model=ContactListOut)
def get_contact_list(list_id: int, tenant_id: int = Depends(current_tenant_id)):
    db = SessionLocal()
    try:
        return _to_out(db, _get_list(db, list_id, tenant_id), tenant_id)
    finally:
        db.close()


@router.put("/{list_id}", response_model=ContactListOut)
@router.patch("/{list_id}", response_model=ContactListOut)
def update_contact_list(
    list_id: int,
    payload: ContactListUpdate,
    tenant_id: int = Depends(current_tenant_id),
):
    """Rename a list, move it to another folder, or change its settings."""
    db = SessionLocal()
    try:
        contact_list = _get_list(db, list_id, tenant_id)
        data = payload.model_dump(exclude_unset=True)

        folder_id = _resolve_folder_id(payload)
        if folder_id is not None:
            _get_folder(db, folder_id, tenant_id)
            contact_list.folder_id = folder_id
        elif "folderId" in data or "folder_id" in data:
            # An explicit null moves the list out of its folder.
            contact_list.folder_id = None

        for field in ("name", "description", "from_name", "from_email", "reply_to", "header", "footer"):
            if field in data and data[field] is not None:
                setattr(contact_list, field, data[field])

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409, detail="A list with that name already exists."
            )
        db.refresh(contact_list)
        return _to_out(db, contact_list, tenant_id)
    finally:
        db.close()


@router.delete("/{list_id}")
def delete_contact_list(list_id: int, tenant_id: int = Depends(current_tenant_id)):
    """Delete a list. Contacts themselves are untouched, as in Brevo."""
    db = SessionLocal()
    try:
        contact_list = _get_list(db, list_id, tenant_id)
        _members_query(db, list_id, tenant_id).delete(synchronize_session=False)
        db.delete(contact_list)
        db.commit()
        return {"message": "List deleted"}
    finally:
        db.close()


@router.post("/{list_id}/duplicate", response_model=ContactListOut, status_code=201)
def duplicate_contact_list(
    list_id: int,
    payload: Optional[DuplicateRequest] = None,
    tenant_id: int = Depends(current_tenant_id),
):
    """Brevo's "Duplicate" action: copy settings and membership."""
    db = SessionLocal()
    try:
        source = _get_list(db, list_id, tenant_id)
        requested = (payload.new_name or payload.name) if payload else None
        name = _unique_list_name(
            db,
            tenant_id,
            (requested or f"{source.name} (copy)").strip()[:255],
        )
        copy = ContactList(
            tenant_id=tenant_id,
            folder_id=source.folder_id,
            name=name,
            description=source.description,
            from_name=source.from_name,
            from_email=source.from_email,
            reply_to=source.reply_to,
            header=source.header,
            footer=source.footer,
        )
        db.add(copy)
        db.flush()

        member_rows = _members_query(db, source.id, tenant_id).all()
        now = datetime.now(timezone.utc)
        for member in member_rows:
            db.add(
                ContactListMember(
                    tenant_id=tenant_id,
                    list_id=copy.id,
                    contact_id=member.contact_id,
                    unsubscribed=member.unsubscribed,
                    added_at=now,
                )
            )
        db.commit()
        db.refresh(copy)
        return _to_out(db, copy, tenant_id)
    finally:
        db.close()


# ---------------------------------------------------- list campaign settings


@router.get("/{list_id}/settings", response_model=ContactListOut)
def get_list_settings(list_id: int, tenant_id: int = Depends(current_tenant_id)):
    db = SessionLocal()
    try:
        return _to_out(db, _get_list(db, list_id, tenant_id), tenant_id)
    finally:
        db.close()


@router.put("/{list_id}/settings", response_model=ContactListOut)
def update_list_settings(
    list_id: int,
    payload: ContactListSettings,
    tenant_id: int = Depends(current_tenant_id),
):
    """Set the list's From name/email, Reply-To, header, footer and description."""
    db = SessionLocal()
    try:
        contact_list = _get_list(db, list_id, tenant_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(contact_list, field, value)
        db.commit()
        db.refresh(contact_list)
        return _to_out(db, contact_list, tenant_id)
    finally:
        db.close()


# ----------------------------------------------------------- membership


@router.get("/{list_id}/contacts", response_model=List[ContactOut])
def list_contacts_in_list(
    list_id: int,
    limit: int = Query(500, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: str = Query("asc", pattern="^(asc|desc)$"),
    modifiedSince: Optional[str] = Query(None),
    tenant_id: int = Depends(current_tenant_id),
):
    """Return subscribed contacts in a list, paginated and sortable."""
    db = SessionLocal()
    try:
        _get_list(db, list_id, tenant_id)
        query = (
            db.query(Contact)
            .join(ContactListMember, ContactListMember.contact_id == Contact.id)
            .filter(
                ContactListMember.list_id == list_id,
                ContactListMember.tenant_id == tenant_id,
                ContactListMember.unsubscribed.isnot(True),
                Contact.tenant_id == tenant_id,
            )
        )
        if modifiedSince:
            try:
                since = datetime.fromisoformat(modifiedSince.replace("Z", "+00:00"))
                query = query.filter(Contact.updated_at >= since)
            except ValueError:
                raise HTTPException(
                    status_code=400, detail="modifiedSince must be an ISO date-time"
                )

        order = Contact.id.desc() if sort == "desc" else Contact.id.asc()
        return query.order_by(order).offset(offset).limit(limit).all()
    finally:
        db.close()


@router.post("/{list_id}/contacts", response_model=ContactListOut)
def add_contacts_to_list(
    list_id: int,
    payload: MembershipUpdate,
    tenant_id: int = Depends(current_tenant_id),
):
    """Add contacts by id to a list. Unknown or foreign ids are rejected whole."""
    db = SessionLocal()
    try:
        contact_list = _get_list(db, list_id, tenant_id)

        if payload.contact_ids:
            owned = {
                row[0]
                for row in db.query(Contact.id)
                .filter(
                    Contact.tenant_id == tenant_id,
                    Contact.id.in_(payload.contact_ids),
                )
                .all()
            }
            unknown = [cid for cid in payload.contact_ids if cid not in owned]
            if unknown:
                raise HTTPException(
                    status_code=404, detail=f"Contacts not found: {unknown}"
                )

            _insert_members(db, tenant_id, list_id, payload.contact_ids)
            db.commit()
            db.refresh(contact_list)

        return _to_out(db, contact_list, tenant_id)
    finally:
        db.close()


@router.post("/{list_id}/contacts/add", status_code=201)
def add_contacts_brevo(
    list_id: int,
    payload: AddContactsRequest,
    tenant_id: int = Depends(current_tenant_id),
):
    """Brevo's add-contacts endpoint: accepts ids, emails or extIds.

    Unknown selectors are reported per-item in ``failure`` rather than failing
    the whole request, which is what Brevo's UI shows after an import.
    """
    db = SessionLocal()
    try:
        _get_list(db, list_id, tenant_id)
        found, failed = _resolve_contacts(db, tenant_id, payload)
        _insert_members(db, tenant_id, list_id, [contact.id for contact in found])
        db.commit()
        success = [
            contact.id
            if (payload.ids or payload.contact_ids)
            else contact.email
            for contact in found
        ]
        return {
            "contacts": {},
            "success": success,
            "failure": failed,
            "total": len(success),
        }
    finally:
        db.close()


@router.post("/{list_id}/contacts/remove")
def remove_contacts_brevo(
    list_id: int,
    payload: RemoveContactsRequest,
    tenant_id: int = Depends(current_tenant_id),
):
    """Remove several contacts from a list in one call."""
    db = SessionLocal()
    try:
        _get_list(db, list_id, tenant_id)
        found, failed = _resolve_contacts(db, tenant_id, payload)
        removed_ids = [contact.id for contact in found]
        removed = 0
        if removed_ids:
            removed = (
                _members_query(db, list_id, tenant_id)
                .filter(ContactListMember.contact_id.in_(removed_ids))
                .delete(synchronize_session=False)
            )
        db.commit()
        return {
            "success": [contact.id for contact in found],
            "failure": failed,
            "removed": removed,
        }
    finally:
        db.close()


@router.delete("/{list_id}/contacts/{contact_id}", response_model=ContactListOut)
def remove_contact_from_list(
    list_id: int,
    contact_id: int,
    tenant_id: int = Depends(current_tenant_id),
):
    """Remove one contact from a list, leaving the contact intact."""
    db = SessionLocal()
    try:
        contact_list = _get_list(db, list_id, tenant_id)
        removed = (
            _members_query(db, list_id, tenant_id)
            .filter(ContactListMember.contact_id == contact_id)
            .delete(synchronize_session=False)
        )
        if not removed:
            raise HTTPException(status_code=404, detail="Contact is not in this list")
        db.commit()
        db.refresh(contact_list)
        return _to_out(db, contact_list, tenant_id)
    finally:
        db.close()


@router.post("/{list_id}/contacts/{contact_id}/unsubscribe", response_model=ContactListOut)
def unsubscribe_contact_from_list(
    list_id: int,
    contact_id: int,
    tenant_id: int = Depends(current_tenant_id),
):
    """Mark a contact unsubscribed from this list only, keeping the row."""
    db = SessionLocal()
    try:
        contact_list = _get_list(db, list_id, tenant_id)
        member = (
            _members_query(db, list_id, tenant_id)
            .filter(ContactListMember.contact_id == contact_id)
            .first()
        )
        if member is None:
            raise HTTPException(status_code=404, detail="Contact is not in this list")
        member.unsubscribed = True
        db.commit()
        db.refresh(contact_list)
        return _to_out(db, contact_list, tenant_id)
    finally:
        db.close()


@router.post("/{list_id}/contacts/{contact_id}/subscribe", response_model=ContactListOut)
def resubscribe_contact_to_list(
    list_id: int,
    contact_id: int,
    tenant_id: int = Depends(current_tenant_id),
):
    """Reverse a list-level unsubscribe."""
    db = SessionLocal()
    try:
        contact_list = _get_list(db, list_id, tenant_id)
        member = (
            _members_query(db, list_id, tenant_id)
            .filter(ContactListMember.contact_id == contact_id)
            .first()
        )
        if member is None:
            raise HTTPException(status_code=404, detail="Contact is not in this list")
        member.unsubscribed = False
        db.commit()
        db.refresh(contact_list)
        return _to_out(db, contact_list, tenant_id)
    finally:
        db.close()


# --------------------------------------------------------------- import


@router.post("/{list_id}/import")
def import_contacts_to_list(
    list_id: int,
    payload: ListImportRequest,
    tenant_id: int = Depends(current_tenant_id),
):
    """Brevo's "Import contacts to the list": create/update then add.

    Headers are normalised first (BOM, ``Email``/``EMAIL``, ``First Name``) so an
    export taken straight from Brevo, Mailchimp or Excel imports instead of
    silently reporting zero rows.
    """
    from app.services.csv_import import CsvImportError, parse_contacts_csv

    rows, errors = ([], [])
    try:
        rows, errors = parse_contacts_csv(payload.csv)
    except CsvImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    db = SessionLocal()
    try:
        contact_list = _get_list(db, list_id, tenant_id)

        created = 0
        updated = 0
        member_ids: List[int] = []
        errors = list(errors)

        for row in rows:
            raw_email = str(row.get("email") or "").strip()
            try:
                email = validate_email(
                    raw_email, check_deliverability=False
                ).normalized
            except EmailNotValidError as exc:
                errors.append(f"{raw_email}: {exc}")
                continue

            row_tags = [str(tag) for tag in (row.get("tags") or [])]
            existing = (
                db.query(Contact)
                .filter(
                    Contact.tenant_id == tenant_id,
                    func.lower(Contact.email) == email.lower(),
                )
                .first()
            )
            if existing:
                for attr in (
                    "name",
                    "company",
                    "role",
                    "phone",
                    "linkedin",
                    "notes",
                ):
                    if row.get(attr):
                        setattr(existing, attr, row[attr])
                if row_tags:
                    existing.tags = _merge_tags(existing.tags, row_tags)
                # An imported contact is someone the operator chose to mail, so
                # the list's audience must not read back as zero recipients.
                if payload.mark_eligible:
                    existing.eligible_to_email = True
                updated += 1
                member_ids.append(existing.id)
            else:
                contact = Contact(
                    tenant_id=tenant_id,
                    email=email,
                    name=row.get("name") or None,
                    company=row.get("company") or None,
                    role=row.get("role") or None,
                    phone=row.get("phone") or None,
                    linkedin=row.get("linkedin") or None,
                    notes=row.get("notes") or None,
                    tags=row_tags,
                    eligible_to_email=payload.mark_eligible,
                )
                db.add(contact)
                db.flush()
                created += 1
                member_ids.append(contact.id)

        added = _insert_members(db, tenant_id, list_id, member_ids)
        db.commit()
        db.refresh(contact_list)
        return {
            "imported": created + updated,
            "created": created,
            "updated": updated,
            "added_to_list": added,
            "errors": errors[:10],
            "list": _to_out(db, contact_list, tenant_id),
        }
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="One or more contacts already exist for another tenant.",
        )
    finally:
        db.close()


# --------------------------------------------- cross-list cleanup actions


@router.post("/{list_id}/contacts/remove-from-other-lists")
def remove_members_from_other_lists(
    list_id: int, tenant_id: int = Depends(current_tenant_id)
):
    """Brevo list settings: remove this list's contacts from every other list."""
    db = SessionLocal()
    try:
        _get_list(db, list_id, tenant_id)
        member_ids = [
            row[0]
            for row in _members_query(db, list_id, tenant_id).with_entities(
                ContactListMember.contact_id
            )
        ]
        if not member_ids:
            return {"removed": 0}
        removed = (
            db.query(ContactListMember)
            .filter(
                ContactListMember.tenant_id == tenant_id,
                ContactListMember.contact_id.in_(member_ids),
                ContactListMember.list_id != list_id,
            )
            .delete(synchronize_session=False)
        )
        db.commit()
        return {"removed": removed}
    finally:
        db.close()


@router.post("/{list_id}/contacts/remove-duplicates")
def remove_duplicates_from_list(
    list_id: int, tenant_id: int = Depends(current_tenant_id)
):
    """Brevo list settings: remove contacts from this list if they are in others."""
    db = SessionLocal()
    try:
        _get_list(db, list_id, tenant_id)
        elsewhere = (
            db.query(ContactListMember.contact_id)
            .filter(
                ContactListMember.tenant_id == tenant_id,
                ContactListMember.list_id != list_id,
            )
        )
        removed = (
            _members_query(db, list_id, tenant_id)
            .filter(
                ContactListMember.contact_id.in_(
                    elsewhere.with_entities(ContactListMember.contact_id)
                )
            )
            .delete(synchronize_session=False)
        )
        db.commit()
        return {"removed": removed}
    finally:
        db.close()


@router.get("/{list_id}/stats")
def get_list_stats(list_id: int, tenant_id: int = Depends(current_tenant_id)):
    """Brevo-style counters for one list, used by the list header."""
    db = SessionLocal()
    try:
        _get_list(db, list_id, tenant_id)
        return _counts(db, list_id, tenant_id)
    finally:
        db.close()
