from datetime import date, datetime, time

from sqlalchemy import (
    DDL,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    Time,
    UniqueConstraint,
    event,
    func,
)
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
    department: Mapped[str | None] = mapped_column(String(30))
    capacity: Mapped[int] = mapped_column(Integer)
    byod: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_hod_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    in_charge_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    technician_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)

    in_charge: Mapped[User | None] = relationship(foreign_keys=[in_charge_id], lazy="joined")
    technician: Mapped[User | None] = relationship(foreign_keys=[technician_id], lazy="joined")
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


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(40))
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    before: Mapped[str | None] = mapped_column(Text)  # JSON
    after: Mapped[str | None] = mapped_column(Text)  # JSON
    via: Mapped[str] = mapped_column(String(10), default="ui")  # ui | agent
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AcademicTerm(Base):
    __tablename__ = "academic_terms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)  # e.g. "2026-27 ODD"
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date] = mapped_column(Date)


class ClassSection(Base):
    __tablename__ = "class_sections"
    __table_args__ = (UniqueConstraint("dept", "year", "section"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    dept: Mapped[str] = mapped_column(String(20))
    year: Mapped[str] = mapped_column(String(5))
    section: Mapped[str] = mapped_column(String(5))
    advisor: Mapped[str | None] = mapped_column(String(120))
    strength: Mapped[int] = mapped_column(Integer, default=60)

    @property
    def label(self) -> str:
        return f"{self.dept} {self.year}-{self.section}"


class TimetableUpload(Base):
    __tablename__ = "timetable_uploads"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(200))
    stored_path: Mapped[str] = mapped_column(String(400))
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    status: Mapped[str] = mapped_column(String(20), default="parsed")  # parsed | committed
    parsed: Mapped[str] = mapped_column(Text)  # JSON: header, grid, slots as reviewed
    section_id: Mapped[int | None] = mapped_column(
        ForeignKey("class_sections.id", ondelete="SET NULL")
    )
    term_id: Mapped[int | None] = mapped_column(
        ForeignKey("academic_terms.id", ondelete="SET NULL")
    )


class TimetableSlot(Base):
    __tablename__ = "timetable_slots"

    id: Mapped[int] = mapped_column(primary_key=True)
    term_id: Mapped[int] = mapped_column(ForeignKey("academic_terms.id", ondelete="CASCADE"))
    section_id: Mapped[int] = mapped_column(ForeignKey("class_sections.id", ondelete="CASCADE"))
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), index=True)
    upload_id: Mapped[int | None] = mapped_column(
        ForeignKey("timetable_uploads.id", ondelete="SET NULL")
    )
    weekday: Mapped[int] = mapped_column(Integer)  # Mon=0
    start: Mapped[time] = mapped_column(Time)
    end: Mapped[time] = mapped_column(Time)
    subject_code: Mapped[str] = mapped_column(String(30))
    subject_name: Mapped[str] = mapped_column(String(160))
    faculty_name: Mapped[str | None] = mapped_column(String(160))
    batch: Mapped[str] = mapped_column(String(10), default="all")

    term: Mapped[AcademicTerm] = relationship(lazy="joined")
    section: Mapped[ClassSection] = relationship(lazy="joined")
    venue: Mapped[Venue] = relationship(lazy="joined")


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(String(20), unique=True)  # e.g. BK-2026-0007
    # Empty for a student request (students have no login).
    requester_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(10), default="staff")  # staff | student
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    event_type: Mapped[str] = mapped_column(String(40))
    description: Mapped[str | None] = mapped_column(Text)
    expected_count: Mapped[int] = mapped_column(Integer)
    requirements: Mapped[str | None] = mapped_column(Text)
    # Overall span; the bookable time on each day is in `occurrences`.
    start_dt: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_dt: Mapped[datetime] = mapped_column(DateTime, index=True)
    # pending_guide | pending_incharge | pending_hod | confirmed | rejected | cancelled
    # | waitlisted | offered | expired
    status: Mapped[str] = mapped_column(String(20), index=True)
    created_via: Mapped[str] = mapped_column(String(10), default="form")  # form | assistant
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id", ondelete="SET NULL"))
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    offer_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Student requests: the faculty guide who approves first, the number the group tracks the
    # request by, and the one address that gets email updates.
    guide_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    tracking_code: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    contact_email: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    requester: Mapped[User | None] = relationship(foreign_keys=[requester_id], lazy="joined")
    guide: Mapped[User | None] = relationship(foreign_keys=[guide_id], lazy="joined")
    venue: Mapped[Venue] = relationship(lazy="joined")
    students: Mapped[list["BookingStudent"]] = relationship(
        back_populates="booking",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="BookingStudent.id",
    )
    occurrences: Mapped[list["BookingOccurrence"]] = relationship(
        back_populates="booking",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="BookingOccurrence.start_dt",
    )
    approvals: Mapped[list["Approval"]] = relationship(
        back_populates="booking",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Approval.id",
    )
    displacements: Mapped[list["SlotOverride"]] = relationship(
        back_populates="booking", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def needs_displacement(self) -> bool:
        return bool(self.displacements)

    @property
    def is_student(self) -> bool:
        return self.kind == "student"

    @property
    def requester_name(self) -> str:
        if self.requester is not None:
            return self.requester.name
        names = [s.name for s in self.students if s.decision != "rejected"] or [
            s.name for s in self.students
        ]
        shown = ", ".join(names[:2]) + (f" +{len(names) - 2}" if len(names) > 2 else "")
        return f"Student group ({shown})" if shown else "Student group"


class BookingStudent(Base):
    """One student in a student request; the faculty guide approves or rejects each one."""

    __tablename__ = "booking_students"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    register_no: Mapped[str | None] = mapped_column(String(30))
    section_id: Mapped[int | None] = mapped_column(
        ForeignKey("class_sections.id", ondelete="SET NULL")
    )
    # e.g. "CSE III-B"; kept if the section is removed later
    class_label: Mapped[str] = mapped_column(String(40))
    # pending | approved | rejected
    decision: Mapped[str] = mapped_column(String(10), default="pending")
    comment: Mapped[str | None] = mapped_column(Text)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    # The class advisor has been told this student's final outcome (approved or rejected).
    advisor_told: Mapped[str | None] = mapped_column(String(10))

    booking: Mapped[Booking] = relationship(back_populates="students")
    section: Mapped[ClassSection | None] = relationship(lazy="joined")
    decided_by: Mapped[User | None] = relationship(lazy="joined")


class BookingOccurrence(Base):
    __tablename__ = "booking_occurrences"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"))
    start_dt: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_dt: Mapped[datetime] = mapped_column(DateTime, index=True)

    booking: Mapped[Booking] = relationship(back_populates="occurrences")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"))
    step: Mapped[str] = mapped_column(String(20))  # guide | incharge | hod
    approver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decision: Mapped[str] = mapped_column(String(10))  # approved | rejected
    comment: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    booking: Mapped[Booking] = relationship(back_populates="approvals")
    approver: Mapped[User | None] = relationship(lazy="joined")


class SlotOverride(Base):
    """A timetabled class moved out of the way of a booking on one date."""

    __tablename__ = "slot_overrides"

    id: Mapped[int] = mapped_column(primary_key=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("timetable_slots.id", ondelete="CASCADE"))
    on_date: Mapped[date] = mapped_column(Date, index=True)
    action: Mapped[str] = mapped_column(String(20))  # relocated | byod_classroom
    new_venue_id: Mapped[int | None] = mapped_column(
        ForeignKey("venues.id", ondelete="SET NULL"), index=True
    )
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"))
    # Takes effect only once the booking is confirmed.
    active: Mapped[bool] = mapped_column(Boolean, default=False)

    slot: Mapped[TimetableSlot] = relationship(lazy="joined")
    new_venue: Mapped[Venue | None] = relationship(lazy="joined")
    booking: Mapped[Booking] = relationship(back_populates="displacements")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(DateTime)


class OutboxEmail(Base):
    """An email to send (students have no login, so their updates go by email)."""

    __tablename__ = "outbox_emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    to: Mapped[str] = mapped_column(String(120), index=True)
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id", ondelete="SET NULL"))
    # queued | sent | failed | saved (no mail server set up: written to storage/outbox instead)
    status: Mapped[str] = mapped_column(String(10), default="queued", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)


# Circulars, reports and past events (RAG) -------------------------------------------------------


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))  # circular | report
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(400))
    ref_no: Mapped[str | None] = mapped_column(String(60), index=True)
    department: Mapped[str | None] = mapped_column(String(80))
    academic_year: Mapped[str | None] = mapped_column(String(10))
    issued_on: Mapped[date | None] = mapped_column(Date)
    text: Mapped[str] = mapped_column(Text)
    fields: Mapped[str] = mapped_column(Text, default="{}")  # JSON: what was extracted
    problems: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PastEvent(Base):
    """One event, described by its circular, its report, or both."""

    __tablename__ = "past_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    circular_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    report_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    series_key: Mapped[str] = mapped_column(String(200), index=True)
    event_type: Mapped[str] = mapped_column(String(40))
    department: Mapped[str | None] = mapped_column(String(80))
    venue_text: Mapped[str | None] = mapped_column(String(300))
    start_date: Mapped[date | None] = mapped_column(Date, index=True)
    end_date: Mapped[date | None] = mapped_column(Date)
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    audience: Mapped[str | None] = mapped_column(Text)
    expected_count: Mapped[int | None] = mapped_column(Integer)
    participants: Mapped[int | None] = mapped_column(Integer)
    registered: Mapped[int | None] = mapped_column(Integer)
    resource_persons: Mapped[str | None] = mapped_column(Text)
    topics: Mapped[str | None] = mapped_column(Text)  # comma-separated
    rating: Mapped[float | None] = mapped_column()
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    problems: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    edited: Mapped[bool] = mapped_column(Boolean, default=False)  # a person corrected it

    circular: Mapped[Document | None] = relationship(foreign_keys=[circular_id], lazy="joined")
    report: Mapped[Document | None] = relationship(foreign_keys=[report_id], lazy="joined")
    venues: Mapped[list[Venue]] = relationship(secondary="past_event_venues", lazy="selectin")


class PastEventVenue(Base):
    __tablename__ = "past_event_venues"

    event_id: Mapped[int] = mapped_column(
        ForeignKey("past_events.id", ondelete="CASCADE"), primary_key=True
    )
    venue_id: Mapped[int] = mapped_column(
        ForeignKey("venues.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class DocChunk(Base):
    """Searchable text of a document (one chunk each: the documents are a page long)."""

    __tablename__ = "doc_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)  # float32 vector
    embed_model: Mapped[str | None] = mapped_column(String(60))


# Full-text index over doc_chunks.text (BM25). Kept in sync by the search service.
FTS_DDL = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS doc_chunks_fts USING fts5("
    "text, content='doc_chunks', content_rowid='id', tokenize='porter unicode61')"
)
event.listen(DocChunk.__table__, "after_create", DDL(FTS_DDL))
event.listen(DocChunk.__table__, "before_drop", DDL("DROP TABLE IF EXISTS doc_chunks_fts"))


# Assistant ----------------------------------------------------------------------------------------


class AppSetting(Base):
    """Settings the Director changes in the app (LLM provider, models, keys)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    provider: Mapped[str | None] = mapped_column(String(20))
    model: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="conversation",
        order_by="ChatMessage.id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(10))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    steps: Mapped[str] = mapped_column(Text, default="[]")  # JSON: tools the assistant used
    cards: Mapped[str] = mapped_column(Text, default="[]")  # JSON: drafts and proposals
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
