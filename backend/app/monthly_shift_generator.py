"""Aylık vardiya çizelgesi otomatik jeneratörü.

İş kuralları (yapılandırma ile parametrize):

  ROTASYON LİSTESİ (Hafta içi B/C 1. personel):
    `weekday_rotation` config listesindeki kişiler 1 hafta B-1st, sonraki
    hafta C-1st olarak çalışır (2 hafta vardiya, sonra N hafta bekleme).

  HAFTA İÇİ B VARDIYASI (2 KİŞİ):
    1. personel: weekday_rotation[week_index % len] — tüm hafta (Pzt-Cu)
    2. personel: `b_secondary` config listesinden 2 kişi, ardışık günleri
       böler:
         - Birinci (b_secondary[0]) Pzt-başlangıç, ikinci (b_secondary[1])
           Cu-sonuç.
         - Çift hafta: 3-2 (baş 3 gün, son 2 gün); tek hafta: 2-3

  HAFTA İÇİ C VARDIYASI (1 KİŞİ):
    C-1st = weekday_rotation[(week_index - 1) % len] (önceki haftanın B-1st'i)

  ON-CALL (Pzt-Paz tüm hafta tek kişi):
    Rotasyon: `oncall_rotation` config listesi (haftalık döngü).
    Bu kişiler is_oncall_only=True; vardiyaya (B/C) hiç girmez.

  HAFTA İÇİ A (geri kalanlar):
    B/C/on-call/B-2nd dışındaki tüm worker'lar hafta içi günü kendi
    lokasyonunun A vardiyasında (Ankara → a_ankara, İstanbul → a_istanbul).

  HAFTA SONU (Cmt-Paz):
    A, B, C için 3 ayrı kişi her gün (toplam 6 kişi-günü).
    Hafta içinde B/C-1st olarak çalışan kişiler hafta sonu off (max 5/hafta).
    B-2nd de bu hafta B'ye girdiyse hafta sonu off. Geri kalan worker'lar
    haftalık rotasyonla hafta sonu kapatır.

  MANUEL MÜDAHALE:
    Bir MonthlyShiftAssignment'ta modified_by_user_id IS NOT NULL ise
    jeneratör o (personnel_id, day) çiftine dokunmaz. overwrite_manual=True
    ile zorlanabilir.

  FORCED_OVERRIDES:
    Config'teki `forced_overrides` her Otomatik Üret / Sıfırla & Üret'te
    garantili uygulanır. Manuel veya otomatik atama olsa bile üstüne yazılır.
    On-call slot'lu bir override o hafta için normal rotasyonu skipler.

  PAZAR C → PAZARTESİ OFF (v0.9.1):
    Hafta sonu Pazar günü C vardiyasında olan kişi bir sonraki Pazartesi
    hiçbir slotta yer alamaz — otomatik `off` atanır. Cross-month'ta önceki
    ayın son Pazar'ı da DB'den okunup uygulanır. Manuel-lock veya
    FORCED_OVERRIDE mevcutsa dokunulmaz.
"""
from __future__ import annotations
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .models import (
    MonthlyShiftAssignment, MonthlyShiftSlot, Personnel, PersonnelGroup,
)
from .personnel_config import get_personnel_config


# --- Yardımcılar --------------------------------------------------------------

def _daterange(start: date, end: date):
    """Kapsayıcı date range yardımcısı (start ve end dahil)."""
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _by_name(personnel: list[Personnel]) -> dict[str, Personnel]:
    return {p.full_name: p for p in personnel}


def _resolve_slot(value: str) -> Optional[MonthlyShiftSlot]:
    try:
        return MonthlyShiftSlot(value)
    except ValueError:
        return None


def _expanded_forced_overrides() -> list[tuple[str, date, MonthlyShiftSlot]]:
    """Config forced_overrides listesini (name, day, slot) tuple'larına açar."""
    cfg = get_personnel_config()
    out: list[tuple[str, date, MonthlyShiftSlot]] = []
    for o in cfg.forced_overrides:
        slot = _resolve_slot(o.slot)
        if slot is None:
            continue
        for d in _daterange(o.start_date, o.end_date):
            out.append((o.name, d, slot))
    return out


#: Rotasyon anchor — config'ten okunur. Bu Pazartesi = weekday_rotation[0].
ROTATION_ANCHOR_MONDAY: date = get_personnel_config().rotation_anchor_monday


def _week_index_for_monday(monday: date, year: int) -> int:
    """Anchor Pazartesi'den itibaren kaç hafta geçti? (negatif olabilir)"""
    delta_days = (monday - ROTATION_ANCHOR_MONDAY).days
    return delta_days // 7


def _weeks_in_month(year: int, month: int) -> list[list[date]]:
    """Ayın günlerini Pzt-Paz haftalara böl (kısmi haftalara izin verir)."""
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])
    days: list[date] = []
    d = first_day
    while d <= last_day:
        days.append(d)
        d += timedelta(days=1)

    weeks: list[list[date]] = []
    current: list[date] = []
    for day in days:
        if day.weekday() == 0 and current:
            weeks.append(current)
            current = []
        current.append(day)
    if current:
        weeks.append(current)
    return weeks


def _monday_of_week(week_days: list[date]) -> date:
    if week_days[0].weekday() == 0:
        return week_days[0]
    return week_days[0] - timedelta(days=week_days[0].weekday())


def _pick_rotating(items: list, week_index: int):
    if not items:
        return None
    return items[week_index % len(items)]


# --- Hafta sonu rotasyon yardımcısı -------------------------------------------

def _weekend_assignments_for_week(
    week_days: list[date],
    workers_available: list[Personnel],
    week_index: int,
) -> dict[date, dict[MonthlyShiftSlot, Personnel]]:
    """Hafta sonu (Cmt-Paz) için A/B/C atamalarını üret (deterministic)."""
    out: dict[date, dict[MonthlyShiftSlot, Personnel]] = {}
    if not workers_available:
        return out

    weekend_days = [d for d in week_days if d.weekday() >= 5]
    if not weekend_days:
        return out

    n = len(workers_available)
    if n < 3:
        weekend_days = weekend_days[:1]

    base = (week_index * 6) % n
    for i, day in enumerate(weekend_days):
        slots = (MonthlyShiftSlot.a_istanbul, MonthlyShiftSlot.b_shift, MonthlyShiftSlot.c_shift)
        out[day] = {}
        for j, slot in enumerate(slots):
            idx = (base + i * 3 + j) % n
            out[day][slot] = workers_available[idx]
    return out


# --- Sonuç dataclass'ı --------------------------------------------------------

@dataclass
class GenerationResult:
    days_generated: int = 0
    assignments_created: int = 0
    assignments_preserved: int = 0
    warnings: list[str] = field(default_factory=list)


# --- Ana jeneratör ------------------------------------------------------------

def generate_month(
    db: Session,
    year: int,
    month: int,
    overwrite_manual: bool = False,
) -> GenerationResult:
    """Bir ayın vardiya çizelgesini üretir + DB'ye yazar.

    Manuel kayıtlar (modified_by_user_id NOT NULL) overwrite_manual=False
    iken korunur. True olursa hepsi silinir. FORCED_OVERRIDES her koşulda
    uygulanır (manuel/otomatik ayrımı yapmaz).
    """
    result = GenerationResult()
    cfg = get_personnel_config()

    personnel = (
        db.query(Personnel)
        .filter(Personnel.is_active.is_(True))
        .order_by(Personnel.full_name.asc())
        .all()
    )
    if not personnel:
        result.warnings.append("Personel listesi boş; önce config dosyasına ekleyin.")
        return result

    by_name = _by_name(personnel)

    fixed = [p for p in personnel if p.group == PersonnelGroup.fixed_a]
    oncall_pool_named = [by_name[n] for n in cfg.oncall_rotation if n in by_name]
    b_secondary = [by_name[n] for n in cfg.b_secondary if n in by_name]
    rotation_personnel = [by_name[n] for n in cfg.weekday_rotation if n in by_name]

    role_names = (
        set(cfg.weekday_rotation)
        | set(cfg.b_secondary)
        | set(cfg.oncall_rotation)
        | {p.full_name for p in fixed}
    )
    other_workers = [
        p for p in personnel
        if p.full_name not in role_names and not p.is_oncall_only and not p.is_fixed_a
    ]

    missing = [
        n for n in (cfg.weekday_rotation + cfg.b_secondary + cfg.oncall_rotation)
        if n not in by_name
    ]
    if missing:
        result.warnings.append(
            f"Personel master'da bulunamayan rotasyon isimleri: {len(missing)} adet "
            "— bu kişiler için atama yapılamadı."
        )

    forced_overrides = _expanded_forced_overrides()

    # Ayın mevcut atamaları
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])
    existing_q = (
        db.query(MonthlyShiftAssignment)
        .filter(MonthlyShiftAssignment.day >= first_day)
        .filter(MonthlyShiftAssignment.day <= last_day)
    )
    if overwrite_manual:
        deleted = existing_q.delete(synchronize_session=False)
        result.warnings.append(f"{deleted} mevcut atama silindi (overwrite_manual=True).")
    else:
        existing_q.filter(
            MonthlyShiftAssignment.modified_by_user_id.is_(None)
        ).delete(synchronize_session=False)
        preserved = (
            db.query(MonthlyShiftAssignment)
            .filter(MonthlyShiftAssignment.day >= first_day)
            .filter(MonthlyShiftAssignment.day <= last_day)
            .count()
        )
        result.assignments_preserved = preserved
    db.commit()

    # FORCED_OVERRIDES: mevcut kayıtları temizle
    override_person_days: set[tuple[int, date]] = set()
    for name, override_date, _slot in forced_overrides:
        if first_day <= override_date <= last_day:
            p = by_name.get(name)
            if p:
                db.query(MonthlyShiftAssignment).filter(
                    MonthlyShiftAssignment.personnel_id == p.id,
                    MonthlyShiftAssignment.day == override_date,
                ).delete(synchronize_session=False)
                override_person_days.add((p.id, override_date))
    if override_person_days:
        db.commit()

    # Manuel lock'lu (person_id, day) seti — dokunulmaz
    locked_keys: set[tuple[int, date]] = set()
    for (pid, dday) in (
        db.query(MonthlyShiftAssignment.personnel_id, MonthlyShiftAssignment.day)
        .filter(MonthlyShiftAssignment.day >= first_day)
        .filter(MonthlyShiftAssignment.day <= last_day)
        .all()
    ):
        locked_keys.add((pid, dday))

    # FORCED_OVERRIDES person-day'lerini locked_keys'e ekle → main loop skiplasın
    for (pid, dday) in override_person_days:
        locked_keys.add((pid, dday))

    # On-call override haftaları: normal rotasyon skiplenir
    weeks_with_oncall_override: set[date] = set()
    for _name, _override_date, _slot in forced_overrides:
        if _slot == MonthlyShiftSlot.oncall and first_day <= _override_date <= last_day:
            _monday = _override_date - timedelta(days=_override_date.weekday())
            weeks_with_oncall_override.add(_monday)

    weeks = _weeks_in_month(year, month)
    result.days_generated = sum(len(w) for w in weeks)

    to_add: list[MonthlyShiftAssignment] = []

    def add(p: Personnel, d: date, s: MonthlyShiftSlot) -> bool:
        if (p.id, d) in locked_keys:
            return False
        to_add.append(MonthlyShiftAssignment(personnel_id=p.id, day=d, slot=s))
        return True

    # B-secondary split — b_secondary[0] = week-start half, b_secondary[1] = week-end half
    b_sec_first = b_secondary[0] if len(b_secondary) >= 1 else None
    b_sec_second = b_secondary[1] if len(b_secondary) >= 2 else None

    for week_days in weeks:
        monday = _monday_of_week(week_days)
        week_idx = _week_index_for_monday(monday, year)

        b_first = _pick_rotating(rotation_personnel, week_idx) if rotation_personnel else None
        c_first = _pick_rotating(rotation_personnel, week_idx - 1) if rotation_personnel else None

        # B-2nd günlük dağılım — çift hafta: 3-2 (baş 3, son 2); tek hafta: 2-3
        if week_idx % 2 == 0:
            first_b_weekdays = {0, 1, 2}   # Pzt, Sal, Çar — 3 gün
            second_b_weekdays = {3, 4}     # Per, Cu       — 2 gün
        else:
            first_b_weekdays = {0, 1}      # Pzt, Sal      — 2 gün
            second_b_weekdays = {2, 3, 4}  # Çar, Per, Cu  — 3 gün

        # On-call kişisi — override haftasında normal rotasyon skiplansın
        if monday in weeks_with_oncall_override:
            oncall_person = None
        else:
            oncall_person = _pick_rotating(oncall_pool_named, week_idx) if oncall_pool_named else None

        # Hafta sonu worker havuzu
        weekend_busy_names = set()
        if b_first: weekend_busy_names.add(b_first.full_name)
        if c_first: weekend_busy_names.add(c_first.full_name)
        for p in b_secondary:
            weekend_busy_names.add(p.full_name)

        weekend_workers_pool: list[Personnel] = []
        for p in rotation_personnel:
            if p.full_name not in weekend_busy_names:
                weekend_workers_pool.append(p)
        for p in other_workers:
            if p.full_name not in weekend_busy_names:
                weekend_workers_pool.append(p)

        # %20 hafta sonu off — her 5 haftadan 1'inde havuzdan ilkini çıkar
        if weekend_workers_pool and week_idx % 5 == 0:
            weekend_workers_pool.pop(0)

        weekend_slots = _weekend_assignments_for_week(
            week_days, weekend_workers_pool, week_idx,
        )

        for day in week_days:
            is_weekend = day.weekday() >= 5

            if oncall_person:
                add(oncall_person, day, MonthlyShiftSlot.oncall)

            if not is_weekend:
                for p in fixed:
                    add(p, day, MonthlyShiftSlot.a_fixed)

                if b_first:
                    add(b_first, day, MonthlyShiftSlot.b_shift)

                wd = day.weekday()
                if b_sec_first and wd in first_b_weekdays:
                    add(b_sec_first, day, MonthlyShiftSlot.b_shift)
                elif b_sec_first:
                    slot = (MonthlyShiftSlot.a_istanbul
                            if b_sec_first.location.value == "istanbul"
                            else MonthlyShiftSlot.a_ankara)
                    add(b_sec_first, day, slot)
                if b_sec_second and wd in second_b_weekdays:
                    add(b_sec_second, day, MonthlyShiftSlot.b_shift)
                elif b_sec_second:
                    slot = (MonthlyShiftSlot.a_istanbul
                            if b_sec_second.location.value == "istanbul"
                            else MonthlyShiftSlot.a_ankara)
                    add(b_sec_second, day, slot)

                if c_first:
                    add(c_first, day, MonthlyShiftSlot.c_shift)

                already_assigned_today = {
                    a.personnel_id for a in to_add if a.day == day
                }
                for p in rotation_personnel:
                    if p.id in already_assigned_today:
                        continue
                    slot = (MonthlyShiftSlot.a_istanbul if p.location.value == "istanbul"
                            else MonthlyShiftSlot.a_ankara)
                    add(p, day, slot)
                for p in other_workers:
                    if p.id in already_assigned_today:
                        continue
                    slot = (MonthlyShiftSlot.a_istanbul if p.location.value == "istanbul"
                            else MonthlyShiftSlot.a_ankara)
                    add(p, day, slot)
                # On-call only kişiler on-call değilse kendi lokasyon A'sında
                for p in oncall_pool_named:
                    if p.id in already_assigned_today:
                        continue
                    slot = (MonthlyShiftSlot.a_istanbul if p.location.value == "istanbul"
                            else MonthlyShiftSlot.a_ankara)
                    add(p, day, slot)
            else:
                slots_for_day = weekend_slots.get(day, {})
                for slot, person in slots_for_day.items():
                    add(person, day, slot)

    # FORCED_OVERRIDES uygula — locked_keys sayesinde main loop atlamıştı
    for name, override_date, slot in forced_overrides:
        if not (first_day <= override_date <= last_day):
            continue
        p = by_name.get(name)
        if not p:
            result.warnings.append(
                "FORCED_OVERRIDE atlandı: personel master'da yok."
            )
            continue
        to_add.append(MonthlyShiftAssignment(
            personnel_id=p.id,
            day=override_date,
            slot=slot,
            note="Sabit override",
        ))

    # --- v0.9.1: Pazar C vardiyası → sonraki Pazartesi zorunlu off ---
    # Hafta sonu Pazar günü C vardiyasında olan kişi bir sonraki Pazartesi
    # HİÇBİR slotta olamaz. Otomatik olarak `off` atanır. Cross-week (aynı ay
    # içi) ve cross-month (önceki aydan gelen bloklama) desteklenir.
    # Manuel-lock veya FORCED_OVERRIDE zaten varsa dokunulmaz.
    sunday_c_next_monday: list[tuple[int, date]] = []

    # (a) Aynı ay içinde: to_add'daki Pazar C atamalarından sonraki Pzt
    for a in to_add:
        if a.day.weekday() == 6 and a.slot == MonthlyShiftSlot.c_shift:
            next_mon = a.day + timedelta(days=1)
            if first_day <= next_mon <= last_day:
                sunday_c_next_monday.append((a.personnel_id, next_mon))

    # (b) Cross-month: ay Pazartesi ile başlıyorsa önceki Pazar'ı DB'den çek
    if first_day.weekday() == 0:
        prev_sunday = first_day - timedelta(days=1)
        prev_c_rows = (
            db.query(MonthlyShiftAssignment)
            .filter(MonthlyShiftAssignment.day == prev_sunday)
            .filter(MonthlyShiftAssignment.slot == MonthlyShiftSlot.c_shift)
            .all()
        )
        for row in prev_c_rows:
            sunday_c_next_monday.append((row.personnel_id, first_day))

    # Uygula: mevcut Monday atamalarını temizle + off ekle + lock'la
    for pid, mon in sunday_c_next_monday:
        if (pid, mon) in locked_keys:
            # Manuel lock ya da FORCED_OVERRIDE var — saygı göster
            continue
        # Bu (person, day) için mevcut to_add kayıtlarını çıkar
        to_add[:] = [
            a for a in to_add
            if not (a.personnel_id == pid and a.day == mon)
        ]
        # Zorunlu off ekle
        to_add.append(MonthlyShiftAssignment(
            personnel_id=pid,
            day=mon,
            slot=MonthlyShiftSlot.off,
            note="Pazar C sonrası zorunlu off",
        ))
        locked_keys.add((pid, mon))

    # Boş hücrelere off yaz
    person_days: dict[int, set[date]] = {}
    for a in to_add:
        person_days.setdefault(a.personnel_id, set()).add(a.day)
    for (pid, dday) in locked_keys:
        person_days.setdefault(pid, set()).add(dday)

    all_month_days: list[date] = []
    for week_days in weeks:
        all_month_days.extend(week_days)

    for p in personnel:
        for day in all_month_days:
            if (p.id, day) in locked_keys:
                continue
            if day in person_days.get(p.id, set()):
                continue
            to_add.append(MonthlyShiftAssignment(
                personnel_id=p.id, day=day, slot=MonthlyShiftSlot.off,
            ))

    db.bulk_save_objects(to_add)
    db.commit()
    result.assignments_created = len(to_add)
    return result
