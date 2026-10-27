"""Ownership-aware permission checks shared by the REST API and (later) MCP tools."""

from fastapi import HTTPException, status

from app.models import User, Venue
from app.permissions import has_capability


def can(user: User | None, capability: str) -> bool:
    return has_capability(user.role_keys if user else None, capability)


def can_edit_venue(user: User | None, venue: Venue) -> bool:
    if user is None:
        return False
    return can(user, "edit_venue_all") or (
        can(user, "edit_venue_own") and venue.in_charge_id == user.id
    )


def can_update_equipment(user: User | None, venue: Venue) -> bool:
    if user is None:
        return False
    if can(user, "update_equipment_all"):
        return True
    owns = user.id in (venue.in_charge_id, venue.technician_id)
    return can(user, "update_equipment_own") and owns


def forbid() -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to this venue")
