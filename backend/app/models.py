"""SQLAlchemy ORM models.

Domain model:
  User          - operators, supervisors, admins (RBAC)
  Shift         - a shift window (A/B/C, Europe/Istanbul), owned by 1..N operators
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
    """v0.6.2: Yeni iki rollü sistem.

    standard    → Standart kullanıcı. Sistem üzerinde tam yetkilidir;
                  kullanıcı oluşturma, mail listesi, rapor, giriş düzenleme
                  vb. tüm operasyonel yetkilere sahip. Vardiya çizelgesinde
                  yalnızca okuma yetkisi (read-only).
    super_admin → Standart yetkileri + Vardiya Listesi çizelgelerine manuel
                  müdahale (ekle/sil/düzenle/yükle) + yeni Super Admin
                  rolü atama yetkisi. Yalnızca bir super_admin başka bir
                  kullanıcıyı super_admin yapabilir.

    Eski 3 rollü sistem (operator / supervisor / admin) v0.6.2'de tek hamlede
    bu 2 role çekildi. Startup migration mevcut kullanıcıları otomatik
    standard'a düşürür ve en az bir super_admin'i (varsayılan: seed admin)
    promosyon eder.
    """
    standard = "standard"
    super_admin = "super_admin"


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
    """A/B/C vardiyaları (Europe/Istanbul).

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
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.standard)
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
    # --- "Arayanlar" (callers) için snapshot kolonları (v0.6.1+) ---
    # Müşteri İrtibat Listesi tablolarına FK koymak yerine string snapshot
    # tutuyoruz: irtibat ileride silinirse/değişirse rapordaki tarihsel kayıt
    # bozulmaz. CustomerOrg/CustomerContact tabloları sadece autocomplete
    # önerileri için kullanılır. Diğer entry türlerinde bu kolonlar null.
    caller_org_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    caller_contact_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    caller_contact_phone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # --- "DDoS Taşıma" için MPLS ekibi + otomatik hatırlatma (v0.8.14) ---
    # mpls_team_id set + mpls_reminder_enabled True ise, occurs_at'a 30 dk
    # kala MPLS ekibinin mail adresine hatırlatma otomatik gönderilir.
    # Diğer entry türlerinde bu alanlar null/false.
    mpls_team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("mpls_teams.id"), nullable=True)
    mpls_reminder_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # v0.8.16: "Arayanlar" için rapora dahil edilme takibi. Rapor dispatched
    # olduğunda o vardiyaya ait tüm callers girişleri reported_at ile
    # işaretlenir; bir sonraki generate bunları rapora eklemez (tek-seferlik).
    # Diğer türler bu alanı NULL bırakır.
    reported_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
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


# --- v0.6.1: Müşteri İrtibat Listesi -----------------------------------------
# "Arayanlar" giriş türünde operatör hangi kurumun (müşterinin) hangi
# kişisini girdiyse, bu kişi/numara çiftleri buradan autocomplete edilir.
# Bir kurumun birden fazla irtibat kişisi olabilir (1-N ilişki).
#
# Tarihsel veri bütünlüğü için Entry tablosundaki caller_org_name /
# caller_contact_name / caller_contact_phone alanları **snapshot** olarak
# tutulur — burada ileride yapılan değişiklikler eski girişleri etkilemez.

class CustomerOrg(Base):
    __tablename__ = "customer_orgs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    contacts: Mapped[List["CustomerContact"]] = relationship(
        back_populates="org", cascade="all, delete-orphan",
    )


class CustomerContact(Base):
    __tablename__ = "customer_contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("customer_orgs.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    org: Mapped["CustomerOrg"] = relationship(back_populates="contacts")

    __table_args__ = (
        Index("ix_customer_contact_org_name", "org_id", "name"),
    )


# --- Aylık vardiya jeneratörü ------------------------------------------------
# Rotasyon analizi (config'ten okunur):
#
#   - fixed_a grubu: hafta içi C kolonu (sabit A vardiyası, ofis)
#   - istanbul (vardiyaya girer): A 07:30-17:00 (E kolonu) + hafta sonu
#   - istanbul (on-call rotasyonu): vardiyaya girmez, sadece on-call
#   - ankara (vardiyaya girer): A 08:00-18:00 (D kolonu) + B/C rotasyon
#   - ankara (on-call rotasyonu): vardiyaya girmez, sadece on-call
#
#   - Hafta içi B vardiyası: 2 kişi (b_secondary çifti + 1 rotating)
#   - Hafta içi C vardiyası: 1 kişi (haftalık rotating)
#   - Hafta sonu A/B/C: her biri 1 farklı kişi
#   - On-call: 4 haftalık döngü Ank ↔ İst alternate
#   - Off-day: hafta sonu çalışan → hafta içi 1 gün izinli + hafta sonu 1 gün
#   - Vardiyaya girmeyenler: Pzt-Per ofiste, Cuma evden çalışma

class PersonnelLocation(str, enum.Enum):
    istanbul = "istanbul"
    ankara = "ankara"


class PersonnelGroup(str, enum.Enum):
    """Renk kodlamasıyla eşleşen üç grup.

    fixed_a   → siyah font: vardiyaya hiç girmez, sabit A
    istanbul  → mavi font:  İstanbul personeli
    ankara    → kırmızı font: Ankara personeli
    """
    fixed_a = "fixed_a"
    istanbul = "istanbul"
    ankara = "ankara"


class Personnel(Base):
    """Aylık vardiya jeneratörü için personel master tablosu.

    is_oncall_only: True ise bu kişi vardiyaya (B/C) hiç girmez, sadece
    on-call rotasyonuna girer.

    on_leave_until: belirli bir tarihe kadar izinli; jeneratör bu kişiyi
    o aralıkta atlar.
    """
    __tablename__ = "personnel"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    location: Mapped[PersonnelLocation] = mapped_column(Enum(PersonnelLocation), index=True)
    group: Mapped[PersonnelGroup] = mapped_column(Enum(PersonnelGroup), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Sadece on-call rotasyonu (vardiyaya girmez)
    is_oncall_only: Mapped[bool] = mapped_column(Boolean, default=False)
    # Sabit A vardiyası (rotation yok)
    is_fixed_a: Mapped[bool] = mapped_column(Boolean, default=False)
    # Notlar (örn. "izinli 30 Nisan'a kadar")
    notes: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class MonthlyShiftSlot(str, enum.Enum):
    """Bir günde bir personelin atanabileceği slotlar.

    a_fixed   → Sabit A (fixed_a grubu), C kolonu, 09:00-18:00 ofis
    a_ankara  → Ankara A (D kolonu), 08:00-18:00
    a_istanbul → İstanbul A (E kolonu), 07:30-17:00
    b_shift   → B vardiyası, 15:30-23:30
    c_shift   → C vardiyası, 23:30-07:30
    oncall    → On-call (Pzt-Paz aynı kişi, 7 gün)
    leave     → İzin
    off       → Off-day (hafta sonu çalışan için hafta içi 1 gün)
    wfh       → Evden Çalışma (v0.8.6, sadece manuel)
    """
    a_fixed = "a_fixed"
    a_ankara = "a_ankara"
    a_istanbul = "a_istanbul"
    b_shift = "b_shift"
    c_shift = "c_shift"
    oncall = "oncall"
    leave = "leave"
    off = "off"
    wfh = "wfh"


# --- v0.8.14: MPLS Ekipleri --------------------------------------------------
# DDoS Taşıma girişleri için taşımayı gerçekleştirecek MPLS ekibinin
# tanımlandığı master tablo. Kullanıcı yeni giriş oluştururken bu listeden
# seçim yapar; "otomatik hatırlatma" işaretlerse taşıma zamanına 30 dk kala
# ekibin mail adresine hatırlatma gider.

class MplsTeam(Base):
    __tablename__ = "mpls_teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255))
    notes: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class DailyDutyType(str, enum.Enum):
    """Hafta içi günlük görev türleri (v0.8.1).

    distributor → "Aylık Dağıtıcı" görevi (gün başına 1 kişi)
    lunch       → "Öğlen Nöbetçisi" görevi (gün başına 1 kişi)
    """
    distributor = "distributor"
    lunch = "lunch"


class DailyDuty(Base):
    """Hafta içi günlük dağıtıcı / öğlen nöbetçi ataması (v0.8.3: 2 kişi/slot).

    Bir gün × bir görev türü (dağıtıcı veya öğlen) için **2 kişiye kadar**
    atama yapılır. Generator her gün için:
      - 2 dağıtıcı (lokasyon kısıtsız)
      - 2 öğlen nöbetçi (her ikisi de aynı lokasyondan: Ank-Ank veya İst-İst)

    Aylık Vardiya'dan beslenir: o gün B/C/on-call/leave/off olmayan kişiler
    havuzdan seçilir (excluded_from_daily_duty listesindekiler hariç). Manuel müdahale
    `modified_by_user_id` ile korunur. Aynı kişi aynı gün × görev türü
    içinde birden fazla seat'e atanamaz (unique constraint).
    """
    __tablename__ = "daily_duty"

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[datetime] = mapped_column(Date, index=True)
    duty_type: Mapped[DailyDutyType] = mapped_column(Enum(DailyDutyType), index=True)
    personnel_id: Mapped[int] = mapped_column(ForeignKey("personnel.id"), index=True)
    modified_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    personnel: Mapped["Personnel"] = relationship()

    __table_args__ = (
        # v0.8.3: (day, duty_type) unique kaldırıldı → 2 kişi/slot.
        # Aynı kişi aynı gün+görev türü içinde tekrar atanmasın diye:
        Index("ix_daily_duty_person_unique", "day", "duty_type", "personnel_id", unique=True),
    )


class MonthlyShiftAssignment(Base):
    """Tek bir personelin tek bir gündeki vardiya ataması (v0.7.0).

    Bir ayın çizelgesi N personel × ~30 gün = ~300-500 satır. Jeneratör tüm
    ayı atomik olarak üretir (eski ayı silip yenisini yazar veya merge eder).
    Super admin elle bir kaydı düzenleyebilir; `modified_by_user_id`
    set edilirse jeneratör bu kaydı yeniden yazmaz.
    """
    __tablename__ = "monthly_shift_assignment"

    id: Mapped[int] = mapped_column(primary_key=True)
    personnel_id: Mapped[int] = mapped_column(ForeignKey("personnel.id"), index=True)
    day: Mapped[datetime] = mapped_column(Date, index=True)  # YYYY-MM-DD
    slot: Mapped[MonthlyShiftSlot] = mapped_column(Enum(MonthlyShiftSlot), index=True)
    # Manuel müdahale yapılmışsa (super admin), jeneratör bu satırı korur.
    modified_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    personnel: Mapped["Personnel"] = relationship()

    __table_args__ = (
        Index("ix_msa_day_person", "day", "personnel_id", unique=True),
    )
