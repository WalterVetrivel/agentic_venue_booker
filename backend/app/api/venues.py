from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_optional_user, require
from app.db import get_db
from app.models import Equipment, SeasonalRule, User, Venue, VenueAlias, VenueStatusPeriod
from app.schemas import (
    RESTRICTED_VENUE_FIELDS,
    EquipmentIn,
    EquipmentOut,
    EquipmentUpdate,
    SeasonalRuleIn,
    SeasonalRuleOut,
    StatusPeriodIn,
    StatusPeriodOut,
    VenueCreate,
    VenueFullOut,
    VenueOut,
    VenueUpdate,
)
from app.services import audit
from app.services.access import can, can_edit_venue, can_update_equipment, forbid
from app.services.venues import find_venues, get_venue

router = APIRouter(prefix="/api", tags=["venues"])


def split_csv(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def venue_or_404(db: Session, code: str) -> Venue:
    venue = get_venue(db, code)
    if venue is None:
        raise HTTPException(404, "Venue not found")
    return venue


def full_out(venue: Venue, user: User | None) -> VenueFullOut:
    return VenueFullOut(
        **VenueOut.model_validate(venue).model_dump(),
        equipment=[EquipmentOut.model_validate(e) for e in venue.equipment],
        aliases=[a.alias for a in venue.aliases],
        technician=venue.technician,
        notes=venue.notes,
        status_periods=sorted(venue.status_periods, key=lambda p: p.from_date),
        seasonal_rules=venue.seasonal_rules,
        can_edit=can_edit_venue(user, venue),
        can_update_equipment=can_update_equipment(user, venue),
        can_edit_restricted=can(user, "edit_venue_all"),
    )


def user_by_email(db: Session, email: str | None) -> User | None:
    if not email:
        return None
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        raise HTTPException(422, f"No user with email {email}")
    return user


@router.get("/venues", response_model=list[VenueOut])
def list_venues(
    type: str | None = None,
    min_capacity: int | None = Query(default=None, ge=1),
    needs: str | None = Query(default=None, description="Comma-separated equipment or software"),
    db: Session = Depends(get_db),
) -> list[Venue]:
    return find_venues(db, type=type, min_capacity=min_capacity, needs=split_csv(needs))


@router.get("/venues/{code}", response_model=VenueFullOut)
def venue_detail(
    code: str, db: Session = Depends(get_db), user: User | None = Depends(get_optional_user)
) -> VenueFullOut:
    return full_out(venue_or_404(db, code), user)


@router.post("/venues", response_model=VenueFullOut, status_code=status.HTTP_201_CREATED)
def create_venue(
    body: VenueCreate, db: Session = Depends(get_db), user: User = Depends(require("create_venue"))
) -> VenueFullOut:
    code = body.code.upper()
    if get_venue(db, code):
        raise HTTPException(409, f"Venue {code} already exists")
    data = body.model_dump(exclude={"in_charge_email", "technician_email", "code"})
    venue = Venue(
        code=code,
        in_charge=user_by_email(db, body.in_charge_email),
        technician=user_by_email(db, body.technician_email),
        **data,
    )
    venue.aliases = [VenueAlias(alias=a) for a in {code, body.name}]
    db.add(venue)
    db.flush()
    audit.record(db, user, "create", "venue", venue.id, after=body.model_dump())
    db.commit()
    return full_out(venue, user)


@router.patch("/venues/{code}", response_model=VenueFullOut)
def update_venue(
    code: str,
    body: VenueUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VenueFullOut:
    venue = venue_or_404(db, code)
    if not can_edit_venue(user, venue):
        raise forbid()
    changes = body.model_dump(exclude_unset=True)
    if RESTRICTED_VENUE_FIELDS & changes.keys() and not can(user, "edit_venue_all"):
        raise HTTPException(403, "Only the Director can change capacity, type or in-charges")
    before = {k: getattr(venue, k, None) for k in changes if not k.endswith("_email")}
    for key in ("in_charge_email", "technician_email"):
        if key in changes:
            setattr(venue, key.removesuffix("_email"), user_by_email(db, changes.pop(key)))
    for key, value in changes.items():
        setattr(venue, key, value)
    audit.record(db, user, "update", "venue", venue.id, before=before, after=body.model_dump())
    db.commit()
    return full_out(venue, user)


# Equipment ---------------------------------------------------------------------------------


@router.post("/venues/{code}/equipment", response_model=EquipmentOut, status_code=201)
def add_equipment(
    code: str,
    body: EquipmentIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Equipment:
    venue = venue_or_404(db, code)
    if not can_edit_venue(user, venue):
        raise forbid()
    item = Equipment(venue=venue, updated_by_id=user.id, **body.model_dump())
    db.add(item)
    db.flush()
    audit.record(db, user, "create", "equipment", item.id, after=body.model_dump())
    db.commit()
    return item


def equipment_or_404(db: Session, item_id: int) -> Equipment:
    item = db.get(Equipment, item_id)
    if item is None:
        raise HTTPException(404, "Equipment not found")
    return item


@router.patch("/equipment/{item_id}", response_model=EquipmentOut)
def update_equipment(
    item_id: int,
    body: EquipmentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Equipment:
    item = equipment_or_404(db, item_id)
    changes = body.model_dump(exclude_unset=True)
    status_only = changes.keys() <= {"status"}
    allowed = (
        can_update_equipment(user, item.venue) if status_only else can_edit_venue(user, item.venue)
    )
    if not allowed:
        raise forbid()
    before = {k: getattr(item, k) for k in changes}
    for key, value in changes.items():
        setattr(item, key, value)
    item.updated_by_id = user.id
    audit.record(db, user, "update", "equipment", item.id, before=before, after=changes)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/equipment/{item_id}", status_code=204)
def delete_equipment(
    item_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Response:
    item = equipment_or_404(db, item_id)
    if not can_edit_venue(user, item.venue):
        raise forbid()
    audit.record(db, user, "delete", "equipment", item.id, before={"name": item.name})
    db.delete(item)
    db.commit()
    return Response(status_code=204)


# Status periods and seasonal rules ---------------------------------------------------------


@router.post("/venues/{code}/status-periods", response_model=StatusPeriodOut, status_code=201)
def add_status_period(
    code: str,
    body: StatusPeriodIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VenueStatusPeriod:
    venue = venue_or_404(db, code)
    if not can_edit_venue(user, venue):
        raise forbid()
    period = VenueStatusPeriod(venue=venue, set_by_id=user.id, **body.model_dump())
    db.add(period)
    db.flush()
    audit.record(db, user, "create", "status_period", period.id, after=body.model_dump())
    db.commit()
    return period


@router.delete("/status-periods/{period_id}", status_code=204)
def delete_status_period(
    period_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Response:
    period = db.get(VenueStatusPeriod, period_id)
    if period is None:
        raise HTTPException(404, "Not found")
    if not can_edit_venue(user, period.venue):
        raise forbid()
    audit.record(db, user, "delete", "status_period", period.id, before={"status": period.status})
    db.delete(period)
    db.commit()
    return Response(status_code=204)


@router.post("/venues/{code}/seasonal-rules", response_model=SeasonalRuleOut, status_code=201)
def add_seasonal_rule(
    code: str,
    body: SeasonalRuleIn,
    db: Session = Depends(get_db),
    user: User = Depends(require("edit_venue_all")),
) -> SeasonalRule:
    venue = venue_or_404(db, code)
    rule = SeasonalRule(venue=venue, **body.model_dump())
    db.add(rule)
    db.flush()
    audit.record(db, user, "create", "seasonal_rule", rule.id, after=body.model_dump())
    db.commit()
    return rule


@router.delete("/seasonal-rules/{rule_id}", status_code=204)
def delete_seasonal_rule(
    rule_id: int, db: Session = Depends(get_db), user: User = Depends(require("edit_venue_all"))
) -> Response:
    rule = db.get(SeasonalRule, rule_id)
    if rule is None:
        raise HTTPException(404, "Not found")
    audit.record(db, user, "delete", "seasonal_rule", rule.id, before={"reason": rule.reason})
    db.delete(rule)
    db.commit()
    return Response(status_code=204)
