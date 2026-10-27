from pydantic import BaseModel, ConfigDict


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    initials: str | None
    designation: str | None
    roles: list[str]
    capabilities: list[str]


class MeOut(BaseModel):
    user: UserOut | None
    capabilities: list[str]


class EquipmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str
    quantity: int
    status: str


class InChargeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str


class VenueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    type: str
    block: str | None
    department: str | None
    capacity: int
    byod: bool
    needs_hod_approval: bool
    in_charge: InChargeOut | None


class VenueDetailOut(VenueOut):
    equipment: list[EquipmentOut]
    aliases: list[str]
