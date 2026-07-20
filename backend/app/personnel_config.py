"""Personnel + rotasyon yapılandırma loader'ı (v0.9.0).

Tüm gerçek personel isimleri ve iş-kuralı listeleri (rotasyon sırası, on-call
havuzu, Cuma öğlen havuzu, sabit override'lar vb.) dış bir JSON dosyasından
okunur. Bu dosya `.gitignored` olduğundan repo'ya sızmaz.

Dosya yolu öncelik sırası:
  1) PERSONNEL_CONFIG_PATH env değişkeni (varsa)
  2) /app/config/personnel_config.json  (Docker mount noktası)
  3) <repo_root>/config/personnel_config.json  (yerel geliştirme)

Dosya yoksa boş yapı döner — sistem çalışmaya devam eder ama Aylık Vardiya
jeneratörü personel bulamaz ve kullanıcıya "personel yok" uyarısı verir.
"""
from __future__ import annotations
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class PersonnelSpec:
    full_name: str
    location: str  # 'istanbul' | 'ankara'
    group: str    # PersonnelGroup enum value
    is_oncall_only: bool = False
    is_fixed_a: bool = False


@dataclass
class ForcedOverride:
    name: str
    start_date: date
    end_date: date
    slot: str  # MonthlyShiftSlot enum value


@dataclass
class PersonnelConfig:
    personnel: list[PersonnelSpec] = field(default_factory=list)
    excluded_from_daily_duty: list[str] = field(default_factory=list)
    weekday_rotation: list[str] = field(default_factory=list)
    b_secondary: list[str] = field(default_factory=list)
    oncall_rotation: list[str] = field(default_factory=list)
    friday_lunch_pool: list[str] = field(default_factory=list)
    rotation_anchor_monday: date = date(2026, 6, 1)
    forced_overrides: list[ForcedOverride] = field(default_factory=list)


def _candidate_paths() -> list[Path]:
    env = os.environ.get("PERSONNEL_CONFIG_PATH")
    paths: list[Path] = []
    if env:
        paths.append(Path(env))
    paths.append(Path("/app/config/personnel_config.json"))
    # Yerel geliştirme (repo_root/config/personnel_config.json)
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "config" / "personnel_config.json"
        if candidate.exists():
            paths.append(candidate)
            break
    return paths


def _parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _load_from_disk() -> PersonnelConfig:
    for path in _candidate_paths():
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception:
            log.exception("Personnel config parse hatası: %s", path)
            continue

        personnel = [
            PersonnelSpec(
                full_name=p["full_name"],
                location=p["location"],
                group=p.get("group", p["location"]),
                is_oncall_only=bool(p.get("is_oncall_only", False)),
                is_fixed_a=bool(p.get("is_fixed_a", False)),
            )
            for p in raw.get("personnel", [])
        ]
        overrides = [
            ForcedOverride(
                name=o["name"],
                start_date=_parse_date(o["start_date"]),
                end_date=_parse_date(o["end_date"]),
                slot=o["slot"],
            )
            for o in raw.get("forced_overrides", [])
        ]
        anchor = raw.get("rotation_anchor_monday")
        cfg = PersonnelConfig(
            personnel=personnel,
            excluded_from_daily_duty=list(raw.get("excluded_from_daily_duty", [])),
            weekday_rotation=list(raw.get("weekday_rotation", [])),
            b_secondary=list(raw.get("b_secondary", [])),
            oncall_rotation=list(raw.get("oncall_rotation", [])),
            friday_lunch_pool=list(raw.get("friday_lunch_pool", [])),
            rotation_anchor_monday=(
                _parse_date(anchor) if anchor else date(2026, 6, 1)
            ),
            forced_overrides=overrides,
        )
        log.info(
            "Personnel config yüklendi: %s (%d kişi, %d override)",
            path, len(cfg.personnel), len(cfg.forced_overrides),
        )
        return cfg

    log.warning(
        "Personnel config bulunamadı; boş yapı döndürülüyor. "
        "config/personnel_config.example.json dosyasını kopyalayıp "
        "config/personnel_config.json olarak doldurun."
    )
    return PersonnelConfig()


@lru_cache(maxsize=1)
def get_personnel_config() -> PersonnelConfig:
    """Cache'li config erişimi — startup'ta bir kez okunur."""
    return _load_from_disk()


def reload_personnel_config() -> PersonnelConfig:
    """Cache'i temizleyip yeniden yükler (test/CLI için)."""
    get_personnel_config.cache_clear()
    return get_personnel_config()
