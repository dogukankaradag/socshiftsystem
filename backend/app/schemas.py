"""Pydantic schemas for request/response serialization."""
from __future__ import annotations
from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict

from .models import (
    DailyDutyType, EntryType, IncidentStatus, MonthlyShiftSlot, PersonnelGroup,
    PersonnelLocation, Priority, ReportStatus, Role, RosterTeam, ShiftType,
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
    role: Role = Role.standard


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
    # --- "Arayanlar" (callers) snapshot alanları (v0.6.1+) ---
    caller_org_name: Optional[str] = Field(default=None, max_length=255)
    caller_contact_name: Optional[str] = Field(default=None, max_length=255)
    caller_contact_phone: Optional[str] = Field(default=None, max_length=64)
    # --- "DDoS Taşıma" için MPLS ekibi + otomatik hatırlatma (v0.8.14) ---
    mpls_team_id: Optional[int] = None
    mpls_reminder_enabled: Optional[bool] = False


class EntryCreate(EntryBase):
    shift_id: Optional[int] = None  # inferred to current open shift if omitted


class EntryUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    numeric_value: Optional[int] = Field(default=None, ge=0)
    occurs_at: Optional[datetime] = None
    incident_id: Optional[int] = None
    caller_org_name: Optional[str] = Field(default=None, max_length=255)
    caller_contact_name: Optional[str] = Field(default=None, max_length=255)
    caller_contact_phone: Optional[str] = Field(default=None, max_length=64)
    mpls_team_id: Optional[int] = None
    mpls_reminder_enabled: Optional[bool] = None


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
    #   scheduled_at set -> schedule for later (Europe/Istanbul local datetime accepted; naive = Europe/Istanbul)
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


class CallerStat(BaseModel):
    """Kullanıcı bazlı 'Arayanlar' girişi sayısı (performans metriği)."""
    user_id: int
    user_name: str
    count: int


class AnalyticsOverview(BaseModel):
    total_entries: int
    open_incidents: int
    upcoming_count: int = 0  # henüz zamanı gelmemiş planlı girişler
    entries_by_type: List[TypeCount]
    trend_14d: List[TrendPoint]
    totals_30d: List[TypeTotal]
    top_tags: List[dict]
    recurring_titles: List[dict]
    # v0.6.1: "Arayanlar" girişlerinin son 30 günlük kullanıcı dağılımı.
    # Hangi operatör kaç çağrı aldı — performans değerlendirmesi için.
    callers_by_user_30d: List[CallerStat] = []


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


# --- v0.6.1: Müşteri İrtibat Listesi -----------------------------------------
class CustomerContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = Field(default=None, max_length=512)


class CustomerContactUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = Field(default=None, max_length=512)


class CustomerContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    org_id: int
    name: str
    phone: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


class CustomerOrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    notes: Optional[str] = None
    # İlk kişiyi de aynı çağrıda oluşturmak için opsiyonel:
    initial_contact: Optional[CustomerContactCreate] = None


class CustomerOrgUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    notes: Optional[str] = None


class CustomerOrgOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    notes: Optional[str]
    contacts: List[CustomerContactOut] = []
    created_at: datetime
    updated_at: datetime


# --- v0.7.0: Aylık vardiya jeneratörü ----------------------------------------
class PersonnelCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=128)
    location: PersonnelLocation
    group: PersonnelGroup
    is_oncall_only: bool = False
    is_fixed_a: bool = False
    is_active: bool = True
    notes: Optional[str] = Field(default=None, max_length=512)


class PersonnelUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    location: Optional[PersonnelLocation] = None
    group: Optional[PersonnelGroup] = None
    is_oncall_only: Optional[bool] = None
    is_fixed_a: Optional[bool] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = Field(default=None, max_length=512)


class PersonnelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    full_name: str
    location: PersonnelLocation
    group: PersonnelGroup
    is_oncall_only: bool
    is_fixed_a: bool
    is_active: bool
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


class MonthlyShiftAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    personnel_id: int
    personnel_name: Optional[str] = None  # _to_out tarafından doldurulur
    day: date
    slot: MonthlyShiftSlot
    modified_by_user_id: Optional[int]
    note: Optional[str]
    created_at: datetime
    updated_at: datetime


class MonthlyShiftAssignmentUpdate(BaseModel):
    """Super admin manuel düzenleme — slot ve/veya note değiştirir."""
    slot: Optional[MonthlyShiftSlot] = None
    note: Optional[str] = Field(default=None, max_length=256)


class MonthlyShiftAssignmentCreate(BaseModel):
    """Super admin yeni bir kayıt elle eklediğinde."""
    personnel_id: int
    day: date
    slot: MonthlyShiftSlot
    note: Optional[str] = Field(default=None, max_length=256)


class GenerateMonthlyShiftRequest(BaseModel):
    """POST /monthly-shifts/generate payload'u."""
    year: int = Field(ge=2020, le=2100)
    month: int = Field(ge=1, le=12)
    # True ise mevcut ayın TÜM kayıtlarını siler (manuel müdahaleler dahil).
    # False ise sadece modified_by_user_id IS NULL olan kayıtları yeniden yazar.
    overwrite_manual: bool = False


class GenerateMonthlyShiftResult(BaseModel):
    year: int
    month: int
    days_generated: int
    assignments_created: int
    assignments_preserved: int  # manuel müdahale korundu
    warnings: List[str] = []


# --- v0.8.1: Dağıtıcı + Öğlen Nöbetçi (DailyDuty) ----------------------------
class DailyDutyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    day: date
    duty_type: DailyDutyType
    personnel_id: int
    personnel_name: Optional[str] = None  # _to_out tarafından doldurulur
    modified_by_user_id: Optional[int]
    note: Optional[str]
    created_at: datetime
    updated_at: datetime


class DailyDutyCreate(BaseModel):
    """Super admin elle bir görev ekler."""
    day: date
    duty_type: DailyDutyType
    personnel_id: int
    note: Optional[str] = Field(default=None, max_length=256)


class DailyDutyUpdate(BaseModel):
    personnel_id: Optional[int] = None
    note: Optional[str] = Field(default=None, max_length=256)


class GenerateDailyDutyRequest(BaseModel):
    year: int = Field(ge=2020, le=2100)
    month: int = Field(ge=1, le=12)
    overwrite_manual: bool = False


class GenerateDailyDutyResult(BaseModel):
    year: int
    month: int
    weekdays_generated: int
    assignments_created: int
    assignments_preserved: int
    per_person_distributor: dict[str, int] = {}  # personel_adı → atanan dağıtıcı sayısı
    per_person_lunch: dict[str, int] = {}
    warnings: List[str] = []


# --- v0.8.14: MPLS Ekipleri --------------------------------------------------
class MplsTeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    email: EmailStr
    notes: Optional[str] = Field(default=None, max_length=512)
    is_active: bool = True


class MplsTeamUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    email: Optional[EmailStr] = None
    notes: Optional[str] = Field(default=None, max_length=512)
    is_active: Optional[bool] = None


class MplsTeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str
    notes: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


# Forward-ref resolution
Token.model_rebuild()
