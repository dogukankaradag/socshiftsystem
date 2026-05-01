"""SQLAlchemy ORM models.

Domain model:
  User          - operators, supervisors, admins (RBAC)
  Shift         - a shift window (A/B/C, Europe/Istanbul GMT+3), owned by 1..N operators
  Entry         - structured operator input during a shift (see EntryType)
  Incident      - long-running issues with status lifecycle (open -> resolved)
  Report        - generated & dispatched handover report (snapshot of entries)
  AuditLog      - append-only trail of privileged actions
  MailingList   - configurable distribution lists for auto-dispatch
  OnCallRoster  - L2 / MSSP on-call schedule entries parsed from uploaded files

All data stays local. No third-party / cloud services are contacted at runtime.
"""
from __future__ import annotations
import enum
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    String, Integer, DateTime, Date, Text, ForeignKey, Enum, Boolean, JSON, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    operator = "operator"
    supervisor = "supervisor"
    admin = "admin"


class Priority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class EntryType(str, enum.Enum):
    """Domain-specific entry categories used during a shift."""
    ddos_transfer = "ddos_transfer"      # DDoS Taşıma (metin)
    info = "info"                        # Bilgi (metin)
    important_work = "important_work"    # Yapılan Önemli İşler (metin)
    l2_escalation = "l2_escalation"      # L2'ye eskale edilen konu(lar) (metin)
    callers = "callers"                  # Arayanlar (metin)
    dhs = "dhs"                          # DHS case sayısı (sayı)
    iys = "iys"                          # İYS case sayısı (sayı)


NUMERIC_ENTRY_TYPES = {EntryType.dhs, EntryType.iys}


class ShiftType(str, enum.Enum):
    """A/B/C vardiyaları (Europe/Istanbul, GMT+3).

    A: 07:30 - 15:30
    B: 15:30 - 23:30
    C: 23:30 - 07:30
    """
    a = "a"
    b = "b"
    c = "c"


class IncidentStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    closed = "closed"


class ReportStatus(str, enum.Enum):
    draft = "draft"
    scheduled = "scheduled"
    dispatched = "dispatched"
    failed = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.operator)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    entries: Mapped[List["Entry"]] = relationship(back_populates="author")


class Shift(Base):
    __tablename__ = "shifts"

    id: Mapped[int] = mapped_column(primary_key=True)
    shift_type: Mapped[ShiftType] = mapped_column(Enum(ShiftType))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    supervisor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    entries: Mapped[List["Entry"]] = relationship(back_populates="shift", cascade="all, delete-orphan")
    reports: Mapped[List["Report"]] = relationship(back_populates="shift", cascade="all, delete-orphan")


class Entry(Base):
    __tablename__ = "entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    entry_type: Mapped[EntryType] = mapped_column(Enum(EntryType), index=True)
    # Title is optional; kept for legacy/display, auto-derived from entry_type if blank.
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Text body for narrative entry types (ddos_transfer, info, important_work, l2_escalation, callers).
    body: Mapped[str] = mapped_column(Text, default="")
    # Numeric value for countable types (DHS, İYS). Null for text entries.
    numeric_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Olayın planlanan gerçekleşme zamanı (UTC). Doldurulursa giriş, occurs_at zamanına
    # kadar oluşturulan tüm vardiya raporlarına otomatik dahil edilir ve 30 dk kala
    # hatırlatma e-postası gönderilir. Null = anlık/retroaktif giriş.
    occurs_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    # Hatırlatma e-postasının gönderildiği zaman (tekrar göndermeyi engellemek için).
    reminder_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Bu girişin otomatik bir kaynak (ör. IMAP poller) tarafından oluşturulup
    # oluşturulmadığı. Gösterimde küçük bir etiket ile gösterilir.
    source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    incident_id: Mapped[Optional[int]] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    is_duplicate_of: Mapped[Optional[int]] = mapped_column(ForeignKey("entries.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    shift: Mapped["Shift"] = relationship(back_populates="entries")
    author: Mapped["User"] = relationship(back_populates="entries")
    incident: Mapped[Optional["Incident"]] = relationship(back_populates="entries", foreign_keys=[incident_id])

    __table_args__ = (
        Index("ix_entries_shift_occurs", "shift_id", "occurs_at"),
    )


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[IncidentStatus] = mapped_column(Enum(IncidentStatus), default=IncidentStatus.open, index=True)
    priority: Mapped[Priority] = mapped_column(Enum(Priority), default=Priority.high)
    opened_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assigned_to_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    entries: Mapped[List["Entry"]] = relationship(back_populates="incident", foreign_keys="Entry.incident_id")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id"), index=True)
    generated_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text)
    body_markdown: Mapped[str] = mapped_column(Text)
    body_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[ReportStatus] = mapped_column(Enum(ReportStatus), default=ReportStatus.draft, index=True)
    # TO recipients (comma-separated). "recipients" kept as column name for back-compat.
    recipients: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # CC recipients (comma-separated).
    cc_recipients: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # When to auto-dispatch (UTC). Null = dispatched immediately or kept as draft.
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    shift: Mapped["Shift"] = relationship(back_populates="reports")


class MailingList(Base):
    __tablename__ = "mailing_lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    recipients: Mapped[str] = mapped_column(Text)
    cc_recipients: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    shift_type: Mapped[Optional[ShiftType]] = mapped_column(Enum(ShiftType), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(128), index=True)
    target_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    target_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class RosterTeam(str, enum.Enum):
    """Nöbetçi & dağıtıcı listesi ekibi.

    L2 / MSSP   → "Nöbetçi Listesi" sayfasında görüntülenir.
    Distributor / Lunch → "Dağıtıcı Listesi" sayfasında görüntülenir.
    Aynı OnCallRoster tablosunu paylaşır; sadece team değeri ayrışır.
    """
    l2 = "l2"                    # L2 nöbetçi
    mssp = "mssp"                # MSSP aylık vardiya çizelgesi
    distributor = "distributor"  # Aylık dağıtıcı (Dağıtıcı Listesi sayfası)
    lunch = "lunch"              # Öğlen nöbetçileri (Dağıtıcı Listesi sayfası)


# Hangi RosterTeam değerleri "Dağıtıcı Listesi" sayfasında listelenir.
DISTRIBUTOR_TEAMS = {RosterTeam.distributor, RosterTeam.lunch}
# Hangi RosterTeam değerleri "Nöbetçi Listesi" sayfasında listelenir.
ROSTER_TEAMS = {RosterTeam.l2, RosterTeam.mssp}


class OnCallRoster(Base):
    """Yüklenen XLSX/PDF nöbetçi çizelgelerinden parse edilmiş satırlar.

    Her satır, bir kişinin belirli bir tarih aralığında (start_date–end_date)
    belirli bir ekipte (L2 / MSSP) nöbetçi olduğunu temsil eder. MSSP
    vardiyaları için `shift_label` kolonu A/B/C etiketini taşır.
    """
    __tablename__ = "oncall_roster"

    id: Mapped[int] = mapped_column(primary_key=True)
    team: Mapped[RosterTeam] = mapped_column(Enum(RosterTeam), index=True)
    person_name: Mapped[str] = mapped_column(String(255), index=True)
    start_date: Mapped[datetime] = mapped_column(Date, index=True)
    end_date: Mapped[datetime] = mapped_column(Date, index=True)
    # MSSP için A/B/C vardiya etiketi; L2 için null.
    shift_label: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    # Bu satırı hangi yükleme grubundan geldiği — aynı yükleme birlikte
    # silinebilsin diye UUID'ye benzer bir tekil anahtar.
    upload_batch: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    uploaded_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    __table_args__ = (
        Index("ix_oncall_team_range", "team", "start_date", "end_date"),
    )
