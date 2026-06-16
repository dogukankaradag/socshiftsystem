"""Dağıtıcı + Öğlen Nöbetçi günlük atama jeneratörü (v0.8.3).

Kullanıcı tarifindeki kurallar:

  - Sadece hafta içi (Pzt-Cu) günler — hafta sonu atama yok.
  - Aylık Vardiya verileriyle entegre: bir kişi o gün B/C/on-call/leave/off
    slot'larında DEĞİLSE havuza dahil.
  - **Sadece Rıdvan ve Fatih hariç** — kalan TÜM aktif personel havuzda
    (Sabri/Yağız/Ülkü/Zehra dahil — on-call olmadıkları günlerde).
  - Gün başına **2 Dağıtıcı + 2 Öğlen Nöbet** = toplam 4 farklı kişi.
  - Dağıtıcı: lokasyon kısıtsız (Ankara veya İstanbul, karışık olabilir).
  - **Öğlen: 2 kişi aynı lokasyondan** (Ank-Ank veya İst-İst).
  - Hedef: her aktif personele ay başına ≥2 dağıtıcı + ≥2 öğlen.
  - Algoritma: greedy round-robin — en az atama almış kişiyi öncelikle seç.
  - Manuel müdahale (`modified_by_user_id IS NOT NULL`) korunur.

Bir gün için 4 atama: 2 dağıtıcı + 2 öğlen. Aynı kişi aynı gün × görev türü
içinde tekrar atanamaz (unique index). Aynı kişi aynı gün hem dağıtıcı hem
öğlen olabilir mi? Hayır — adalet için aynı günde her kişi tek rol alır.
"""
from __future__ import annotations
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy.orm import Session

from .models import (
    DailyDuty, DailyDutyType, MonthlyShiftAssignment, MonthlyShiftSlot,
    Personnel, PersonnelLocation,
)


# Bu kişiler dağıtıcı / öğlen nöbetine girmez (kullanıcı kararı).
EXCLUDED_NAMES: set[str] = {"Rıdvan", "Fatih"}

# v0.8.11: O gün bir kişiyi dağıtıcı/öğlen yapmaktan ALIKOYAN slot'lar.
# On-call PASİF (standby) bir durum — aktif olarak çağırılana kadar çalışır.
# Bu nedenle on-call kişiler aynı gün dist/öğlen alabilir (kullanıcı veri
# örneklerinde Yağız ve Zehra'nın on-call rotasyonu üyeleriyken dist
# yaptığını gösterdi).
BLOCKING_SLOTS = {
    MonthlyShiftSlot.b_shift,
    MonthlyShiftSlot.c_shift,
    MonthlyShiftSlot.leave,
    MonthlyShiftSlot.off,
}

# v0.8.4: Cuma günleri öğlen nöbeti için ÖZEL havuz — sadece bu kişilerden
# biri seçilebilir. Geri kalan günlerde (Pzt-Per) normal havuz kullanılır.
FRIDAY_LUNCH_POOL: set[str] = {"Yağız", "Sabri", "Ülkü", "Zehra"}


# v0.8.10: Haftalık öğlen lokasyon kalıbı — kullanıcı tarifine göre:
#   "Hafta içi 3 gün Ankara, 2 gün İstanbul; sonraki hafta tersi 2/3"
#
# Anchor: ROTATION_ANCHOR_MONDAY (2026-06-01, Pzt). Bu pazartesiyi haftanın
# 0. günü kabul ediyoruz. 8 Haziran haftası (week_idx 1, tek hafta) "3 Ank +
# 2 İst" olacak (kullanıcının doğrudan verdiği örnek).
#
#   Çift hafta (week_idx 0, 2, ...): 2 Ank + 3 İst → Pzt İst, Sa Ank, Çr İst,
#                                                   Pe Ank, Cu İst
#   Tek hafta  (week_idx 1, 3, ...): 3 Ank + 2 İst → Pzt Ank, Sa İst, Çr Ank,
#                                                   Pe İst, Cu Ank
#
# Cuma lokasyonu Friday-special-pool'dan kim seçileceğini de belirler
# (Ank → Ülkü/Zehra, İst → Yağız/Sabri).
from .monthly_shift_generator import ROTATION_ANCHOR_MONDAY

# v0.8.11: Kullanıcı verisinden çıkardığım gerçek pattern:
#   Her hafta 3 Ank + 2 İst (alternation Mon-Thu, Fri her zaman Ank).
#   - Çift hafta (1-5 Haz): Mon İst, Tue Ank, Wed İst, Thu Ank, Fri Ank
#   - Tek hafta  (8-12 Haz): Mon Ank, Tue İst, Wed Ank, Thu İst, Fri Ank
# Cuma her zaman Ank (Ülkü veya Zehra special pool'dan).
WEEKDAY_LUNCH_LOC_EVEN: dict[int, str] = {
    0: "istanbul", 1: "ankara", 2: "istanbul", 3: "ankara", 4: "ankara",
}
WEEKDAY_LUNCH_LOC_ODD: dict[int, str] = {
    0: "ankara", 1: "istanbul", 2: "ankara", 3: "istanbul", 4: "ankara",
}


def _lunch_target_location(day: date) -> str:
    """Bu güne hangi lokasyonun öğlen nöbeti düşüyor?"""
    monday = day - timedelta(days=day.weekday())
    week_idx = (monday - ROTATION_ANCHOR_MONDAY).days // 7
    pattern = WEEKDAY_LUNCH_LOC_ODD if week_idx % 2 == 1 else WEEKDAY_LUNCH_LOC_EVEN
    return pattern[day.weekday()]


def _week_key(day: date) -> tuple[int, int]:
    """ISO yıl/hafta — haftalık state için key."""
    iso = day.isocalendar()
    return (iso[0], iso[1])


@dataclass
class DailyDutyGenerationResult:
    weekdays_generated: int = 0
    assignments_created: int = 0
    assignments_preserved: int = 0
    per_person_distributor: dict[str, int] = field(default_factory=dict)
    per_person_lunch: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _weekdays_in_month(year: int, month: int) -> list[date]:
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    out: list[date] = []
    d = first
    while d <= last:
        if d.weekday() < 5:  # Pzt-Cu
            out.append(d)
        d += timedelta(days=1)
    return out


def _pick_lowest(eligible_ids: list[int],
                 counts: dict[int, int],
                 name_by_id: dict[int, str]) -> int | None:
    """En az atama almış kişiyi seç (alfabetik tie-break)."""
    if not eligible_ids:
        return None
    return sorted(
        eligible_ids,
        key=lambda pid: (counts.get(pid, 0), name_by_id[pid]),
    )[0]


def _pick_lunch_pair(eligible_ids: list[int],
                     loc_by_id: dict[int, PersonnelLocation],
                     counts_lunch: dict[int, int],
                     name_by_id: dict[int, str]) -> tuple[int | None, int | None]:
    """Aynı lokasyondan 2 öğlen nöbetçisi seç (counts düşük + alfabetik).

    Strateji: önce en az atama almış kişiyi seç. Onun lokasyonu sabit.
    Sonra aynı lokasyondan ikinci en az atamalı kişiyi seç. Eğer aynı
    lokasyonda 2. kişi yoksa (ör. o gün tüm Ank'lar meşgul), 1. kişiyi
    farklı lokasyondan dene. Hâlâ olmazsa tek kişi atama yapılır.
    """
    if not eligible_ids:
        return (None, None)

    # Strateji A: counts_lunch sıralamasına göre git
    sorted_by_count = sorted(
        eligible_ids,
        key=lambda pid: (counts_lunch.get(pid, 0), name_by_id[pid]),
    )

    # En öncelikli kişiyi pick et
    first = sorted_by_count[0]
    first_loc = loc_by_id[first]

    # Aynı lokasyondan ikinci kişi
    same_loc = [pid for pid in sorted_by_count[1:] if loc_by_id[pid] == first_loc]
    if same_loc:
        return (first, same_loc[0])

    # Aynı lokasyonda 2. kişi yok → birinci kişiyi diğer lokasyondan deniyelim
    # (aynı lokasyonda 2 kişi bulmak için).
    other_loc = (PersonnelLocation.istanbul
                 if first_loc == PersonnelLocation.ankara
                 else PersonnelLocation.ankara)
    other_pool = [pid for pid in sorted_by_count if loc_by_id[pid] == other_loc]
    if len(other_pool) >= 2:
        # Diğer lokasyondan 2 kişi var → onları seç (counts düşük olanlar)
        return (other_pool[0], other_pool[1])

    # Hiçbir lokasyondan 2 kişi bulamadık → sadece first'i atama
    return (first, None)


def generate_month(
    db: Session,
    year: int,
    month: int,
    overwrite_manual: bool = False,
) -> DailyDutyGenerationResult:
    """Bir ayın dağıtıcı + öğlen nöbet çizelgesini üretir + DB'ye yazar."""
    result = DailyDutyGenerationResult()

    weekdays = _weekdays_in_month(year, month)
    result.weekdays_generated = len(weekdays)
    if not weekdays:
        return result

    # 1) Mevcut atamaları sil (manuel olanları koru veya sil).
    first_day = weekdays[0]
    last_day = date(year, month, monthrange(year, month)[1])

    existing_q = (
        db.query(DailyDuty)
        .filter(DailyDuty.day >= first_day)
        .filter(DailyDuty.day <= last_day)
    )
    if overwrite_manual:
        deleted = existing_q.delete(synchronize_session=False)
        result.warnings.append(f"{deleted} mevcut atama silindi (overwrite_manual=True).")
    else:
        existing_q.filter(DailyDuty.modified_by_user_id.is_(None)).delete(
            synchronize_session=False,
        )
        result.assignments_preserved = (
            db.query(DailyDuty)
            .filter(DailyDuty.day >= first_day)
            .filter(DailyDuty.day <= last_day)
            .count()
        )
    db.commit()

    # 2) Aktif eligible personel havuzu (Rıdvan/Fatih hariç).
    personnel = (
        db.query(Personnel)
        .filter(Personnel.is_active.is_(True))
        .filter(~Personnel.full_name.in_(EXCLUDED_NAMES))
        .order_by(Personnel.full_name.asc())
        .all()
    )
    if not personnel:
        result.warnings.append("Eligible personel bulunamadı; önce Personnel master'a ekleyin.")
        return result

    name_by_id = {p.id: p.full_name for p in personnel}
    loc_by_id = {p.id: p.location for p in personnel}

    # 3) Aylık Vardiya'dan blocking slot'larını çek.
    msa_rows = (
        db.query(MonthlyShiftAssignment)
        .filter(MonthlyShiftAssignment.day >= first_day)
        .filter(MonthlyShiftAssignment.day <= last_day)
        .all()
    )
    busy_by_day: dict[date, set[int]] = {}
    for r in msa_rows:
        if r.slot in BLOCKING_SLOTS:
            busy_by_day.setdefault(r.day, set()).add(r.personnel_id)

    if not msa_rows:
        result.warnings.append(
            "Aylık Vardiya verisi yok. Önce 'Aylık Vardiya Listesi' sayfasında "
            "ilgili ayın çizelgesini Otomatik Üret yapın — şimdilik tüm personel "
            "havuzda kabul ediliyor."
        )

    # 4) Counter'lar (manuel korunan atamalar dahil)
    counts_dist: dict[int, int] = {p.id: 0 for p in personnel}
    counts_lunch: dict[int, int] = {p.id: 0 for p in personnel}
    for d in db.query(DailyDuty).filter(
        DailyDuty.day >= first_day, DailyDuty.day <= last_day,
    ).all():
        if d.duty_type == DailyDutyType.distributor:
            counts_dist[d.personnel_id] = counts_dist.get(d.personnel_id, 0) + 1
        else:
            counts_lunch[d.personnel_id] = counts_lunch.get(d.personnel_id, 0) + 1

    # 5) Manuel lock'lu (day, duty_type, personnel_id) çiftleri — yeniden yazma
    locked_combos: set[tuple[date, DailyDutyType, int]] = set()
    # Slot başına "kaç manuel atama var" sayacı (≥2 ise yeni atama yapmayız)
    manual_count_by_slot: dict[tuple[date, DailyDutyType], int] = {}
    for d, t, pid in (
        db.query(DailyDuty.day, DailyDuty.duty_type, DailyDuty.personnel_id)
        .filter(DailyDuty.day >= first_day)
        .filter(DailyDuty.day <= last_day)
        .all()
    ):
        locked_combos.add((d, t, pid))
        manual_count_by_slot[(d, t)] = manual_count_by_slot.get((d, t), 0) + 1

    to_add: list[DailyDuty] = []

    # v0.8.10+v0.8.12: Haftalık state — bir kişi haftada en fazla
    # 1 dist VE 1 lunch alabilir. Mevcut manuel kayıtlar bu set'lere
    # başlangıçta dahil edilerek "max 1/hafta" kuralı bozulmaz.
    weekly_lunch_used: dict[tuple[int, int], set[int]] = {}
    weekly_dist_used: dict[tuple[int, int], set[int]] = {}
    for d in db.query(DailyDuty).filter(
        DailyDuty.day >= first_day,
        DailyDuty.day <= last_day,
    ).all():
        wk = _week_key(d.day)
        if d.duty_type == DailyDutyType.lunch:
            weekly_lunch_used.setdefault(wk, set()).add(d.personnel_id)
        else:
            weekly_dist_used.setdefault(wk, set()).add(d.personnel_id)

    for day in weekdays:
        blocked_today = busy_by_day.get(day, set())
        eligible_ids = [p.id for p in personnel if p.id not in blocked_today]
        if not eligible_ids:
            result.warnings.append(f"{day}: eligible kişi yok, atlandı.")
            continue

        # Bu gün manuel olarak atanan kişileri "aynı gün başka role atama"
        # adaletsizliğinden korumak için takip et.
        assigned_today: set[int] = set()
        for (d, t, pid) in locked_combos:
            if d == day:
                assigned_today.add(pid)

        # --- DAĞITICI (v0.8.12: 1 İst + 1 Ank, haftada max 1/kişi) ---
        dist_slot = (day, DailyDutyType.distributor)
        dist_existing = manual_count_by_slot.get(dist_slot, 0)

        wk = _week_key(day)
        dist_used_this_week = weekly_dist_used.setdefault(wk, set())

        # Eligible: bloklu değil + bugün başka role atanmamış + bu hafta
        # dist olmamış
        dist_eligible = [
            pid for pid in eligible_ids
            if pid not in assigned_today
            and pid not in dist_used_this_week
        ]
        dist_ist = [pid for pid in dist_eligible
                    if loc_by_id[pid].value == "istanbul"]
        dist_ank = [pid for pid in dist_eligible
                    if loc_by_id[pid].value == "ankara"]

        if dist_existing < 2:
            # İstanbul tarafı 1 kişi
            chosen_ist = _pick_lowest(dist_ist, counts_dist, name_by_id)
            if chosen_ist:
                to_add.append(DailyDuty(
                    day=day, duty_type=DailyDutyType.distributor,
                    personnel_id=chosen_ist,
                ))
                counts_dist[chosen_ist] += 1
                assigned_today.add(chosen_ist)
                dist_used_this_week.add(chosen_ist)
            else:
                result.warnings.append(
                    f"{day}: dist için İstanbul tarafından eligible kişi yok "
                    "(bu hafta hepsi kullanılmış veya hepsi B/C/izinli)."
                )
            # Ankara tarafı 1 kişi
            dist_ank = [pid for pid in dist_ank
                        if pid not in assigned_today
                        and pid not in dist_used_this_week]
            chosen_ank = _pick_lowest(dist_ank, counts_dist, name_by_id)
            if chosen_ank:
                to_add.append(DailyDuty(
                    day=day, duty_type=DailyDutyType.distributor,
                    personnel_id=chosen_ank,
                ))
                counts_dist[chosen_ank] += 1
                assigned_today.add(chosen_ank)
                dist_used_this_week.add(chosen_ank)
            else:
                result.warnings.append(
                    f"{day}: dist için Ankara tarafından eligible kişi yok "
                    "(bu hafta hepsi kullanılmış veya hepsi B/C/izinli)."
                )

        # --- ÖĞLEN (v0.8.10 algoritması) ---
        # Yeni 3 kural:
        #   (1) Cuma: 1 kişi (FRIDAY_LUNCH_POOL ∩ haftaya düşen lokasyon)
        #   (2) Pzt-Per: 2 kişi (haftaya düşen günlük lokasyon)
        #   (3) Bir kişi haftada sadece 1 kez öğlen olabilir (no-repeat-week)
        #   Mevcut: aynı kişi aynı gün dağıtıcı + öğlen olamaz (assigned_today)
        is_friday = day.weekday() == 4
        lunch_slot = (day, DailyDutyType.lunch)
        lunch_existing = manual_count_by_slot.get(lunch_slot, 0)

        # Bu güne düşen lokasyon (haftalık 3 Ank / 2 İst veya 2/3 deseni)
        target_loc_str = _lunch_target_location(day)  # 'ankara' | 'istanbul'

        week_key = _week_key(day)
        used_this_week = weekly_lunch_used.setdefault(week_key, set())

        # Eligible: bloklu değil + bugün dağıtıcı değil + bu hafta öğlen olmamış
        lunch_eligible = [
            pid for pid in eligible_ids
            if pid not in assigned_today and pid not in used_this_week
        ]
        # Lokasyon filtresi
        lunch_eligible_loc = [
            pid for pid in lunch_eligible
            if loc_by_id[pid].value == target_loc_str
        ]

        if is_friday:
            # Cuma: 1 kişi, FRIDAY_LUNCH_POOL ∩ target_loc
            if lunch_existing == 0:
                special_eligible = [
                    pid for pid in lunch_eligible_loc
                    if name_by_id[pid] in FRIDAY_LUNCH_POOL
                ]
                # Special pool ve target_loc uyuşmuyorsa (örn. tüm Ank özel
                # pool kişileri kullanılmış), pool'u esnet — sadece pool kalsın
                if not special_eligible:
                    special_eligible = [
                        pid for pid in lunch_eligible
                        if name_by_id[pid] in FRIDAY_LUNCH_POOL
                    ]
                if not special_eligible:
                    result.warnings.append(
                        f"{day} (Cuma): öğlen için {sorted(FRIDAY_LUNCH_POOL)} "
                        "havuzundan eligible kişi yok (bu hafta zaten kullanılmış "
                        "veya hepsi on-call/leave)."
                    )
                else:
                    chosen = _pick_lowest(special_eligible, counts_lunch, name_by_id)
                    if chosen:
                        to_add.append(DailyDuty(
                            day=day, duty_type=DailyDutyType.lunch,
                            personnel_id=chosen,
                        ))
                        counts_lunch[chosen] += 1
                        assigned_today.add(chosen)
                        used_this_week.add(chosen)
            # lunch_existing >= 1: zaten dolu
        else:
            # Pzt-Per: 2 kişi, target_loc'tan, haftada tekrarsız.
            # v0.8.11: Special pool (Yağız/Sabri/Ülkü/Zehra) Mon-Thu lunch'a
            # dahil edilmez — sadece Cuma için ayrılmıştır.
            if lunch_existing == 0:
                lunch_eligible_loc_regular = [
                    pid for pid in lunch_eligible_loc
                    if name_by_id[pid] not in FRIDAY_LUNCH_POOL
                ]
                if len(lunch_eligible_loc_regular) < 2:
                    result.warnings.append(
                        f"{day}: öğlen için {target_loc_str.title()} "
                        f"regular havuzunda yeterli (≥2) eligible kişi yok "
                        f"(bulunan: {len(lunch_eligible_loc_regular)}). "
                        "Bu hafta zaten kullanılmış olabilir."
                    )
                # En az atama almış 2 kişi
                picked: list[int] = []
                remaining = list(lunch_eligible_loc_regular)
                for _ in range(2):
                    if not remaining:
                        break
                    chosen = _pick_lowest(remaining, counts_lunch, name_by_id)
                    if chosen is None:
                        break
                    picked.append(chosen)
                    remaining = [pid for pid in remaining if pid != chosen]
                for pid in picked:
                    to_add.append(DailyDuty(
                        day=day, duty_type=DailyDutyType.lunch, personnel_id=pid,
                    ))
                    counts_lunch[pid] += 1
                    assigned_today.add(pid)
                    used_this_week.add(pid)
            elif lunch_existing == 1:
                # 1 manuel kişi var → 2.'yi aynı lokasyondan (manuel kişinin lokasyonu) bul
                existing_lunch = db.query(DailyDuty).filter(
                    DailyDuty.day == day,
                    DailyDuty.duty_type == DailyDutyType.lunch,
                ).first()
                if existing_lunch:
                    existing_loc = loc_by_id.get(existing_lunch.personnel_id)
                    target_loc_val = (existing_loc.value if existing_loc
                                       else target_loc_str)
                    pool = [pid for pid in lunch_eligible
                            if loc_by_id[pid].value == target_loc_val]
                    if pool:
                        chosen = _pick_lowest(pool, counts_lunch, name_by_id)
                        if chosen:
                            to_add.append(DailyDuty(
                                day=day, duty_type=DailyDutyType.lunch,
                                personnel_id=chosen,
                            ))
                            counts_lunch[chosen] += 1
                            assigned_today.add(chosen)
                            used_this_week.add(chosen)
                    else:
                        result.warnings.append(
                            f"{day}: öğlen 2. kişi için aynı lokasyon "
                            f"({target_loc_val}) havuzda yok; atanmadı."
                        )
            # lunch_existing >= 2: zaten dolu

    db.bulk_save_objects(to_add)
    db.commit()
    result.assignments_created = len(to_add)
    result.per_person_distributor = {
        name_by_id[pid]: c for pid, c in counts_dist.items() if pid in name_by_id
    }
    result.per_person_lunch = {
        name_by_id[pid]: c for pid, c in counts_lunch.items() if pid in name_by_id
    }

    low_dist = [n for n, c in result.per_person_distributor.items() if c < 2]
    low_lunch = [n for n, c in result.per_person_lunch.items() if c < 2]
    if low_dist:
        result.warnings.append(
            f"Hedef olan ≥2 dağıtıcı atamasına ulaşamadı: {', '.join(low_dist)}."
        )
    if low_lunch:
        result.warnings.append(
            f"Hedef olan ≥2 öğlen atamasına ulaşamadı: {', '.join(low_lunch)}."
        )

    return result
