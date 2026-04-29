"""Pydantic schemas for request/response serialization."""
from __future__ import annotations
from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict

from .models import (
    EntryType, IncidentStatus, Priority, ReportStatus, Role, RosterTeam, ShiftType,
)


# ---------- Auth ----------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# ---------- Users ----------
class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: Role = Role.operator


class UserCreate(UserBase):
    password: str = Field(min_length=8)


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[Role] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8)


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: bool
    created_at: datetime


# ---------- Shifts ----------
class ShiftCreate(BaseModel):
    shift_type: ShiftType
    started_at: Optional[datetime] = None
    supervisor_id: Optional[int] = None
    notes: Optional[str] = None


class ShiftUpdate(BaseModel):
    ended_at: Optional[datetime] = None
    notes: Optional[str] = None
    supervisor_id: Optional[int] = None


class ShiftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    shift_type: ShiftType
    started_at: datetime
    ended_at: Optional[datetime]
    supervisor_id: Optional[int]
    notes: Optional[str]
    entry_count: int = 0


# ---------- Entries ----------
class EntryBase(BaseModel):
    entry_type: EntryType
    title: Optional[str] = Field(default=None, max_length=255)
    body: Optional[str] = ""
    numeric_value: Optional[int] = Field(default=None, ge=0)
    # Olayın planlanan gerçekleşme zamanı (UTC). Null ise anlık girişi temsil eder.
    occurs_at: Optional[datetime] = None
    incident_id: Optional[int] = None


class EntryCreate(EntryBase):
    shift_id: Optional[int] = None  # inferred to current open shift if omitted


class EntryUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    numeric_value: Optional[int] = Field(default=None, ge=0)
    occurs_at: Optional[datetime] = None
    incident_id: Optional[int] = None


class EntryOut(EntryBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    shift_id: int
    author_id: int
    author_name: Optional[str] = None
    tags: Optional[str] = None
    source: Optional[str] = None
    reminder_sent_at: Optional[datetime] = None
    is_duplicate_of: Optional[int]
    created_at: datetime
    updated_at: datetime


# ---------- Incidents ----------
class IncidentCreate(BaseModel):
    title: str
    description: str
    priority: Priority = Priority.high
    assigned_to_id: Optional[int] = None
    tags: Optional[str] = None


class IncidentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[IncidentStatus] = None
    priority: Optional[Priority] = None
    assigned_to_id: Optional[int] = None
    resolution_notes: Optional[str] = None
    tags: Optional[str] = None


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: str
    status: IncidentStatus
    priority: Priority
    opened_by_id: int
    assigned_to_id: Optional[int]
    opened_at: datetime
    resolved_at: Optional[datetime]
    resolution_notes: Optional[str]
    tags: Optional[str]
    entry_count: int = 0


# ---------- Reports ----------
class ReportGenerateRequest(BaseModel):
    shift_id: int
    # Operatör son adımda A/B/C vardiya etiketini seçer. Verilirse vardiyanın
    # mevcut tipini ezer ve rapor bu etiketle hazırlanır.
    shift_type: Optional[ShiftType] = None
    # Mail konusu override'ı. Null ise varsayılan "MSSP Vardiya Raporu — X Vardiyası (tarih)"
    # kullanılır.
    subject_override: Optional[str] = Field(default=None, max_length=255)
    to_recipients: Optional[List[EmailStr]] = None
    cc_recipients: Optional[List[EmailStr]] = None
    # Dispatch mode:
    #   dispatch=True + scheduled_at=None -> send immediately
    #   scheduled_at set -> schedule for later (GMT+3 local datetime accepted; naive = Europe/Istanbul)
    #   dispatch=False, scheduled_at=None -> draft
    dispatch: bool = False
    scheduled_at: Optional[datetime] = None


class ReportUpdate(BaseModel):
    """Sadece taslak / planlı / başarısız raporlar üzerinde geçerli alanlar."""
    title: Optional[str] = Field(default=None, max_length=255)
    summary: Optional[str] = None
    body_markdown: Optional[str] = None
    recipients: Optional[List[EmailStr]] = None
    cc_recipients: Optional[List[EmailStr]] = None
    scheduled_at: Optional[datetime] = None


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    shift_id: int
    title: str
    summary: str
    body_markdown: str
    body_html: Optional[str]
    status: ReportStatus
    recipients: Optional[str]
    cc_recipients: Optional[str]
    scheduled_at: Optional[datetime]
    dispatched_at: Optional[datetime]
    error_message: Optional[str]
    created_at: datetime


# ---------- Analytics ----------
class TypeCount(BaseModel):
    entry_type: EntryType
    count: int


class TypeTotal(BaseModel):
    """30-day totals per EntryType (count + sum of numeric_value)."""
    entry_type: EntryType
    count: int
    total: int


class TrendPoint(BaseModel):
    date: str  # YYYY-MM-DD
    total: int


class AnalyticsOverview(BaseModel):
    total_entries: int
    open_incidents: int
    upcoming_count: int = 0  # henüz zamanı gelmemiş planlı girişler
    entries_by_type: List[TypeCount]
    trend_14d: List[TrendPoint]
    totals_30d: List[TypeTotal]
    top_tags: List[dict]
    recurring_titles: List[dict]


# ---------- Mailing lists ----------
class MailingListCreate(BaseModel):
    name: str
    recipients: str
    cc_recipients: Optional[str] = None
    is_default: bool = False
    shift_type: Optional[ShiftType] = None


class MailingListUpdate(BaseModel):
    name: Optional[str] = None
    recipients: Optional[str] = None
    cc_recipients: Optional[str] = None
    is_default: Optional[bool] = None
    shift_type: Optional[ShiftType] = None


class MailingListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    recipients: str
    cc_recipients: Optional[str]
    is_default: bool
    shift_type: Optional[ShiftType]


# ---------- Roster (Nöbetçi Listesi) ----------
class RosterEntryCreate(BaseModel):
    team: RosterTeam
    person_name: str = Field(min_length=1, max_length=255)
    start_date: date
    end_date: date
    shift_label: Optional[str] = Field(default=None, max_length=16)
    notes: Optional[str] = Field(default=None, max_length=512)


class RosterEntryUpdate(BaseModel):
    person_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    shift_label: Optional[str] = Field(default=None, max_length=16)
    notes: Optional[str] = Field(default=None, max_length=512)
    team: Optional[RosterTeam] = None


class RosterEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    team: RosterTeam
    person_name: str
    start_date: date
    end_date: date
    shift_label: Optional[str]
    notes: Optional[str]
    upload_batch: Optional[str]
    uploaded_by_id: Optional[int]
    uploaded_at: datetime


class RosterUploadResult(BaseModel):
    upload_batch: str
    parsed_count: int
    team: RosterTeam
    warnings: List[str] = []


# Forward-ref resolution
Token.model_rebuild()
