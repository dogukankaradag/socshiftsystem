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

# v0.6.0: Mail body için kompakt, Outlook/Gmail uyumlu tablo şablonu.
# Müşterinin paylaştığı görsel örneğe sadık: greeting + tek tablo + footer.
# Tüm CSS inline; class kullanılmaz (kurumsal Outlook bazı class'ları siler).
# v0.8.5: Her giriş türü kendi satırı altında gösterilir; ilgili girişi
# olmayan satırlar render edilmez (boş başlık yok). Bilgi ve L2 ayrı
# satırlara bölündü (önceden L2 satırı altında karışıktı). Bilgi
# kırmızı + kalın vurgulanmaya devam eder (kalıcı uyarı niteliği).
_HTML_TEMPLATE = Template("""<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><title>{{ title }}</title></head>
<body style="font-family:Calibri,Segoe UI,Arial,sans-serif;color:#1f2937;font-size:14px;line-height:1.5;margin:0;padding:16px;">

<p style="margin:0 0 12px;">Merhaba,</p>
<p style="margin:0 0 12px;">MSSP ekibi vardiya raporuna ait detaylar tabloda paylaşılmıştır.</p>
<p style="margin:0 0 20px;">Bilgilerinize.</p>

<table cellspacing="0" cellpadding="6" border="1"
       style="border-collapse:collapse;width:100%;max-width:780px;border:1px solid #7a7a7a;font-size:13px;">

  {# --- MSSP Talepler (3 satır birleşmiş) --- #}
  <tr>
    <td rowspan="3" style="background:#dce6f1;border:1px solid #7a7a7a;font-weight:bold;width:32%;vertical-align:middle;">
      MSSP Talepler
    </td>
    <td style="border:1px solid #7a7a7a;width:43%;">İYS kapatılan case</td>
    <td style="border:1px solid #7a7a7a;text-align:center;width:25%;">{{ totals.iys if totals.iys else '' }}</td>
  </tr>
  <tr>
    <td style="border:1px solid #7a7a7a;">DHS kapatılan iş emri</td>
    <td style="border:1px solid #7a7a7a;text-align:center;">{{ totals.dhs if totals.dhs else '' }}</td>
  </tr>
  <tr>
    <td style="border:1px solid #7a7a7a;">SM kapatılan iş emri</td>
    <td style="border:1px solid #7a7a7a;text-align:center;">{{ totals.sm if totals.sm else '' }}</td>
  </tr>

  {# --- Telefon ile gelen Müşteri Çağrıları --- #}
  {% if grouped['callers'] %}
  <tr>
    <td style="background:#dce6f1;border:1px solid #7a7a7a;font-weight:bold;vertical-align:top;">
      Telefon ile gelen Müşteri Çağrıları
    </td>
    <td colspan="2" style="border:1px solid #7a7a7a;vertical-align:top;">
      <ul style="margin:0;padding-left:18px;">
      {% for e in grouped['callers'] %}<li>
        {% if e.caller_org_name %}<b>{{ e.caller_org_name }}</b>{% endif %}
        {% if e.caller_contact_name %} &mdash; {{ e.caller_contact_name }}{% endif %}
        {% if e.caller_contact_phone %} ({{ e.caller_contact_phone }}){% endif %}
        {% if e.body %} &middot; <span style="color:#555;">{{ e.body }}</span>{% endif %}
      </li>{% endfor %}
      </ul>
    </td>
  </tr>
  {% endif %}

  {# --- Yapılan Önemli İşler / Olaylar --- #}
  {% if grouped['important_work'] %}
  <tr>
    <td style="background:#dce6f1;border:1px solid #7a7a7a;font-weight:bold;vertical-align:top;">
      Yapılan Önemli İşler/Olaylar
    </td>
    <td colspan="2" style="border:1px solid #7a7a7a;vertical-align:top;">
      <ul style="margin:0;padding-left:18px;">
      {% for e in grouped['important_work'] %}<li>{{ entry_display(e)[1] }}</li>{% endfor %}
      </ul>
    </td>
  </tr>
  {% endif %}

  {# --- DDoS Taşıma --- #}
  {% if grouped['ddos_transfer'] %}
  <tr>
    <td style="background:#dce6f1;border:1px solid #7a7a7a;font-weight:bold;vertical-align:top;">
      DDoS Taşıma
    </td>
    <td colspan="2" style="border:1px solid #7a7a7a;vertical-align:top;">
      <ul style="margin:0;padding-left:18px;">
        {% for e in grouped['ddos_transfer'] %}
        <li>{% if e.occurs_at %}<b>[{{ local_fmt(e.occurs_at) }}]</b> {% endif %}{{ entry_display(e)[1] }}</li>
        {% endfor %}
      </ul>
    </td>
  </tr>
  {% endif %}

  {# --- Bilgi (v0.8.5: ayrı satır; kırmızı + kalın — kalıcı uyarı) --- #}
  {% if grouped['info'] %}
  <tr>
    <td style="background:#dce6f1;border:1px solid #7a7a7a;font-weight:bold;vertical-align:top;">
      Bilgi
    </td>
    <td colspan="2" style="border:1px solid #7a7a7a;vertical-align:top;">
      <ul style="margin:0;padding-left:18px;">
        {% for e in grouped['info'] %}
        <li style="color:#c00000;font-weight:bold;">{{ entry_display(e)[1] }}</li>
        {% endfor %}
      </ul>
    </td>
  </tr>
  {% endif %}

  {# --- L2'ye Eskale Edilen Konu (v0.8.5: ayrı satır, sadece l2_escalation girişi varsa) --- #}
  {% if grouped['l2_escalation'] %}
  <tr>
    <td style="background:#dce6f1;border:1px solid #7a7a7a;font-weight:bold;vertical-align:top;">
      L2'ye Eskale Edilen Konu
    </td>
    <td colspan="2" style="border:1px solid #7a7a7a;vertical-align:top;">
      <ul style="margin:0;padding-left:18px;">
        {% for e in grouped['l2_escalation'] %}
        <li>{{ entry_display(e)[1] }}</li>
        {% endfor %}
      </ul>
    </td>
  </tr>
  {% endif %}

  {# --- Yaklaşan planlı (diğer vardiyalardan taşınan DDoS taşımaları) --- #}
  {% if upcoming %}
  <tr>
    <td style="background:#fff2cc;border:1px solid #7a7a7a;font-weight:bold;vertical-align:top;">
      Yaklaşan Planlı İşler
    </td>
    <td colspan="2" style="border:1px solid #7a7a7a;vertical-align:top;background:#fffbe6;">
      <ul style="margin:0;padding-left:18px;">
        {% for e in upcoming %}
        <li><b>[{{ local_fmt(e.occurs_at) }}]</b> <i>{{ type_label_tr[e.entry_type] }}</i>: {{ (e.body or e.title or '')[:300] }}</li>
        {% endfor %}
      </ul>
    </td>
  </tr>
  {% endif %}

</table>

<p style="color:#6b7280;font-size:11px;margin-top:24px;">
  {{ title }} &middot; {{ shift_start }} &rarr; {{ end }} &middot;
  Vardiya Devir Sistemi tarafından {{ now }} ({{ tz }}) zamanında otomatik oluşturuldu.
</p>

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


def _numeric_totals_dict(entries: List[Entry]) -> dict:
    """HTML tablo şablonu için anahtarlı toplamlar (iys/dhs/sm).

    SM henüz EntryType olarak modellenmiş değil; ileride eklendiğinde
    burada okunmaya hazır. Şimdilik daima 0 (None'a düşer).
    """
    out = {"iys": 0, "dhs": 0, "sm": 0}
    for e in entries:
        if e.entry_type == EntryType.iys and e.numeric_value is not None:
            out["iys"] += int(e.numeric_value)
        elif e.entry_type == EntryType.dhs and e.numeric_value is not None:
            out["dhs"] += int(e.numeric_value)
    return out


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
    tz = ZoneInfo(tz_label)
    now_local = datetime.now(timezone.utc).astimezone(tz).strftime("%Y-%m-%d %H:%M")
    shift_start = _local(shift.started_at)
    end = _local(shift.ended_at) if shift.ended_at else "devam ediyor"
    shift_label = SHIFT_TYPE_LABEL_TR.get(shift.shift_type.value, shift.shift_type.value)

    grouped = _group_by_type(entries)
    totals_numeric = _numeric_totals(entries)
    totals_dict = _numeric_totals_dict(entries)  # HTML şablon için

    # v0.9.5: Rapor başlığında shift'in başladığı tarih Europe/Istanbul
    # cinsinden dd.mm.yyyy formatında görünsün. Örn: "A Vardiyası 22.07.2026"
    started = shift.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    shift_date_dmy = started.astimezone(tz).strftime("%d.%m.%Y")

    if subject_override and subject_override.strip():
        title = subject_override.strip()
    else:
        title = f"{DEFAULT_SUBJECT_PREFIX} - {shift_label} {shift_date_dmy}"

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
        totals=totals_dict,           # yeni: iys/dhs/sm sözlüğü
        totals_numeric=totals_numeric,  # eski (markdown / pdf hâlâ kullanıyor)
        entry_display=_entry_display,
        type_label_tr=ENTRY_TYPE_LABEL_TR,
        local_fmt=_local_short,
        now=now_local, tz=tz_label,
    )
    return title, ai.summary, md, html
