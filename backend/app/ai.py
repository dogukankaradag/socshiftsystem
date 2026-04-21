"""On-prem deterministic shift summarization.

This module DOES NOT call any third-party / cloud service. All processing is
local, deterministic, and offline-safe. Outputs are in Turkish to match the UI.

v0.4: Priority kavramı Entry'den kaldırıldı. Özet artık tür bazlı sayım,
sayısal toplamlar ve occurs_at (planlanan zaman) etrafında şekilleniyor.
"""
from __future__ import annotations
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import List

from .models import Entry, EntryType, NUMERIC_ENTRY_TYPES, Priority

# Incident modeli hâlâ Priority kullandığı için label'ı burada tutuyoruz.
PRIORITY_LABEL_TR = {
    Priority.low: "düşük",
    Priority.medium: "orta",
    Priority.high: "yüksek",
    Priority.critical: "kritik",
}

ENTRY_TYPE_LABEL_TR = {
    EntryType.ddos_transfer: "DDoS Taşıma",
    EntryType.info: "Bilgi",
    EntryType.important_work: "Yapılan Önemli İşler",
    EntryType.l2_escalation: "L2'ye Eskale Edilen Konu(lar)",
    EntryType.callers: "Arayanlar",
    EntryType.dhs: "DHS",
    EntryType.iys: "İYS",
}


@dataclass
class AIResult:
    summary: str
    action_items: List[str]
    highlights: List[str]
    duplicates: List[dict]  # [{entry_id, duplicate_of, similarity}]


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def detect_duplicates(entries: List[Entry], threshold: float = 0.82) -> List[dict]:
    """Detect near-duplicate text entries using SequenceMatcher."""
    dupes: List[dict] = []
    docs = [
        (e.id, _clean(f"{e.title or ''} {e.body or ''}").lower())
        for e in entries
        if e.entry_type not in NUMERIC_ENTRY_TYPES
    ]
    for i, (id_a, doc_a) in enumerate(docs):
        for id_b, doc_b in docs[i + 1 :]:
            if not doc_a or not doc_b:
                continue
            if abs(len(doc_a) - len(doc_b)) / max(len(doc_a), len(doc_b)) > 0.5:
                continue
            ratio = SequenceMatcher(None, doc_a, doc_b).ratio()
            if ratio >= threshold:
                dupes.append({
                    "entry_id": id_b,
                    "duplicate_of": id_a,
                    "similarity": round(ratio, 3),
                })
    return dupes


def summarize_shift(entries: List[Entry], upcoming: List[Entry] = None) -> AIResult:
    """Produce a deterministic Turkish handover summary. No network calls.

    `entries`: bu vardiyada girilmiş kayıtlar.
    `upcoming`: henüz zamanı gelmemiş, gelecek vardiyalara taşınan planlı girişler.
    """
    upcoming = upcoming or []
    if not entries and not upcoming:
        return AIResult(
            summary="Bu vardiyada giriş yapılmadı ve yaklaşan planlı iş bulunmuyor.",
            action_items=[],
            highlights=[],
            duplicates=[],
        )

    by_type_count = Counter(e.entry_type for e in entries)
    numeric_totals: dict[EntryType, int] = {}
    for e in entries:
        if e.entry_type in NUMERIC_ENTRY_TYPES and e.numeric_value is not None:
            numeric_totals[e.entry_type] = numeric_totals.get(e.entry_type, 0) + int(e.numeric_value)

    type_summary_parts = []
    for t, count in by_type_count.most_common():
        label = ENTRY_TYPE_LABEL_TR.get(t, t.value)
        if t in NUMERIC_ENTRY_TYPES:
            total = numeric_totals.get(t, 0)
            type_summary_parts.append(f"{count} {label} kaydı (toplam: {total})")
        else:
            type_summary_parts.append(f"{count} {label}")

    parts: List[str] = []
    if entries:
        parts.append(f"Toplam {len(entries)} giriş: " + "; ".join(type_summary_parts) + ".")
    else:
        parts.append("Bu vardiyada girilen yeni kayıt yok.")
    if upcoming:
        parts.append(f"Önümüzdeki dönemde {len(upcoming)} planlı iş takipte.")
    summary = " ".join(parts)

    highlights: List[str] = []
    # Öne çıkanlar: tüm türlerden en son eklenen ilk 6 giriş.
    for e in sorted(entries, key=lambda x: x.created_at, reverse=True)[:6]:
        label = ENTRY_TYPE_LABEL_TR.get(e.entry_type, e.entry_type.value)
        if e.entry_type in NUMERIC_ENTRY_TYPES and e.numeric_value is not None:
            highlights.append(f"{label}: {e.numeric_value}")
        else:
            snippet = _clean(e.body)[:120] or e.title or label
            highlights.append(f"{label} – {snippet}")

    # Takip edilecekler: hem bu vardiyanın L2 escalation/önemli iş tipleri hem de
    # henüz zamanı gelmemiş planlı işlerin özeti.
    action_items: List[str] = []
    for e in entries:
        if e.entry_type in (EntryType.l2_escalation, EntryType.important_work, EntryType.ddos_transfer):
            label = ENTRY_TYPE_LABEL_TR.get(e.entry_type, e.entry_type.value)
            snippet = _clean(e.body)[:140] or e.title or label
            action_items.append(f"Takip: {label} – {snippet}")
    for e in sorted(upcoming, key=lambda x: x.occurs_at or datetime.max.replace(tzinfo=timezone.utc))[:6]:
        label = ENTRY_TYPE_LABEL_TR.get(e.entry_type, e.entry_type.value)
        snippet = _clean(e.body)[:140] or e.title or label
        when = e.occurs_at.strftime("%Y-%m-%d %H:%M") if e.occurs_at else "?"
        action_items.append(f"Planlı ({when} UTC): {label} – {snippet}")

    seen = set()
    action_items = [a for a in action_items if not (a in seen or seen.add(a))][:12]

    return AIResult(
        summary=summary,
        action_items=action_items,
        highlights=highlights,
        duplicates=detect_duplicates(entries),
    )
