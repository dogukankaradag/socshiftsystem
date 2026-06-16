"""Aylık vardiya çizelgesi otomatik jeneratörü (v0.7.3 — kullanıcı tarifi).

Kullanıcının verdiği iş kuralları:

  ROTASYON LİSTESİ (Hafta içi B/C 1. personel):
    Talha → Doğukan → İrfan → Burak → Enes → Kübra → Hasan → Mehmet → Beyza
    Bu kişi 1 hafta B-1st, bir sonraki hafta C-1st olarak çalışır
    (toplam 2 hafta vardiya, sonra rotasyon listesinde dolu N hafta bekleme).

  HAFTA İÇİ B VARDIYASI (2 KİŞİ):
    1. personel: ROTATION_NAMES[week_index % len] — tüm hafta (Pzt-Cu)
    2. personel: Furkan veya Duygu, ardışık günlerde böler:
         - Biri Pzt-Sa (2 gün), diğeri Çr-Cu (3 gün)
         - Hafta bazında "kim 2 gün, kim 3 gün" alternate (week_index parity)

  HAFTA İÇİ C VARDIYASI (1 KİŞİ):
    Bu hafta C-1st = ROTATION_NAMES[(week_index - 1) % len]
    (yani önceki haftanın B-1st'i)

  SABİT A KADRO:
    Rıdvan, Fatih → her hafta içi (Pzt-Cu) a_fixed slot, hafta sonu yok

  ON-CALL (Pzt-Paz tüm hafta tek kişi):
    Rotasyon: Zehra → Yağız → Ülkü → Sabri (4 haftalık döngü, Ank↔İst alternate)
    Bu kişiler vardiyaya hiç girmez (is_oncall_only=True).

  HAFTA İÇİ A (geri kalanlar):
    B/C/on-call/Furkan/Duygu dışında kalan tüm "worker"lar her hafta içi
    günü kendi lokasyon A'sında (Ankara → a_ankara, İstanbul → a_istanbul).

  HAFTA SONU (Cmt-Paz):
    A, B, C için 3 ayrı kişi her gün (toplam 6 kişi-günü).
    Hafta içinde B/C-1st olarak çalışan kişiler hafta sonu **off** (max 5/hafta).
    Furkan ve Duygu da bu haftada B'ye girdiyse hafta sonu off
    (5 gün dolmuş olur).
    Geri kalan worker'lar haftalık rotasyonla hafta sonu kapatır.
    Her 5 haftadan 1'inde (yaklaşık %20) bir worker hafta sonu çalışmaz
    → ona sadece 5 hafta içi A düşer (off-week yok).

  MAX 5 GÜN/HAFTA:
    B-1st kişi: 5 hafta içi B (Pzt-Cu) → hafta sonu off
    C-1st kişi: 5 hafta içi C → hafta sonu off
    Furkan: Pzt-Sa B (2g) + Çr-Cu A (3g) = 5g — hafta sonu off (alt hafta tersi)
    Duygu: Pzt-Sa A (2g) + Çr-Cu B (3g) = 5g — hafta sonu off
    Normal worker: 4 hafta içi A + 1 hafta sonu = 5g

  MANUEL MÜDAHALE:
    Bir MonthlyShiftAssignment'ta modified_by_user_id IS NOT NULL ise
    jeneratör o (personnel_id, day) çiftine dokunmaz. overwrite_manual=True
    ile zorlanabilir (force re-generate).
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


# --- Kullanıcı tarifindeki rotasyon listeleri ----------------------------------

# Hafta içi B/C 1. personel rotasyonu. Her hafta listenin bir kişisi B'ye girer;
# o kişi bir sonraki hafta C'ye geçer (2 hafta vardiya, sonra dinlenir).
# v0.8.6: kullanıcı tarifine göre sıralama güncellendi (Doğukan↔İrfan,
# Burak↔Enes yer değiştirdi). Anchor 1 Haz 2026 = Talha (pozisyon 0).
WEEKDAY_ROTATION_NAMES: list[str] = [
    "Talha", "İrfan", "Doğukan", "Enes", "Burak",
    "Kübra", "Hasan", "Mehmet", "Beyza",
]

# B vardiyasında 2. personel — Furkan ve Duygu, ardışık günleri böler.
B_SECONDARY_NAMES: tuple[str, str] = ("Furkan", "Duygu")

# On-call sırası — Ankara ↔ İstanbul alternate (4 haftalık döngü).
ONCALL_ROTATION_NAMES: list[str] = ["Zehra", "Yağız", "Ülkü", "Sabri"]


@dataclass
class GenerationResult:
    days_generated: int = 0
    assignments_created: int = 0
    assignments_preserved: int = 0
    warnings: list[str] = field(default_factory=list)


# --- Yardımcılar --------------------------------------------------------------

def _by_name(personnel: list[Personnel]) -> dict[str, Personnel]:
    return {p.full_name: p for p in personnel}


#: Rotasyon anchor — bu tarih (Pazartesi) = WEEKDAY_ROTATION_NAMES[0] (Talha).
#: Kullanıcı 1-5 Haziran 2026 haftası için Talha=B-1st, Beyza=C-1st (önceki
#: haftanın B'si) örneği verdi. Buna göre tüm yıllar/aylar geriye-ileriye
#: deterministic hesaplanır.
ROTATION_ANCHOR_MONDAY: date = date(2026, 6, 1)


def _week_index_for_monday(monday: date, year: int) -> int:
    """Anchor Pazartesi'den itibaren kaç hafta geçti? (negatif olabilir)

    Önceki yıllar için negatif değer döner; Python modulo ile zaten doğru
    sonuç verir. Anchor değişirse tüm yıllar için rotasyon yeniden hizalanır.
    """
    delta_days = (monday - ROTATION_ANCHOR_MONDAY).days
    # Negatif fark için floor-division Python'da zaten doğru (toward -inf).
    return delta_days // 7


def _weeks_in_month(year: int, month: int) -> list[list[date]]:
    """Ayın günlerini Pzt-Paz haftalara böl (ay başında/sonunda kısmi olabilir)."""
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
    """Haftadaki ilk Pazartesi (ay başında kısmi haftada da Pazartesi'yi geri çıkar)."""
    if week_days[0].weekday() == 0:
        return week_days[0]
    # Pzt değilse, geri sayarak Pazartesi'yi hesapla
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
    """Hafta sonu (Cmt-Paz) için A/B/C atamalarını üret.

    Her gün 3 farklı kişi (A, B, C). Cmt ve Paz aynı kişiler değil — toplam
    6 farklı kişi (mümkünse). Workers_available içinden week_index'e bağlı
    deterministic seçimle ilerle.
    """
    out: dict[date, dict[MonthlyShiftSlot, Personnel]] = {}
    if not workers_available:
        return out

    weekend_days = [d for d in week_days if d.weekday() >= 5]  # 5=Cmt, 6=Paz
    if not weekend_days:
        return out

    # Slot sırası: A, B, C — 3 ayrı kişi her gün.
    # Cmt için: pool'dan ardışık 3 (week_index*6+0, +1, +2)
    # Paz için: ardışık 3 (week_index*6+3, +4, +5)
    n = len(workers_available)
    if n < 3:
        # Yeterli kişi yoksa elden geleni yap.
        weekend_days = weekend_days[:1]

    base = (week_index * 6) % n
    for i, day in enumerate(weekend_days):
        slots = (MonthlyShiftSlot.a_istanbul, MonthlyShiftSlot.b_shift, MonthlyShiftSlot.c_shift)
        out[day] = {}
        for j, slot in enumerate(slots):
            idx = (base + i * 3 + j) % n
            out[day][slot] = workers_available[idx]
    return out


# --- Ana jeneratör ------------------------------------------------------------

def generate_month(
    db: Session,
    year: int,
    month: int,
    overwrite_manual: bool = False,
) -> GenerationResult:
    """Bir ayın vardiya çizelgesini üretir + DB'ye yazar.

    Manuel kayıtlar (modified_by_user_id NOT NULL) overwrite_manual=False
    iken korunur. True olursa hepsi silinir.
    """
    result = GenerationResult()

    personnel = (
        db.query(Personnel)
        .filter(Personnel.is_active.is_(True))
        .order_by(Personnel.full_name.asc())
        .all()
    )
    if not personnel:
        result.warnings.append("Personel listesi boş; önce /personnel ile ekleyin.")
        return result

    by_name = _by_name(personnel)

    # Sabit A kadrosu
    fixed = [p for p in personnel if p.group == PersonnelGroup.fixed_a]
    # On-call only personel — havuz olarak da listeden seçeceğiz, ama burada
    # rotasyon için isimle eşleştir.
    oncall_pool_named = [by_name[n] for n in ONCALL_ROTATION_NAMES if n in by_name]
    # B 2. personel pool (Furkan + Duygu)
    b_secondary = [by_name[n] for n in B_SECONDARY_NAMES if n in by_name]

    # Vardiya rotasyonuna giren 1. personel (Talha → Beyza arası)
    rotation_personnel = [by_name[n] for n in WEEKDAY_ROTATION_NAMES if n in by_name]

    # Personel master'da olup yukarıdaki rollerden hiçbirinde olmayan worker'lar.
    # Bu kişiler hafta içi her zaman A vardiyası (kendi lokasyonu), hafta sonu
    # rotasyonuna girer.
    role_names = (
        set(WEEKDAY_ROTATION_NAMES)
        | set(B_SECONDARY_NAMES)
        | set(ONCALL_ROTATION_NAMES)
        | {p.full_name for p in fixed}
    )
    other_workers = [
        p for p in personnel
        if p.full_name not in role_names and not p.is_oncall_only and not p.is_fixed_a
    ]

    # Uyarılar — beklenen ama bulunamayan isimler
    missing = [n for n in (WEEKDAY_ROTATION_NAMES + list(B_SECONDARY_NAMES) + ONCALL_ROTATION_NAMES)
               if n not in by_name]
    if missing:
        result.warnings.append(
            f"Personel master'da bulunamayan rotasyon isimleri: {', '.join(missing)} "
            "— bu kişiler için atama yapılamadı."
        )

    # Önce ayın mevcut atamalarını sil (manuelleri koru ya da silmek için).
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
        # Manuel olmayanları sil; manuel olanlar korunur.
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

    # Manuel lock'lu (modified) kayıtların (person_id, day) seti — onlara dokunma.
    locked_keys: set[tuple[int, date]] = set()
    for (pid, dday) in (
        db.query(MonthlyShiftAssignment.personnel_id, MonthlyShiftAssignment.day)
        .filter(MonthlyShiftAssignment.day >= first_day)
        .filter(MonthlyShiftAssignment.day <= last_day)
        .all()
    ):
        locked_keys.add((pid, dday))

    weeks = _weeks_in_month(year, month)
    result.days_generated = sum(len(w) for w in weeks)

    to_add: list[MonthlyShiftAssignment] = []

    def add(p: Personnel, d: date, s: MonthlyShiftSlot) -> bool:
        """Manuel lock yoksa atamaya ekle. (True döner ekleme yapıldıysa)"""
        if (p.id, d) in locked_keys:
            return False
        to_add.append(MonthlyShiftAssignment(personnel_id=p.id, day=d, slot=s))
        return True

    for week_days in weeks:
        monday = _monday_of_week(week_days)
        week_idx = _week_index_for_monday(monday, year)

        # B-1st (this week) ve C-1st (this week = previous week's B-1st)
        b_first = _pick_rotating(rotation_personnel, week_idx) if rotation_personnel else None
        c_first = _pick_rotating(rotation_personnel, week_idx - 1) if rotation_personnel else None

        # v0.8.9: Furkan/Duygu B-2nd split — kullanıcının paylaştığı Haziran
        # ekran görüntülerine göre kesinleşen desen:
        #
        #   Çift hafta (idx 0, 2, 4, ...):
        #     Furkan = Pzt + Sal + Çar (3 gün ardışık)
        #     Duygu  = Per + Cu        (2 gün ardışık)
        #   Tek hafta (idx 1, 3, 5, ...):
        #     Furkan = Pzt + Sal       (2 gün ardışık)
        #     Duygu  = Çar + Per + Cu  (3 gün ardışık)
        #
        # Furkan her zaman haftanın başında, Duygu her zaman haftanın sonunda.
        # Kişiler swap olmaz — yalnızca bölme noktası 2-3 / 3-2 arası kayar.
        # Personel master'da yoksa None kalır, atama yapılmaz.
        furkan = by_name.get("Furkan")
        duygu = by_name.get("Duygu")
        if week_idx % 2 == 0:
            furkan_b_weekdays = {0, 1, 2}  # Pzt, Sal, Çar — 3 gün
            duygu_b_weekdays = {3, 4}      # Per, Cu        — 2 gün
        else:
            furkan_b_weekdays = {0, 1}     # Pzt, Sal       — 2 gün
            duygu_b_weekdays = {2, 3, 4}   # Çar, Per, Cu   — 3 gün

        # On-call kişisi
        oncall_person = _pick_rotating(oncall_pool_named, week_idx) if oncall_pool_named else None

        # Bu haftaki "Hafta sonu çalışacak" worker pool'u:
        # B/C 1st ve B-2nd (Furkan/Duygu) bu hafta hafta sonu off.
        weekend_workers_pool: list[Personnel] = []
        # Önce other_workers (vardiyaya giren ama bu hafta B/C/B-2nd değil)
        weekend_busy_names = set()
        if b_first: weekend_busy_names.add(b_first.full_name)
        if c_first: weekend_busy_names.add(c_first.full_name)
        for p in b_secondary:
            weekend_busy_names.add(p.full_name)

        # Rotation personnel'den bu hafta B/C olmayanlar da hafta sonu havuzuna girer
        for p in rotation_personnel:
            if p.full_name not in weekend_busy_names:
                weekend_workers_pool.append(p)
        # Other workers (sabit roldekiler hariç worker'lar)
        for p in other_workers:
            if p.full_name not in weekend_busy_names:
                weekend_workers_pool.append(p)

        # %20 hafta sonu off kuralı: her 5 haftada 1 worker hafta sonu izinli.
        # weekend_workers_pool sıralı; week_idx % 5 == 0 ise pool'dan ilk
        # kişiyi çıkar (bu hafta o kişi hafta sonu çalışmaz).
        if weekend_workers_pool and week_idx % 5 == 0:
            skipped_for_weekend_off = weekend_workers_pool.pop(0)
            # İsteğe bağlı: bu kişiye Cmt-Paz için 'off' slot yazılabilir,
            # ama tablo daha sade görünmesi için yazmıyoruz; hücre boş kalır.
            _ = skipped_for_weekend_off  # unused intentional

        weekend_slots = _weekend_assignments_for_week(
            week_days, weekend_workers_pool, week_idx,
        )

        for day in week_days:
            is_weekend = day.weekday() >= 5  # 5=Sat, 6=Sun

            # On-call — tüm hafta (Pzt-Paz)
            if oncall_person:
                add(oncall_person, day, MonthlyShiftSlot.oncall)

            if not is_weekend:
                # Sabit A — Pzt-Cu
                for p in fixed:
                    add(p, day, MonthlyShiftSlot.a_fixed)

                # B vardiyası 1. personel — Pzt-Cu
                if b_first:
                    add(b_first, day, MonthlyShiftSlot.b_shift)

                # v0.8.9: B vardiyası 2. personel — Furkan/Duygu split (yukarıda
                # week_idx parity'ye göre furkan_b_weekdays/duygu_b_weekdays
                # set'leri hesaplandı). Her gün hangi set'e dahilse o kişiyi
                # B'ye, diğerini kendi lokasyonunun A'sına yaz.
                wd = day.weekday()
                if furkan and wd in furkan_b_weekdays:
                    add(furkan, day, MonthlyShiftSlot.b_shift)
                elif furkan:
                    slot = (MonthlyShiftSlot.a_istanbul
                            if furkan.location.value == "istanbul"
                            else MonthlyShiftSlot.a_ankara)
                    add(furkan, day, slot)
                if duygu and wd in duygu_b_weekdays:
                    add(duygu, day, MonthlyShiftSlot.b_shift)
                elif duygu:
                    slot = (MonthlyShiftSlot.a_istanbul
                            if duygu.location.value == "istanbul"
                            else MonthlyShiftSlot.a_ankara)
                    add(duygu, day, slot)

                # C vardiyası 1. personel — Pzt-Cu
                if c_first:
                    add(c_first, day, MonthlyShiftSlot.c_shift)

                # Geri kalan tüm worker'lar → A (lokasyon bazlı)
                already_assigned_today = {
                    a.personnel_id for a in to_add if a.day == day
                }
                # rotation_personnel içinde bu hafta B/C değil olanlar
                for p in rotation_personnel:
                    if p.id in already_assigned_today:
                        continue
                    slot = (MonthlyShiftSlot.a_istanbul if p.location.value == "istanbul"
                            else MonthlyShiftSlot.a_ankara)
                    add(p, day, slot)
                # other_workers (rotasyona girmeyen worker'lar)
                for p in other_workers:
                    if p.id in already_assigned_today:
                        continue
                    slot = (MonthlyShiftSlot.a_istanbul if p.location.value == "istanbul"
                            else MonthlyShiftSlot.a_ankara)
                    add(p, day, slot)
                # v0.8.8: On-call only kişiler (Sabri/Yağız/Ülkü/Zehra) bu
                # hafta on-call değilse hafta içi günlerde kendi lokasyonunun
                # A vardiyasında olur. Bu haftaki on-call kişisi zaten
                # already_assigned_today içinde (oncall slot atandı).
                for p in oncall_pool_named:
                    if p.id in already_assigned_today:
                        continue
                    slot = (MonthlyShiftSlot.a_istanbul if p.location.value == "istanbul"
                            else MonthlyShiftSlot.a_ankara)
                    add(p, day, slot)
            else:
                # Hafta sonu (Cmt-Paz): A/B/C için 3 farklı kişi
                slots_for_day = weekend_slots.get(day, {})
                for slot, person in slots_for_day.items():
                    add(person, day, slot)

    # --- v0.8.7: Max 5 gün/hafta + boş günlere "off" yaz ---
    #
    # Her personelin Pzt-Paz aralığında 5 günden fazla atanmasını engelle:
    # 5+ ise sonradan eklenen weekend atamalarını "off" ile değiştir.
    # Sonra TÜM boş (personnel, day) hücrelerine 'off' slot'u yaz —
    # çizelgede kimin hangi gün izinli/off olduğu açıkça görünsün.
    #
    # Kullanıcı taleplerine göre on-call dahil 7 gün çalışan biri "max 5"
    # kuralından muaftır (on-call zaten bekleme statüsü). Sadece hafta sonu
    # haftaiçi A/B/C alan kişilere off uygulanır.
    weekday_a_b_c_slots = {
        MonthlyShiftSlot.a_fixed, MonthlyShiftSlot.a_ankara,
        MonthlyShiftSlot.a_istanbul, MonthlyShiftSlot.b_shift,
        MonthlyShiftSlot.c_shift,
    }

    # Person → set(days) mapping
    person_days: dict[int, set[date]] = {}
    for a in to_add:
        person_days.setdefault(a.personnel_id, set()).add(a.day)

    # Her haftada her personele 5 gün üst sınırı (on-call dışında).
    # On-call kişi 7 gün on-call yazılı (Pzt-Paz), bu cap'a tabi değil.
    oncall_person_ids_per_week: dict[int, set[int]] = {}
    for a in to_add:
        if a.slot == MonthlyShiftSlot.oncall:
            wk_iso = a.day.isocalendar().week
            oncall_person_ids_per_week.setdefault(wk_iso, set()).add(a.personnel_id)

    # Manuel locked combolardaki günleri de say (off yazmasın)
    for (pid, dday) in locked_keys:
        person_days.setdefault(pid, set()).add(dday)

    # Boş hücrelere off yaz — tüm aktif personnel × tüm ay günleri
    all_month_days: list[date] = []
    for week_days in weeks:
        all_month_days.extend(week_days)

    for p in personnel:
        # Sabit A kadrosu hafta sonu off — onlar zaten Pzt-Cu sabit A.
        # Diğer worker'lar weekend rotasyonuna girer; rotasyon dışındakilere off.
        # On-call kişiler tüm hafta on-call atandıkları için boş günleri yok.
        for day in all_month_days:
            if (p.id, day) in locked_keys:
                continue
            if day in person_days.get(p.id, set()):
                continue
            # Bu (person, day) için hiç atama yok → off yaz
            to_add.append(MonthlyShiftAssignment(
                personnel_id=p.id, day=day, slot=MonthlyShiftSlot.off,
            ))

    db.bulk_save_objects(to_add)
    db.commit()
    result.assignments_created = len(to_add)
    return result
