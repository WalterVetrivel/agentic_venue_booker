from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    initials: Mapped[str | None] = mapped_column(String(10))
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    designation: Mapped[str | None] = mapped_column(String(60))
    password_hash: Mapped[str] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def role_keys(self) -> list[str]:
        return sorted(r.role_key for r in self.roles)


class Role(Base):
    __tablename__ = "roles"

    key: Mapped[str] = mapped_column(String(20), primary_key=True)
    label: Mapped[str] = mapped_column(String(60))


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_key: Mapped[str] = mapped_column(ForeignKey("roles.key"), primary_key=True)

    user: Mapped[User] = relationship(back_populates="roles")


class Venue(Base):
    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(20))  # lab | seminar_hall | coe
    block: Mapped[str | None] = mapped_column(String(30))
    department: Mapped[str | None] = mapped_column(String(30))
    capacity: Mapped[int] = mapped_column(Integer)
    byod: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_hod_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    in_charge_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)

    in_charge: Mapped[User | None] = relationship(lazy="joined")
    aliases: Mapped[list["VenueAlias"]] = relationship(
        back_populates="venue", cascade="all, delete-orphan", lazy="selectin"
    )
    equipment: Mapped[list["Equipment"]] = relationship(
        back_populates="venue", cascade="all, delete-orphan", lazy="selectin"
    )
    status_periods: Mapped[list["VenueStatusPeriod"]] = relationship(
        back_populates="venue", cascade="all, delete-orphan", lazy="selectin"
    )
    seasonal_rules: Mapped[list["SeasonalRule"]] = relationship(
        back_populates="venue", cascade="all, delete-orphan", lazy="selectin"
    )


class VenueAlias(Base):
    __tablename__ = "venue_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(String(120), unique=True)

    venue: Mapped[Venue] = relationship(back_populates="aliases")


class Equipment(Base):
    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(20))  # hardware | software | av | facility
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    # working | faulty | under_repair
    status: Mapped[str] = mapped_column(String(20), default="working")
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    venue: Mapped[Venue] = relationship(back_populates="equipment")


class VenueStatusPeriod(Base):
    __tablename__ = "venue_status_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20))  # maintenance | renovation | closed
    from_date: Mapped[date] = mapped_column(Date)
    to_date: Mapped[date | None] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(Text)
    set_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    venue: Mapped[Venue] = relationship(back_populates="status_periods")


class SeasonalRule(Base):
    __tablename__ = "seasonal_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"))
    start_month: Mapped[int] = mapped_column(Integer)
    end_month: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))  # blocked | soft_warning
    reason: Mapped[str] = mapped_column(Text)

    venue: Mapped[Venue] = relationship(back_populates="seasonal_rules")
