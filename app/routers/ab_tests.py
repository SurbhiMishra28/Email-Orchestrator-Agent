"""Tenant-scoped A/B test CRUD plus per-variant results."""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db import ABTest, ABVariant, SessionLocal, Template
from app.deps import current_tenant_id
from app.services.abtesting import results_for_tenant, test_results

logger = logging.getLogger(__name__)

router = APIRouter()

VALID_STATUSES = {"active", "paused", "completed"}


class VariantIn(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=50000)
    weight: int = Field(default=1, ge=0, le=1000)


class VariantUpdate(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=100)
    subject: Optional[str] = Field(default=None, min_length=1, max_length=500)
    body: Optional[str] = Field(default=None, min_length=1, max_length=50000)
    weight: Optional[int] = Field(default=None, ge=0, le=1000)


class ABTestCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    template_id: Optional[int] = None
    status: str = "active"
    variants: List[VariantIn] = Field(min_length=1)


class ABTestUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    template_id: Optional[int] = None
    status: Optional[str] = None


def _get_test(db, test_id: int, tenant_id: int) -> ABTest:
    test = (
        db.query(ABTest)
        .filter(ABTest.id == test_id, ABTest.tenant_id == tenant_id)
        .first()
    )
    if not test:
        raise HTTPException(status_code=404, detail=f"A/B test {test_id} not found")
    return test


def _validate_status(status: str) -> str:
    if status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of {sorted(VALID_STATUSES)}",
        )
    return status


def _validate_template(db, template_id: Optional[int], tenant_id: int) -> None:
    if template_id is None:
        return
    exists = (
        db.query(Template.id)
        .filter(Template.id == template_id, Template.tenant_id == tenant_id)
        .first()
    )
    if not exists:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")


def _test_summary(db, test: ABTest) -> dict:
    variants = (
        db.query(ABVariant)
        .filter(
            ABVariant.ab_test_id == test.id,
            ABVariant.tenant_id == test.tenant_id,
        )
        .order_by(ABVariant.id.asc())
        .all()
    )
    return {
        "id": test.id,
        "name": test.name,
        "status": test.status,
        "template_id": test.template_id,
        "created_at": test.created_at.isoformat() if test.created_at else None,
        "updated_at": test.updated_at.isoformat() if test.updated_at else None,
        "variants": [
            {
                "id": variant.id,
                "label": variant.label,
                "subject": variant.subject,
                "body": variant.body,
                "weight": variant.weight,
            }
            for variant in variants
        ],
    }


@router.get("")
def list_ab_tests(tenant_id: int = Depends(current_tenant_id)):
    """List the tenant's experiments with their variants."""
    db = SessionLocal()
    try:
        tests = (
            db.query(ABTest)
            .filter(ABTest.tenant_id == tenant_id)
            .order_by(ABTest.id.desc())
            .all()
        )
        return [_test_summary(db, test) for test in tests]
    finally:
        db.close()


@router.get("/results")
def all_results(tenant_id: int = Depends(current_tenant_id)):
    """Per-variant performance for every experiment in the tenant."""
    db = SessionLocal()
    try:
        return results_for_tenant(db, tenant_id)
    finally:
        db.close()


@router.post("", status_code=201)
def create_ab_test(payload: ABTestCreate, tenant_id: int = Depends(current_tenant_id)):
    """Create an experiment and its variants."""
    _validate_status(payload.status)
    labels = [variant.label for variant in payload.variants]
    if len(set(labels)) != len(labels):
        raise HTTPException(status_code=409, detail="Variant labels must be unique")
    if not any(variant.weight > 0 for variant in payload.variants):
        raise HTTPException(
            status_code=422, detail="At least one variant needs a positive weight"
        )

    db = SessionLocal()
    try:
        _validate_template(db, payload.template_id, tenant_id)
        test = ABTest(
            tenant_id=tenant_id,
            name=payload.name,
            status=payload.status,
            template_id=payload.template_id,
        )
        db.add(test)
        db.flush()
        for variant in payload.variants:
            db.add(
                ABVariant(
                    tenant_id=tenant_id,
                    ab_test_id=test.id,
                    label=variant.label,
                    subject=variant.subject,
                    body=variant.body,
                    weight=variant.weight,
                )
            )
        db.commit()
        db.refresh(test)
        return _test_summary(db, test)
    finally:
        db.close()


@router.get("/{test_id}")
def get_ab_test(test_id: int, tenant_id: int = Depends(current_tenant_id)):
    db = SessionLocal()
    try:
        return _test_summary(db, _get_test(db, test_id, tenant_id))
    finally:
        db.close()


@router.patch("/{test_id}")
def update_ab_test(
    test_id: int, payload: ABTestUpdate, tenant_id: int = Depends(current_tenant_id)
):
    db = SessionLocal()
    try:
        test = _get_test(db, test_id, tenant_id)
        if payload.name is not None:
            test.name = payload.name
        if payload.status is not None:
            test.status = _validate_status(payload.status)
        if payload.template_id is not None:
            _validate_template(db, payload.template_id, tenant_id)
            test.template_id = payload.template_id
        db.commit()
        db.refresh(test)
        return _test_summary(db, test)
    finally:
        db.close()


@router.delete("/{test_id}", status_code=204)
def delete_ab_test(test_id: int, tenant_id: int = Depends(current_tenant_id)):
    """Delete an experiment and its variants. Drafts keep their recorded ids."""
    db = SessionLocal()
    try:
        test = _get_test(db, test_id, tenant_id)
        db.query(ABVariant).filter(
            ABVariant.ab_test_id == test.id,
            ABVariant.tenant_id == tenant_id,
        ).delete(synchronize_session=False)
        db.delete(test)
        db.commit()
        return None
    finally:
        db.close()


@router.get("/{test_id}/results")
def ab_test_results(test_id: int, tenant_id: int = Depends(current_tenant_id)):
    """Per-variant sent/opened/clicked/replied counts for one experiment."""
    db = SessionLocal()
    try:
        return test_results(db, _get_test(db, test_id, tenant_id))
    finally:
        db.close()


@router.post("/{test_id}/variants", status_code=201)
def add_variant(
    test_id: int, payload: VariantIn, tenant_id: int = Depends(current_tenant_id)
):
    db = SessionLocal()
    try:
        test = _get_test(db, test_id, tenant_id)
        duplicate = (
            db.query(ABVariant.id)
            .filter(
                ABVariant.ab_test_id == test.id,
                ABVariant.tenant_id == tenant_id,
                ABVariant.label == payload.label,
            )
            .first()
        )
        if duplicate:
            raise HTTPException(
                status_code=409, detail=f"Variant '{payload.label}' already exists"
            )
        variant = ABVariant(
            tenant_id=tenant_id,
            ab_test_id=test.id,
            label=payload.label,
            subject=payload.subject,
            body=payload.body,
            weight=payload.weight,
        )
        db.add(variant)
        db.commit()
        db.refresh(variant)
        return {
            "id": variant.id,
            "label": variant.label,
            "subject": variant.subject,
            "body": variant.body,
            "weight": variant.weight,
        }
    finally:
        db.close()


@router.patch("/{test_id}/variants/{variant_id}")
def update_variant(
    test_id: int,
    variant_id: int,
    payload: VariantUpdate,
    tenant_id: int = Depends(current_tenant_id),
):
    db = SessionLocal()
    try:
        test = _get_test(db, test_id, tenant_id)
        variant = (
            db.query(ABVariant)
            .filter(
                ABVariant.id == variant_id,
                ABVariant.ab_test_id == test.id,
                ABVariant.tenant_id == tenant_id,
            )
            .first()
        )
        if not variant:
            raise HTTPException(status_code=404, detail="Variant not found")
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(variant, field, value)
        db.commit()
        db.refresh(variant)
        return {
            "id": variant.id,
            "label": variant.label,
            "subject": variant.subject,
            "body": variant.body,
            "weight": variant.weight,
        }
    finally:
        db.close()


@router.delete("/{test_id}/variants/{variant_id}", status_code=204)
def delete_variant(
    test_id: int, variant_id: int, tenant_id: int = Depends(current_tenant_id)
):
    """Delete one variant; the last remaining variant cannot be removed."""
    db = SessionLocal()
    try:
        test = _get_test(db, test_id, tenant_id)
        remaining = (
            db.query(ABVariant)
            .filter(
                ABVariant.ab_test_id == test.id,
                ABVariant.tenant_id == tenant_id,
            )
            .count()
        )
        variant = (
            db.query(ABVariant)
            .filter(
                ABVariant.id == variant_id,
                ABVariant.ab_test_id == test.id,
                ABVariant.tenant_id == tenant_id,
            )
            .first()
        )
        if not variant:
            raise HTTPException(status_code=404, detail="Variant not found")
        if remaining <= 1:
            raise HTTPException(
                status_code=409,
                detail="An experiment needs at least one variant.",
            )
        db.delete(variant)
        db.commit()
        return None
    finally:
        db.close()
