"""Build Markdown / HTML handover reports from shift entries (Turkish).

v0.4: Priority kaldırıldı; rapor içeriği tür bazlı gruplama ve
"Yaklaşan Planlı İşler" bölümü üzerinden şekilleniyor. Varsayılan başlık
"MSSP Vardiya Raporu — {A/B/C Vardiyası} ({tarih})"; operatör isterse
UI'dan konu alanını ezebilir.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from jinja2 import Template

from .ai import AIResult, ENTRY_TYPE_LABEL_TR
from .config import get_settings
from .models import Entry, EntryType, NUMERIC_ENTRY_TYPES, Shift

settings = get_settings()

# Rapor içinde tür bazlı gruplama sırası — en kritik/gözlem türleri en üstte.
TYPE_ORDER: List[EntryType] = [
    EntryType.ddos_transfer,
    EntryType.important_work,
    EntryType.l2_escalation,
    EntryType.callers,
    EntryType.info,
    EntryType.dhs,
    EntryType.iys,
]

SHIFT_TYPE_LABEL_TR = {
    "a": "A Vardiyası",
    "b": "B Vardiyası",
    "c": "C Vardiyası",
}

DEFAULT_SUBJECT_PREFIX = "MSSP Vardiya Raporu"


def _entry_display(e: Entry) -> tuple[str, str]:
    """Return (type label, content string)."""
    label = ENTRY_TYPE_LABEL_TR.get(e.entry_type, e.entry_type.value)
    if e.entry_type in NUMERIC_ENTRY_TYPES and e.numeric_value is not None:
        return label, f"Adet: {e.numeric_value}"
    return label, (e.body or "").strip()


_MD_TEMPLATE = Template("""# {{ title }}

**Dönem:** {{ shift_start }} → {{ end }}
**Toplam giriş:** {{ entries|length }}{% if upcoming %}  ·  **Yaklaşan Planlı İşler:** {{ upcoming|length }}{% endif %}

## Yönetici Özeti
{{ ai.summary }}

{% if totals_numeric %}
## Sayısal Toplamlar (Bu Vardiya)
{% for row in totals_numeric %}- **{{ row.label }}:** {{ row.total }} (kayıt: {{ row.count }})
{% endfor %}{% endif %}
{% if ai.highlights %}
## Öne Çıkan Maddeler
{% for h in ai.highlights %}- {{ h }}
{% endfor %}{% endif %}
{% if ai.action_items %}
## Bir Sonraki Vardiya İçin Takip Edilecekler
{% for a in ai.action_items %}{{ loop.index }}. {{ a }}
{% endfor %}{% endif %}

## Tür Bazında Girişler
{% for t in types %}{% if grouped[t.value] %}
### {{ type_label_tr[t] }} ({{ grouped[t.value]|length }})
{% for e in grouped[t.value] %}- {% if e.occurs_at %}**[{{ local_fmt(e.occurs_at) }}]** {% endif %}{{ entry_display(e)[1] }}{% if e.source %} _({{ e.source }})_{% endif %}
{% endfor %}{% endif %}{% endfor %}

{% if upcoming %}
## Yaklaşan Planlı İşler (Diğer Vardiyalardan Taşınan)
{% for e in upcoming %}- **{{ local_fmt(e.occurs_at) }}** — _{{ type_label_tr[e.entry_type] }}_: {{ (e.body or e.title or '')[:200] }}
{% endfor %}{% endif %}

{% if ai.duplicates %}
## Olası Mükerrer Kayıtlar
{% for d in ai.duplicates %}- #{{ d.entry_id }} ≈ #{{ d.duplicate_of }} (benzerlik: {{ d.similarity }})
{% endfor %}{% endif %}

---
_Bu rapor Vardiya Devir Sistemi tarafından {{ now }} ({{ tz }}) zamanında otomatik oluşturuldu._
""")

_HTML_TEMPLATE = Template("""<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><title>{{ title }}</title>
<style>
  body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:820px;margin:24px auto;color:#1f2937;line-height:1.55;padding:0 16px}
  h1{margin-bottom:4px;color:#111827}
  h2{border-bottom:1px solid #e5e7eb;padding-bottom:4px;margin-top:28px;color:#111827}
  .meta{color:#6b7280;margin-bottom:16px}
  .entry{padding:10px 12px;border:1px solid #e5e7eb;border-radius:8px;margin:8px 0;background:#fafafa}
  .entry .t{font-weight:600}
  .entry .b{color:#374151;white-space:pre-wrap;margin-top:4px}
  .upcoming{background:#fef3c7;border-color:#fde68a}
  .when{display:inline-block;font-size:12px;color:#1d4ed8;background:#dbeafe;padding:2px 8px;border-radius:999px;margin-right:8px;font-weight:600}
  .src{display:inline-block;font-size:11px;color:#6b7280;background:#e5e7eb;padding:1px 6px;border-radius:4px;margin-left:6px}
  .totals{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px;margin:12px 0}
  .tot{background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:10px}
  .tot b{color:#1d4ed8;font-size:20px}
  footer{color:#9ca3af;font-size:12px;margin-top:32px;border-top:1px solid #e5e7eb;padding-top:12px}
</style></head><body>
<h1>{{ title }}</h1>
<div class="meta"><b>Dönem:</b> {{ shift_start }} &rarr; {{ end }} &nbsp;|&nbsp; <b>Giriş sayısı:</b> {{ entries|length }}{% if upcoming %} &nbsp;|&nbsp; <b>Yaklaşan:</b> {{ upcoming|length }}{% endif %}</div>
<h2>Yönetici Özeti</h2><p>{{ ai.summary }}</p>
{% if totals_numeric %}
<h2>Sayısal Toplamlar</h2>
<div class="totals">{% for row in totals_numeric %}<div class="tot">{{ row.label }}<br><b>{{ row.total }}</b><br><span style="color:#6b7280;font-size:12px">kayıt: {{ row.count }}</span></div>{% endfor %}</div>
{% endif %}
{% if ai.highlights %}<h2>Öne Çıkan Maddeler</h2><ul>{% for h in ai.highlights %}<li>{{ h }}</li>{% endfor %}</ul>{% endif %}
{% if ai.action_items %}<h2>Bir Sonraki Vardiya İçin Takip</h2><ol>{% for a in ai.action_items %}<li>{{ a }}</li>{% endfor %}</ol>{% endif %}
<h2>Tür Bazında Girişler</h2>
{% for t in types %}{% if grouped[t.value] %}
<h3>{{ type_label_tr[t] }} ({{ grouped[t.value]|length }})</h3>
{% for e in grouped[t.value] %}<div class="entry">{% if e.occurs_at %}<span class="when">{{ local_fmt(e.occurs_at) }}</span>{% endif %}<span class="t">{{ type_label_tr[e.entry_type] }}</span>{% if e.source %}<span class="src">{{ e.source }}</span>{% endif %}<div class="b">{{ entry_display(e)[1] }}</div></div>{% endfor %}
{% endif %}{% endfor %}
{% if upcoming %}
<h2>Yaklaşan Planlı İşler (Diğer Vardiyalardan)</h2>
{% for e in upcoming %}<div class="entry upcoming"><span class="when">{{ local_fmt(e.occurs_at) }}</span><span class="t">{{ type_label_tr[e.entry_type] }}</span><div class="b">{{ (e.body or e.title or '')[:400] }}</div></div>{% endfor %}
{% endif %}
{% if ai.duplicates %}<h2>Olası Mükerrer Kayıtlar</h2><ul>{% for d in ai.duplicates %}<li>#{{ d.entry_id }} ≈ #{{ d.duplicate_of }} (benzerlik: {{ d.similarity }})</li>{% endfor %}</ul>{% endif %}
<footer>Vardiya Devir Sistemi tarafından {{ now }} ({{ tz }}) zamanında otomatik oluşturuldu.</footer>
</body></html>
""")


def _group_by_type(entries: List[Entry]) -> dict:
    grouped = {t.value: [] for t in TYPE_ORDER}
    for e in sorted(entries, key=lambda x: x.created_at):
        grouped.setdefault(e.entry_type.value, []).append(e)
    return grouped


def _numeric_totals(entries: List[Entry]) -> list[dict]:
    """Summarize DHS/İYS totals for this shift."""
    agg: dict[EntryType, dict] = {}
    for e in entries:
        if e.entry_type in NUMERIC_ENTRY_TYPES:
            row = agg.setdefault(e.entry_type, {"label": ENTRY_TYPE_LABEL_TR[e.entry_type], "total": 0, "count": 0})
            row["total"] += int(e.numeric_value or 0)
            row["count"] += 1
    return list(agg.values())


def _local(dt: datetime) -> str:
    tz = ZoneInfo(settings.scheduler_timezone)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M")


def _local_short(dt: datetime) -> str:
    tz = ZoneInfo(settings.scheduler_timezone)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz).strftime("%d.%m %H:%M")


def build_report(shift: Shift, entries: List[Entry], ai: AIResult,
                 upcoming: Optional[List[Entry]] = None,
                 subject_override: Optional[str] = None) -> tuple[str, str, str, str]:
    """Return (title, summary, markdown, html). All strings are Turkish."""
    upcoming = upcoming or []
    tz_label = settings.scheduler_timezone
    now_local = datetime.now(timezone.utc).astimezone(ZoneInfo(tz_label)).strftime("%Y-%m-%d %H:%M")
    shift_start = _local(shift.started_at)
    end = _local(shift.ended_at) if shift.ended_at else "devam ediyor"
    shift_label = SHIFT_TYPE_LABEL_TR.get(shift.shift_type.value, shift.shift_type.value)

    grouped = _group_by_type(entries)
    totals_numeric = _numeric_totals(entries)

    if subject_override and subject_override.strip():
        title = subject_override.strip()
    else:
        title = f"{DEFAULT_SUBJECT_PREFIX} — {shift_label} ({shift_start[:10]})"

    md = _MD_TEMPLATE.render(
        title=title, shift_label=shift_label,
        shift_start=shift_start, end=end,
        entries=entries, upcoming=upcoming, ai=ai,
        types=TYPE_ORDER, grouped=grouped,
        totals_numeric=totals_numeric,
        entry_display=_entry_display,
        type_label_tr=ENTRY_TYPE_LABEL_TR,
        local_fmt=_local_short,
        now=now_local, tz=tz_label,
    )
    html = _HTML_TEMPLATE.render(
        title=title,
        shift_start=shift_start, end=end,
        entries=entries, upcoming=upcoming, ai=ai,
        types=TYPE_ORDER, grouped=grouped,
        totals_numeric=totals_numeric,
        entry_display=_entry_display,
        type_label_tr=ENTRY_TYPE_LABEL_TR,
        local_fmt=_local_short,
        now=now_local, tz=tz_label,
    )
    return title, ai.summary, md, html
