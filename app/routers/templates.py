"""Templates API router (tenant-scoped)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from typing import List

from app.db import SessionLocal, Template, Log, Contact, Draft, Campaign, ABTest
from app.deps import current_tenant_id
from app.models.schemas import TemplateCreate, TemplateUpdate, TemplateOut, TemplateUseRequest, TemplateExpandRequest

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_tenant_template(db, template_id: int, tenant_id: int) -> Template:
    template = (
        db.query(Template)
        .filter(Template.id == template_id, Template.tenant_id == tenant_id)
        .first()
    )
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.get("")
def list_templates(active_only: bool = True, tenant_id: int = Depends(current_tenant_id)):
    db = SessionLocal()
    try:
        query = db.query(Template).filter(Template.tenant_id == tenant_id)
        if active_only:
            query = query.filter(Template.is_active == True)
        templates = query.order_by(Template.id.asc()).all()
        return {"templates": [TemplateOut.model_validate(t) for t in templates]}
    finally:
        db.close()


@router.post("", response_model=TemplateOut)
def create_template(
    template: TemplateCreate,
    tenant_id: int = Depends(current_tenant_id),
):
    db = SessionLocal()
    try:
        db_template = Template(**template.model_dump(), tenant_id=tenant_id)
        db.add(db_template)
        db.commit()
        db.refresh(db_template)
        
        log = Log(
            message=f"Created template: {template.name}",
            level="info",
            tenant_id=tenant_id,
        )
        db.add(log)
        db.commit()
        
        return TemplateOut.model_validate(db_template)
    finally:
        db.close()


@router.get("/categories")
def get_template_categories(tenant_id: int = Depends(current_tenant_id)):
    db = SessionLocal()
    try:
        categories = (
            db.query(Template.category)
            .filter(Template.tenant_id == tenant_id)
            .distinct()
            .all()
        )
        category_list = [c[0] for c in categories]
        return {"categories": category_list if category_list else ["intro", "followup", "outreach", "nurture"]}
    finally:
        db.close()


@router.post("/use")
async def use_template(
    request: TemplateUseRequest,
    tenant_id: int = Depends(current_tenant_id),
):
    """Create a draft from a template with personalization.

    Sending is always a separate, explicit step, so the result is a draft.
    """
    db = SessionLocal()
    try:
        template = (
            db.query(Template)
            .filter(
                Template.id == request.template_id,
                Template.tenant_id == tenant_id,
                Template.is_active == True,
            )
            .first()
        )
        if not template:
            raise HTTPException(status_code=404, detail="Template not found or inactive")

        contact = (
            db.query(Contact)
            .filter(Contact.id == request.contact_id, Contact.tenant_id == tenant_id)
            .first()
        )
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")

        from app.agents import expand_template_with_ai

        result = await expand_template_with_ai(template, contact, request.custom_values)

        draft = Draft(
            contact_id=contact.id,
            subject=result["subject"],
            body=result["body"],
            status="draft",
            tenant_id=tenant_id,
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)

        return {
            "draft_id": draft.id,
            "subject": draft.subject,
            "body": draft.body,
            "status": draft.status,
        }
    finally:
        db.close()


@router.post("/expand")
async def expand_template_endpoint(
    request: TemplateExpandRequest,
    tenant_id: int = Depends(current_tenant_id),
):
    """Expand a template with contact variables."""
    db = SessionLocal()
    try:
        template = _get_tenant_template(db, request.template_id, tenant_id)

        contact = (
            db.query(Contact)
            .filter(Contact.id == request.contact_id, Contact.tenant_id == tenant_id)
            .first()
        )
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")

        from app.agents import expand_template_with_ai

        result = await expand_template_with_ai(template, contact, request.custom_values)
        return {"subject": result["subject"], "body": result["body"]}
    finally:
        db.close()


@router.post("/{template_id}", response_model=TemplateOut)
def update_template(
    template_id: int,
    template: TemplateUpdate,
    tenant_id: int = Depends(current_tenant_id),
):
    """Update a template by ID."""
    db = SessionLocal()
    try:
        db_template = _get_tenant_template(db, template_id, tenant_id)
        
        for field, value in template.model_dump(exclude_unset=True).items():
            setattr(db_template, field, value)
        
        db.commit()
        db.refresh(db_template)
        return TemplateOut.model_validate(db_template)
    finally:
        db.close()


@router.delete("/{template_id}")
def delete_template(template_id: int, tenant_id: int = Depends(current_tenant_id)):
    db = SessionLocal()
    try:
        db_template = _get_tenant_template(db, template_id, tenant_id)

        references = []
        campaign_count = (
            db.query(Campaign)
            .filter(Campaign.template_id == template_id)
            .count()
        )
        if campaign_count:
            references.append(f"{campaign_count} campaign(s)")
        ab_test_count = (
            db.query(ABTest)
            .filter(ABTest.template_id == template_id)
            .count()
        )
        if ab_test_count:
            references.append(f"{ab_test_count} A/B test(s)")
        if references:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Template is still used by {' and '.join(references)}. "
                    "Remove or repoint those first."
                ),
            )

        db.delete(db_template)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="Template is still referenced by other records.",
            )
        return {"message": "Template deleted"}
    finally:
        db.close()


@router.post("/{template_id}/duplicate")
def duplicate_template(template_id: int, tenant_id: int = Depends(current_tenant_id)):
    db = SessionLocal()
    try:
        original = _get_tenant_template(db, template_id, tenant_id)
        
        new_template = Template(
            name=f"{original.name} (Copy)",
            category=original.category,
            subject_template=original.subject_template,
            body_template=original.body_template,
            footer_template=original.footer_template,
            variables=original.variables,
            tags=original.tags,
            is_active=original.is_active,
            tenant_id=tenant_id,
        )
        db.add(new_template)
        db.commit()
        db.refresh(new_template)
        
        return {"id": new_template.id, "name": new_template.name}
    finally:
        db.close()
