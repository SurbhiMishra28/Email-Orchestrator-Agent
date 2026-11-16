"""Contacts API router."""
import csv
from io import StringIO
from typing import List

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.db import Contact, Draft, EmailVerification, Event, Log, SessionLocal
from app.models.schemas import ContactCreate, ContactOut, ContactUpdate, CSVImport

router = APIRouter()


class EligibilityUpdate(BaseModel):
    eligible_to_email: bool


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("", response_model=List[ContactOut])
def list_contacts(skip: int = 0, limit: int = 100):
    db = SessionLocal()
    try:
        contacts = db.query(Contact).offset(skip).limit(limit).all()
        return contacts
    finally:
        db.close()


@router.post("", response_model=ContactOut)
def create_contact(contact: ContactCreate):
    db = SessionLocal()
    try:
        # Check if email already exists
        existing = db.query(Contact).filter(Contact.email == contact.email).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Contact with email {contact.email} already exists")
        
        db_contact = Contact(**contact.model_dump())
        db.add(db_contact)
        db.commit()
        db.refresh(db_contact)
        
        log = Log(message=f"Created contact: {contact.email}", level="info")
        db.add(log)
        db.commit()
        
        # Convert to dict to avoid detached instance issues
        return ContactOut.model_validate(db_contact)
    finally:
        db.close()


@router.get("/{contact_id}", response_model=ContactOut)
def get_contact(contact_id: int):
    db = SessionLocal()
    try:
        contact = db.query(Contact).filter(Contact.id == contact_id).first()
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")
        return contact
    finally:
        db.close()


@router.patch("/{contact_id}", response_model=ContactOut)
def update_contact(contact_id: int, contact: ContactUpdate):
    db = SessionLocal()
    try:
        db_contact = db.query(Contact).filter(Contact.id == contact_id).first()
        if not db_contact:
            raise HTTPException(status_code=404, detail="Contact not found")
        
        for field, value in contact.model_dump(exclude_unset=True).items():
            setattr(db_contact, field, value)
        
        db.commit()
        db.refresh(db_contact)
        return db_contact
    finally:
        db.close()


@router.delete("/{contact_id}")
def delete_contact(contact_id: int):
    """Delete a contact together with the rows that reference it."""
    db = SessionLocal()
    try:
        db_contact = db.query(Contact).filter(Contact.id == contact_id).first()
        if not db_contact:
            raise HTTPException(status_code=404, detail="Contact not found")

        drafts_removed = (
            db.query(Draft)
            .filter(Draft.contact_id == contact_id)
            .delete(synchronize_session=False)
        )
        events_removed = (
            db.query(Event)
            .filter(Event.contact_id == contact_id)
            .delete(synchronize_session=False)
        )
        db.query(EmailVerification).filter(
            EmailVerification.contact_id == contact_id
        ).update({EmailVerification.contact_id: None}, synchronize_session=False)

        db.delete(db_contact)
        db.add(
            Log(
                message=(
                    f"Deleted contact {contact_id} with {drafts_removed} draft(s) "
                    f"and {events_removed} event(s)"
                ),
                level="warning",
            )
        )
        db.commit()
        return {
            "message": "Contact deleted",
            "drafts_removed": drafts_removed,
            "events_removed": events_removed,
        }
    finally:
        db.close()


@router.post("/{contact_id}/eligibility")
def update_eligibility(
    contact_id: int,
    payload: EligibilityUpdate = None,
    eligible: bool = Query(None),
):
    """Set email permission, accepting either a JSON body or a query parameter."""
    value = payload.eligible_to_email if payload is not None else eligible
    if value is None:
        raise HTTPException(status_code=422, detail="eligible_to_email is required")

    db = SessionLocal()
    try:
        db_contact = db.query(Contact).filter(Contact.id == contact_id).first()
        if not db_contact:
            raise HTTPException(status_code=404, detail="Contact not found")

        db_contact.eligible_to_email = bool(value)
        db.commit()

        db.add(Log(message=f"Contact {contact_id} eligibility set to {bool(value)}", level="info"))
        db.commit()

        return {"message": f"Eligibility updated to {bool(value)}", "eligible_to_email": bool(value)}
    finally:
        db.close()


@router.post("/import")
def import_csv(csv_data: CSVImport):
    db = SessionLocal()
    try:
        file_obj = StringIO(csv_data.csv)
        reader = csv.DictReader(file_obj)
        
        imported = 0
        errors = []
        
        for row in reader:
            try:
                email = row.get("email", row.get("Email", "")).strip()
                if not email:
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

                existing = db.query(Contact).filter(Contact.email == email).first()
                if existing:
                    # Update existing
                    for field in ["name", "company", "role", "phone", "linkedin", "notes"]:
                        if field in row:
                            setattr(existing, field, row[field])
                    if permission_known:
                        existing.eligible_to_email = permission
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
                    db_contact = Contact(**{k: v for k, v in contact_data.items() if v})
                    db.add(db_contact)
                
                imported += 1
            except Exception as e:
                errors.append(str(e))
        
        db.commit()
        
        log = Log(message=f"Imported {imported} contacts from CSV", level="info")
        db.add(log)
        db.commit()
        
        return {
            "imported": imported,
            "errors": errors[:10] if errors else []
        }
    finally:
        db.close()