from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    department: str | None
    capacity: int
    byod: bool
    needs_hod_approval: bool
    in_charge: InChargeOut | None


class VenueDetailOut(VenueOut):
    equipment: list[EquipmentOut]
    aliases: list[str]


class StatusPeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    from_date: date
    to_date: date | None
    reason: str | None


class SeasonalRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    start_month: int
    end_month: int
    kind: str
    reason: str


class VenueFullOut(VenueDetailOut):
    technician: InChargeOut | None
    notes: str | None
    status_periods: list[StatusPeriodOut]
    seasonal_rules: list[SeasonalRuleOut]
    can_edit: bool
    can_update_equipment: bool
    can_edit_restricted: bool


VenueType = Literal["lab", "seminar_hall", "coe"]
EquipmentCategory = Literal["hardware", "software", "av", "facility"]
EquipmentStatus = Literal["working", "faulty", "under_repair"]


class VenueCreate(BaseModel):
    code: str = Field(min_length=1, max_length=30, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    type: VenueType
    department: str | None = "CSE"
    capacity: int = Field(gt=0, le=2000)
    byod: bool = False
    needs_hod_approval: bool = False
    in_charge_email: str | None = None
    technician_email: str | None = None
    notes: str | None = None


class VenueUpdate(BaseModel):
    # Anyone who can edit the venue
    name: str | None = Field(default=None, min_length=1, max_length=120)
    notes: str | None = None
    byod: bool | None = None
    # Director only
    type: VenueType | None = None
    department: str | None = None
    capacity: int | None = Field(default=None, gt=0, le=2000)
    needs_hod_approval: bool | None = None
    in_charge_email: str | None = None
    technician_email: str | None = None


RESTRICTED_VENUE_FIELDS = {
    "type",
    "department",
    "capacity",
    "needs_hod_approval",
    "in_charge_email",
    "technician_email",
}


class EquipmentIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: EquipmentCategory
    quantity: int = Field(default=1, ge=1, le=10000)
    status: EquipmentStatus = "working"


class EquipmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: EquipmentCategory | None = None
    quantity: int | None = Field(default=None, ge=1, le=10000)
    status: EquipmentStatus | None = None


class StatusPeriodIn(BaseModel):
    status: Literal["maintenance", "renovation", "closed"]
    from_date: date
    to_date: date | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _order(self):
        if self.to_date and self.to_date < self.from_date:
            raise ValueError("to_date must be on or after from_date")
        return self


class SeasonalRuleIn(BaseModel):
    start_month: int = Field(ge=1, le=12)
    end_month: int = Field(ge=1, le=12)
    kind: Literal["blocked", "soft_warning"]
    reason: str = Field(min_length=1)


class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    roles: list[str] = []


class BlockOut(BaseModel):
    start: datetime
    end: datetime
    kind: str
    label: str
    hard: bool


class NoticeOut(BaseModel):
    kind: str
    message: str


class VenueDayOut(BaseModel):
    code: str
    name: str
    type: str
    capacity: int
    byod: bool
    blocks: list[BlockOut]
    warnings: list[NoticeOut]


class DayAvailabilityOut(BaseModel):
    date: date
    open_from: time | None
    open_to: time | None
    slot_minutes: int
    venues: list[VenueDayOut]


class VenueRangeDayOut(BaseModel):
    date: date
    open_from: time | None
    open_to: time | None
    blocks: list[BlockOut]
    warnings: list[NoticeOut]


class VenueRangeOut(BaseModel):
    code: str
    name: str
    days: list[VenueRangeDayOut]


class CheckOut(BaseModel):
    venue: str
    start: datetime
    end: datetime
    free: bool
    needs_displacement: bool
    conflicts: list[BlockOut]
    classes: list[BlockOut]
    warnings: list[NoticeOut]


class TimetableSlotIn(BaseModel):
    weekday: str
    start: str
    end: str
    subject_code: str = Field(min_length=1)
    subject_name: str = ""
    faculty_name: str = ""
    batch: str = "all"
    venue: str = Field(min_length=1)


class TimetableHeader(BaseModel):
    dept: str | None = None
    year: str | None = None
    section: str | None = None
    term_name: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    class_advisor: str | None = None


class TimetableReviewIn(BaseModel):
    header: TimetableHeader
    slots: list[TimetableSlotIn]


class TimetableUploadOut(BaseModel):
    id: int
    filename: str
    status: str
    uploaded_at: datetime
    header: dict
    periods: list[dict]
    grid: dict
    slots: list[dict]
    problems: list[str]
    can_commit: bool


class TimetableUploadBrief(BaseModel):
    id: int
    filename: str
    status: str
    uploaded_at: datetime
    section: str | None
    slots: int
    can_commit: bool


class SectionOut(BaseModel):
    id: int
    label: str
    dept: str
    year: str
    section: str
    advisor: str | None
    lab_slots: int


class ClassSlotOut(BaseModel):
    id: int
    section: str
    term: str
    venue: str
    weekday: str
    start: time
    end: time
    subject_code: str
    subject_name: str
    faculty_name: str | None
    batch: str


# Bookings ---------------------------------------------------------------------------------------


class MoveIn(BaseModel):
    slot_id: int
    date: date
    action: Literal["relocated", "byod_classroom"]
    venue_code: str | None = None


class BookingIn(BaseModel):
    venue: str
    title: str = Field(max_length=200)
    event_type: str
    expected_count: int = Field(ge=1, le=2000)
    date_from: date
    date_to: date | None = None
    start_time: time
    end_time: time
    description: str | None = Field(default=None, max_length=4000)
    requirements: str | None = Field(default=None, max_length=2000)
    moves: list[MoveIn] = []


class BookingSubmitIn(BookingIn):
    join_waitlist: bool = False
    reschedule_of: int | None = None


class RelocationOptionOut(BaseModel):
    code: str
    name: str
    capacity: int
    software_match: float
    missing_software: list[str]


class ClassClashOut(BaseModel):
    slot_id: int
    date: date
    label: str
    subject_name: str
    faculty_name: str | None
    start: time
    end: time
    batch_size: int
    options: list[RelocationOptionOut]


class VenueBrief(BaseModel):
    code: str
    name: str
    type: str
    capacity: int


class BookingCheckOut(BaseModel):
    venue: VenueBrief
    outcome: Literal["free", "displace", "waitlist", "blocked"]
    days: list[date]
    blocked: list[BlockOut]
    taken: list[BlockOut]
    clashes: list[ClassClashOut]
    warnings: list[NoticeOut]
    alternatives: list[VenueBrief]


class OccurrenceOut(BaseModel):
    start: datetime
    end: datetime


class ApprovalOut(BaseModel):
    step: str
    decision: str
    approver: str | None
    comment: str | None
    decided_at: datetime


class MoveOut(BaseModel):
    slot_id: int
    date: date
    label: str
    time: str
    action: str
    venue: str | None
    faculty_name: str | None


class StudentOut(BaseModel):
    id: int
    name: str
    register_no: str | None
    class_label: str
    decision: str
    comment: str | None
    decided_at: datetime | None


class BookingOut(BaseModel):
    id: int
    ref: str
    title: str
    event_type: str
    description: str | None
    requirements: str | None
    expected_count: int
    venue: VenueBrief
    requester: str
    requester_email: str
    status: str
    start: datetime
    end: datetime
    occurrences: list[OccurrenceOut]
    approvals: list[ApprovalOut]
    moves: list[MoveOut]
    steps: list[str]
    waitlist_position: int | None
    offer_expires_at: datetime | None
    cancel_reason: str | None
    parent_ref: str | None
    created_at: datetime
    can_cancel: bool
    can_reschedule: bool
    can_approve: bool
    kind: str = "staff"
    guide: str | None = None
    students: list[StudentOut] = []
    tracking_code: str | None = None
    contact_email: str | None = None


class ApprovalItemOut(BaseModel):
    booking: BookingOut
    step: str
    notes: list[str]
    waiting_behind: int


class DecisionHistoryOut(BaseModel):
    booking: BookingOut
    step: str
    decision: str
    comment: str | None
    decided_at: datetime


class StudentDecisionItem(BaseModel):
    student_id: int
    decision: Literal["approved", "rejected"]
    comment: str | None = Field(default=None, max_length=1000)


class StudentDecisionIn(BaseModel):
    decisions: list[StudentDecisionItem] = Field(min_length=1, max_length=20)


class DecisionIn(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)


class CancelIn(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    message: str
    link: str | None
    created_at: datetime
    read_at: datetime | None


# Documents and past events -----------------------------------------------------------------------


class DocRef(BaseModel):
    id: int
    kind: str
    ref_no: str | None
    filename: str
    file_url: str


class PastEventBrief(BaseModel):
    id: int
    title: str
    event_type: str
    start_date: date | None
    end_date: date | None
    venues: list[str]
    needs_review: bool


class DocumentOut(DocRef):
    department: str | None
    academic_year: str | None
    issued_on: date | None
    uploaded_at: datetime
    problems: list[str]
    event: PastEventBrief | None


class DocumentDetailOut(DocumentOut):
    text: str
    fields: dict


class UploadResultOut(BaseModel):
    filename: str
    document: DocumentOut | None = None
    error: str | None = None
    replaced: bool = False


class PastEventOut(BaseModel):
    id: int
    title: str
    series_key: str
    event_type: str
    department: str | None
    venue_text: str | None
    venues: list[VenueBrief]
    start_date: date | None
    end_date: date | None
    start_time: time | None
    end_time: time | None
    audience: str | None
    expected_count: int | None
    participants: int | None
    registered: int | None
    resource_persons: str | None
    topics: list[str]
    rating: float | None
    needs_review: bool
    problems: list[str]
    edited: bool
    circular: DocRef | None
    report: DocRef | None


class PastEventUpdate(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    event_type: str
    venue_codes: list[str]
    start_date: date
    end_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    participants: int | None = Field(default=None, ge=0)
    resource_persons: str | None = None

    @model_validator(mode="after")
    def _order(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("The last day can't be before the first day")
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValueError("The end time must be after the start time")
        return self


class EventFacetsOut(BaseModel):
    event_types: list[str]
    years: list[str]
    documents: int
    events: int
    needs_review: int
    embedded: int
    embeddings: str  # on | off


class SearchHitOut(BaseModel):
    document: DocRef
    event: PastEventBrief | None
    snippet: str
    score: float
    matched_by: list[str]


class SearchOut(BaseModel):
    query: str
    mode: str  # hybrid | keywords
    hits: list[SearchHitOut]


# Assistant ---------------------------------------------------------------------------------------


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class AttachmentOut(BaseModel):
    kind: Literal["timetable", "document", "text"]
    title: str
    context: str  # what the assistant is told about the file
    link: str | None = None


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: int | None = None
    provider: Literal["groq", "ollama"] | None = None
    model: str | None = Field(None, max_length=80)
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)  # visitors only
    attachment: AttachmentOut | None = None
    # Run the last message again: its earlier reply (if any) is replaced, not kept.
    regenerate: bool = False


class ConversationBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    provider: str | None
    model: str | None
    updated_at: datetime


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    steps: list[dict]
    cards: list[dict]
    created_at: datetime


class ConversationOut(ConversationBrief):
    messages: list[ChatMessageOut]


class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class CardStateIn(BaseModel):
    state: Literal["done", "dismissed"]
    note: str | None = Field(None, max_length=300)


class ProviderOut(BaseModel):
    key: str
    label: str
    ready: bool
    note: str
    models: list[str]
    model: str  # the default model


class ProvidersOut(BaseModel):
    default: str
    demo: bool  # the scripted demo assistant answers instead of a real model
    providers: list[ProviderOut]


class LLMSettingsOut(BaseModel):
    provider: str
    groq_model: str
    groq_fallback_model: str
    groq_key_set: bool
    groq_key_masked: str
    groq_key_source: str  # settings | env | none
    ollama_base_url: str
    ollama_model: str


class LLMSettingsIn(BaseModel):
    provider: Literal["groq", "ollama"] | None = None
    groq_api_key: str | None = Field(None, max_length=200)  # "" removes the saved key
    groq_model: str | None = Field(None, max_length=80)
    groq_fallback_model: str | None = Field(None, max_length=80)
    ollama_base_url: str | None = Field(None, max_length=200)
    ollama_model: str | None = Field(None, max_length=80)


class LLMTestIn(BaseModel):
    provider: Literal["groq", "ollama"]
    model: str | None = Field(None, max_length=80)


class LLMTestOut(BaseModel):
    ok: bool
    message: str


# Student requests (no login) ---------------------------------------------------------------------


class StudentIn(BaseModel):
    name: str = Field(max_length=120)
    register_no: str | None = Field(default=None, max_length=30)
    section_id: int


class StudentSlotIn(BaseModel):
    venue: str
    date_from: date
    date_to: date | None = None
    start_time: time
    end_time: time
    count: int = Field(default=1, ge=1, le=10)


class StudentBookingIn(BaseModel):
    venue: str
    date_from: date
    date_to: date | None = None
    start_time: time
    end_time: time
    reason: str = Field(max_length=2000)
    guide_id: int
    contact_email: str = Field(max_length=120)
    students: list[StudentIn] = Field(max_length=10)


class StudentCheckOut(BaseModel):
    venue: VenueBrief
    ok: bool
    problem: str | None
    days: list[date]
    warnings: list[NoticeOut]
    alternatives: list[VenueBrief]


class ClassOptionOut(BaseModel):
    id: int
    label: str
    dept: str
    year: str
    section: str


class GuideOut(BaseModel):
    id: int
    name: str
    designation: str | None


class StudentOptionsOut(BaseModel):
    sections: list[ClassOptionOut]
    guides: list[GuideOut]
    venues: list[VenueBrief]
    max_students: int
    email_domain: str | None


class TrackStepOut(BaseModel):
    step: str
    label: str
    state: Literal["done", "current", "waiting", "rejected", "skipped"]
    approver: str | None
    comment: str | None
    decided_at: datetime | None


class StudentTrackOut(BaseModel):
    ref: str
    tracking_code: str
    status: str
    venue: VenueBrief
    reason: str
    guide: str | None
    contact_email: str | None  # masked
    occurrences: list[OccurrenceOut]
    students: list[StudentOut]
    steps: list[TrackStepOut]
    created_at: datetime
    cancel_reason: str | None
    can_cancel: bool


class MailSettingsOut(BaseModel):
    host: str
    port: int
    user: str
    from_addr: str
    password_set: bool
    password_source: str  # settings | env | none
    configured: bool
    student_email_domain: str | None


class MailSettingsIn(BaseModel):
    host: str | None = Field(default=None, max_length=200)
    port: int | None = Field(default=None, ge=1, le=65535)
    user: str | None = Field(default=None, max_length=200)
    password: str | None = Field(default=None, max_length=200)
    from_addr: str | None = Field(default=None, max_length=200)


class MailTestIn(BaseModel):
    to: str = Field(max_length=120)
