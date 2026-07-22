"""Dağıtıcı + Öğlen Nöbetçi günlük atama jeneratörü.

İş kuralları (yapılandırma ile parametrize):

  - Sadece hafta içi (Pzt-Cu) günler — hafta sonu atama yok.
  - Aylık Vardiya verileriyle entegre: bir kişi o gün B/C/leave/off slot'larında
    DEĞİLSE havuza dahil. On-call PASİF (standby) — aynı gün dist/öğlen olabilir.
  - `excluded_from_daily_duty` config listesindeki kişiler havuza girmez.
  - Gün başına 2 Dağıtıcı + 2 Öğlen Nöbet = 4 farklı kişi.
  - Dağıtıcı: 1 İstanbul + 1 Ankara. Öğlen (Pzt-Per): 2 kişi aynı lokasyondan.
  - Cuma öğlen: 2 kişi, `friday_lunch_pool` config listesinden (lokasyon
    bağımsız). Pair kısıtı (Ankara + on-call-only ikilisi) uygulanır.
  - Kişi başı hedef ay içinde ≥2 dağıtıcı + ≥2 öğlen; haftada max 1 dist +
    1 öğlen (no-repeat-week).
  - Öğlen çift kısıtı: aynı gün iki on-call-only Ankara personeli
    eşleşemez (yük dengeleme).
  - Algoritma: greedy round-robin — en az atama almış kişiyi öncelikle seç.
  - Manuel müdahale (modified_by_user_id NOT NULL) korunur — AMA Aylık
    Vardiya'da o gün leave/off/B/C alan kişi için mevcut manuel/otomatik
    dist/lunch kaydı otomatik silinir (çakışma temizliği, v0.9.3).
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
from .personnel_config import get_personnel_config


# O gün bir kişiyi dağıtıcı/öğlen yapmaktan ALIKOYAN slot'lar.
# On-call PASİF (standby) durum — aktif olarak çağırılana kadar çalışır;
# bu nedenle on-call kişiler aynı gün dist/öğlen alabilir.
BLOCKING_SLOTS = {
    MonthlyShiftSlot.b_shift,
    MonthlyShiftSlot.c_shift,
    MonthlyShiftSlot.leave,
    MonthlyShiftSlot.off,
}


def _excluded_names() -> set[str]:
    return set(get_personnel_config().excluded_from_daily_duty)


def _friday_lunch_pool() -> set[str]:
    return set(get_personnel_config().friday_lunch_pool)


# Öğlen çifti yasak kuralı — isim değil nitelik bazlı:
#   is_oncall_only=True olan iki Ankara personeli aynı gün öğlen olamaz.
# Yük dengeleme amacıyla o güne ait 2. kişi Ankara'nın diğer (vardiyaya giren)
# personelinden seçilir. Yeni kurallar için bu fonksiyona OR ile eklenir.


def _pair_allowed(p_a: Personnel, p_b: Personnel) -> bool:
    """İki kişinin aynı gün öğlen çiftinde birlikte olması mümkün mü?"""
    if p_a.location != p_b.location:
        return True
    if p_a.location != PersonnelLocation.ankara:
        return True
    if p_a.is_oncall_only and p_b.is_oncall_only:
        return False
    return True


# Haftalık öğlen lokasyon kalıbı — her hafta 3 Ank + 2 İst (alternation Mon-Thu,
# Fri her zaman Ank). Çift/tek hafta desenleri config anchor'dan hesaplanır.
from .monthly_shift_generator import ROTATION_ANCHOR_MONDAY
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

    # 2) Aktif eligible personel havuzu (excluded_from_daily_duty listesi hariç).
    personnel = (
        db.query(Personnel)
        .filter(Personnel.is_active.is_(True))
        .filter(~Personnel.full_name.in_(_excluded_names()))
        .order_by(Personnel.full_name.asc())
        .all()
    )
    if not personnel:
        result.warnings.append("Eligible personel bulunamadı; önce Personnel master'a ekleyin.")
        return result

    name_by_id = {p.id: p.full_name for p in personnel}
    loc_by_id = {p.id: p.location for p in personnel}
    # v0.8.19: Personnel objelerinin id-index'i — _pair_allowed niteliklere
    # (location, is_oncall_only) baktığı için tam objeye erişim gerekiyor.
    person_by_id: dict[int, Personnel] = {p.id: p for p in personnel}

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

    # v0.9.3: Aylık Vardiya çakışması temizliği.
    # Aylık Vardiya'da o gün BLOCKING slotta (leave/off/B/C) olan bir kişi
    # Dağıtıcı Listesi'nde aynı günde dist/lunch olarak duruyorsa (manuel
    # dahil) kayıt burada silinir. Böylece kullanıcı Aylık Vardiya'ya izin
    # girip Dağıtıcı'da "Otomatik Üret" bastığında çakışma sürmez —
    # algoritma o boşluğu başka bir uygun kişiyle doldurur.
    if busy_by_day:
        conflicts = (
            db.query(DailyDuty)
            .filter(DailyDuty.day >= first_day)
            .filter(DailyDuty.day <= last_day)
            .all()
        )
        conflict_deleted = 0
        for d in conflicts:
            blocked_ids = busy_by_day.get(d.day, set())
            if d.personnel_id in blocked_ids:
                db.delete(d)
                conflict_deleted += 1
        if conflict_deleted:
            db.commit()
            result.warnings.append(
                f"Aylık Vardiya çakışması: {conflict_deleted} dist/lunch kaydı "
                "silindi (izin/off/B/C olan kişi-günleri). Boşluklar yeniden "
                "atandı."
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

        # --- ÖĞLEN ---
        # Kurallar:
        #   (1) Cuma: 1 kişi (friday_lunch_pool config listesinden)
        #   (2) Pzt-Per: 2 kişi (haftaya düşen günlük lokasyon)
        #   (3) Bir kişi haftada sadece 1 kez öğlen olabilir (no-repeat-week)
        #   (4) Aynı kişi aynı gün hem dağıtıcı hem öğlen olamaz
        #   (5) Ankara + on-call-only çift kısıtı (_pair_allowed)
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
            # v0.9.2: Cuma → 2 kişi, friday_lunch_pool tamamından (lokasyon
            # bağımsız). Pair kısıtı (Ankara + on-call-only ikilisi olamaz)
            # uygulanır — pratikte bu, Ülkü/Zehra tarzı iki Ank on-call
            # kişinin aynı Cuma öğlen çiftinde olmamasını sağlar.
            needed = 2 - lunch_existing
            if needed > 0:
                friday_pool = _friday_lunch_pool()
                special_eligible = [
                    pid for pid in lunch_eligible
                    if name_by_id[pid] in friday_pool
                ]
                # lunch_existing == 1 ise mevcut manuel kişiyi pair kontrolüne
                # dahil et.
                existing_pids_today: list[int] = []
                if lunch_existing >= 1:
                    existing_rows = (
                        db.query(DailyDuty)
                        .filter(DailyDuty.day == day)
                        .filter(DailyDuty.duty_type == DailyDutyType.lunch)
                        .all()
                    )
                    existing_pids_today = [e.personnel_id for e in existing_rows]

                if len(special_eligible) < needed and needed > 1:
                    result.warnings.append(
                        f"{day} (Cuma): öğlen için friday_lunch_pool "
                        f"havuzunda yeterli eligible kişi yok "
                        f"(bulunan: {len(special_eligible)}, gereken: {needed})."
                    )

                picked_friday: list[int] = []
                remaining_friday = list(special_eligible)
                while len(picked_friday) < needed:
                    if not remaining_friday:
                        break
                    all_partners = existing_pids_today + picked_friday
                    eligible_now = [
                        pid for pid in remaining_friday
                        if pid in person_by_id
                        and all(
                            partner in person_by_id
                            and _pair_allowed(person_by_id[pid], person_by_id[partner])
                            for partner in all_partners
                        )
                    ]
                    if not eligible_now:
                        if all_partners:
                            result.warnings.append(
                                f"{day} (Cuma): öğlen için yasak çift kısıtı "
                                "(Ankara + on-call-only eşleşmesi) nedeniyle "
                                "friday_lunch_pool'da aday kalmadı."
                            )
                        break
                    chosen = _pick_lowest(eligible_now, counts_lunch, name_by_id)
                    if chosen is None:
                        break
                    picked_friday.append(chosen)
                    remaining_friday = [pid for pid in remaining_friday if pid != chosen]

                for pid in picked_friday:
                    to_add.append(DailyDuty(
                        day=day, duty_type=DailyDutyType.lunch,
                        personnel_id=pid,
                    ))
                    counts_lunch[pid] += 1
                    assigned_today.add(pid)
                    used_this_week.add(pid)
            # lunch_existing >= 2: zaten dolu
        else:
            # v0.8.15: Pzt-Per → 2 kişi, target_loc'tan, haftada tekrarsız.
            # friday_lunch_pool üyeleri de havuza DAHİL — böylece hepsi
            # ay boyunca adilce rotasyona girer.
            if lunch_existing == 0:
                if len(lunch_eligible_loc) < 2:
                    result.warnings.append(
                        f"{day}: öğlen için {target_loc_str.title()} "
                        f"havuzunda yeterli (≥2) eligible kişi yok "
                        f"(bulunan: {len(lunch_eligible_loc)}). "
                        "Bu hafta zaten kullanılmış olabilir."
                    )
                # En az atama almış 2 kişi (v0.8.19: yasak çift kısıtıyla)
                picked: list[int] = []
                remaining = list(lunch_eligible_loc)
                for _ in range(2):
                    if not remaining:
                        break
                    # Daha önce seçilen kişi(ler)le pair kuralı (_pair_allowed)
                    # ihlali yapmayan adayları filtrele.
                    eligible_now = [
                        pid for pid in remaining
                        if all(
                            _pair_allowed(person_by_id[pid], person_by_id[p])
                            for p in picked
                        )
                    ]
                    if not eligible_now:
                        if picked:
                            result.warnings.append(
                                f"{day}: öğlen 2. kişi için yasak çift kısıtı "
                                "(Ankara + on-call-only özelliği eşleşmesi) "
                                "nedeniyle havuzda aday kalmadı."
                            )
                        break
                    chosen = _pick_lowest(eligible_now, counts_lunch, name_by_id)
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
                    # v0.8.19: mevcut manuel kişiyle LUNCH_FORBIDDEN_PAIRS
                    # ihlali yapan adayları filtrele.
                    pool = [
                        pid for pid in lunch_eligible
                        if loc_by_id[pid].value == target_loc_val
                        and pid in person_by_id
                        and existing_lunch.personnel_id in person_by_id
                        and _pair_allowed(
                            person_by_id[pid],
                            person_by_id[existing_lunch.personnel_id],
                        )
                    ]
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
