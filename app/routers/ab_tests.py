"""Tenant-scoped A/B test CRUD plus per-variant results."""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db import ABTest, ABVariant, Campaign, SessionLocal, Template
from app.deps import current_tenant_id
from app.services.abtesting import results_for_tenant, test_results

logger = logging.getLogger(__name__)

router = APIRouter()

VALID_STATUSES = {"active", "paused", "completed"}

# Brevo offers exactly these three things to test.
VALID_TEST_TYPES = {"subject", "sender", "content"}
# The metric that decides the winner.
VALID_WINNING_METRICS = {"open_rate", "click_rate", "reply_rate"}


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
    # Brevo's A/B configuration.
    test_type: str = "subject"
    winning_metric: str = "open_rate"
    split_a: int = Field(default=50, ge=0, le=100)
    split_b: int = Field(default=50, ge=0, le=100)
    evaluation_hours: int = Field(default=4, ge=1, le=720)
    campaign_id: Optional[int] = None


class ABTestUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    template_id: Optional[int] = None
    status: Optional[str] = None
    test_type: Optional[str] = None
    winning_metric: Optional[str] = None
    split_a: Optional[int] = Field(default=None, ge=0, le=100)
    split_b: Optional[int] = Field(default=None, ge=0, le=100)
    evaluation_hours: Optional[int] = Field(default=None, ge=1, le=720)


class WinnerRequest(BaseModel):
    """Force a winner (Brevo's "select winner manually") or ask for the leader."""
    variant_label: Optional[str] = None


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


def _validate_test_type(test_type: str) -> str:
    if test_type not in VALID_TEST_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"test_type must be one of {sorted(VALID_TEST_TYPES)}",
        )
    return test_type


def _validate_winning_metric(metric: str) -> str:
    if metric not in VALID_WINNING_METRICS:
        raise HTTPException(
            status_code=422,
            detail=f"winning_metric must be one of {sorted(VALID_WINNING_METRICS)}",
        )
    return metric


def _validate_split(split_a: int, split_b: int) -> None:
    """The two shares are a proportion; they have to add up to a whole."""
    if split_a + split_b != 100:
        raise HTTPException(
            status_code=422,
            detail="split_a + split_b must equal 100 (e.g. 50/50, 20/80).",
        )


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
        "test_type": test.test_type or "subject",
        "winning_metric": test.winning_metric or "open_rate",
        "split_a": test.split_a if test.split_a is not None else 50,
        "split_b": test.split_b if test.split_b is not None else 50,
        "evaluation_hours": (
            test.evaluation_hours if test.evaluation_hours is not None else 4
        ),
        "winner_label": test.winner_label,
        "decided_at": test.decided_at.isoformat() if test.decided_at else None,
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
    test_type = _validate_test_type(payload.test_type or "subject")
    winning_metric = _validate_winning_metric(payload.winning_metric or "open_rate")
    _validate_split(payload.split_a, payload.split_b)
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
            test_type=test_type,
            winning_metric=winning_metric,
            split_a=payload.split_a,
            split_b=payload.split_b,
            evaluation_hours=payload.evaluation_hours,
        )
        db.add(test)
        db.flush()
        # Brevo's default is a 50/50 traffic split even when variant weights are
        # left at 1, so the split drives the weights unless they were set.
        weights = [variant.weight for variant in payload.variants]
        use_split = len(weights) == 2 and all(weight == 1 for weight in weights)
        for index, variant in enumerate(payload.variants):
            if use_split:
                weight = payload.split_a if index == 0 else payload.split_b
            else:
                weight = variant.weight
            db.add(
                ABVariant(
                    tenant_id=tenant_id,
                    ab_test_id=test.id,
                    label=variant.label,
                    subject=variant.subject,
                    body=variant.body,
                    weight=max(int(weight), 0),
                )
            )
        if payload.campaign_id is not None:
            campaign = (
                db.query(Campaign)
                .filter(
                    Campaign.id == payload.campaign_id,
                    Campaign.tenant_id == tenant_id,
                )
                .first()
            )
            if campaign is not None:
                campaign.ab_test_id = test.id
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
        if payload.test_type is not None:
            test.test_type = _validate_test_type(payload.test_type)
        if payload.winning_metric is not None:
            test.winning_metric = _validate_winning_metric(payload.winning_metric)
        if payload.split_a is not None or payload.split_b is not None:
            split_a = payload.split_a if payload.split_a is not None else test.split_a
            split_b = payload.split_b if payload.split_b is not None else test.split_b
            _validate_split(split_a, split_b)
            test.split_a = split_a
            test.split_b = split_b
        if payload.evaluation_hours is not None:
            test.evaluation_hours = payload.evaluation_hours
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


def _leading_variant(results: dict, metric: str) -> Optional[dict]:
    """The variant with the best ``metric``, ignoring empty ones.

    A variant with no sends has a 0% rate by construction; letting it "win" would
    freeze an experiment that has not run yet.
    """
    key = metric if metric in {"open_rate", "click_rate", "reply_rate"} else "open_rate"
    contenders = [variant for variant in results.get("variants", []) if variant.get("sent")]
    if not contenders:
        return None
    contenders.sort(key=lambda variant: (variant.get(key) or 0, variant.get("sent") or 0), reverse=True)
    best = contenders[0]
    if len(contenders) > 1 and (contenders[1].get(key) or 0) == (best.get(key) or 0):
        return None  # a tie is not a winner
    return best


@router.get("/{test_id}/winner")
def ab_test_winner(test_id: int, tenant_id: int = Depends(current_tenant_id)):
    """Preview which variant is ahead, without freezing the experiment."""
    # A shared Pydantic instance as a default would be mutated across requests.
    payload = payload or WinnerRequest()

    db = SessionLocal()
    try:
        test = _get_test(db, test_id, tenant_id)
        results = test_results(db, test)
        leader = _leading_variant(results, test.winning_metric or "open_rate")
        return {
            "test_id": test.id,
            "winning_metric": test.winning_metric,
            "winner_label": test.winner_label,
            "decided_at": test.decided_at.isoformat() if test.decided_at else None,
            "leading": leader,
            "tie": leader is None and any(
                variant.get("sent") for variant in results.get("variants", [])
            ),
            "results": results,
        }
    finally:
        db.close()


@router.post("/{test_id}/winner")
def decide_ab_test_winner(
    test_id: int,
    payload: WinnerRequest | None = None,
    tenant_id: int = Depends(current_tenant_id),
):
    """Select the winner and close the experiment.

    With no ``variant_label`` the best-performing variant is picked using the
    configured metric, which is what Brevo's automatic winner selection does
    once the evaluation window has elapsed.
    """
    db = SessionLocal()
    try:
        test = _get_test(db, test_id, tenant_id)
        results = test_results(db, test)

        if payload.variant_label:
            label = payload.variant_label
            if not any(variant["label"] == label for variant in results["variants"]):
                raise HTTPException(
                    status_code=404, detail=f"Variant '{label}' not found"
                )
        else:
            leader = _leading_variant(results, test.winning_metric or "open_rate")
            if leader is None:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "No winner yet: variants are tied or have not been sent. "
                        "Pass variant_label to choose one manually."
                    ),
                )
            label = leader["label"]

        test.winner_label = label
        test.decided_at = datetime.now(timezone.utc)
        test.status = "completed"
        db.commit()
        db.refresh(test)

        from app.services.abtesting import freeze_winner_drafts, winner_for_campaign

        # Remaining recipients still get the winning message rather than a
        # variant that lost, which is the point of running the test.
        winner_for_campaign(db, test, label)
        freeze_winner_drafts(db, test, label)
        db.commit()

        return _test_summary(db, test)
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
