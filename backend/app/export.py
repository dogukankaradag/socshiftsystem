"""Export reports and entries to PDF (reportlab) and CSV.

Turkish character support:
  reportlab'ın varsayılan Helvetica/Times fontları Türkçe karakterleri
  (ş, ı, ğ, İ, vb.) desteklemez ve bu karakterler PDF'te kutu olarak görünür.
  Bu yüzden ilk yüklemede Unicode destekli bir TTF font (DejaVuSans) kaydediyoruz.
  fonts-dejavu-core paketi Dockerfile'da yüklüdür; paket bulunmazsa emniyetli
  şekilde Helvetica'ya düşer.

Uzun içerik:
  Tablo hücrelerinde metin artık kırpılmaz; reportlab `Paragraph` kullanarak
  hücre genişliği içinde otomatik satır sarmalı yapar.
"""
from __future__ import annotations
import csv
import io
import logging
import os
from datetime import timezone
from typing import Iterable
from zoneinfo import ZoneInfo

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors

from .ai import ENTRY_TYPE_LABEL_TR
from .config import get_settings
from .models import Entry, NUMERIC_ENTRY_TYPES, Report

_settings = get_settings()

log = logging.getLogger(__name__)

# Yaygın DejaVu font konumları (Debian/Ubuntu/Alpine sürümleri).
_FONT_CANDIDATES = {
    "regular": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    ],
    "bold": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    ],
}

_BASE_FONT = "Helvetica"
_BOLD_FONT = "Helvetica-Bold"
_UNICODE_FONTS_REGISTERED = False


def _first_existing(paths: list[str]) -> str | None:
    for p in paths:
        if os.path.isfile(p):
            return p
    return None


def _register_unicode_fonts() -> None:
    """DejaVuSans'ı bir kereye mahsus reportlab'a kaydeder."""
    global _BASE_FONT, _BOLD_FONT, _UNICODE_FONTS_REGISTERED
    if _UNICODE_FONTS_REGISTERED:
        return
    _UNICODE_FONTS_REGISTERED = True

    regular = _first_existing(_FONT_CANDIDATES["regular"])
    bold = _first_existing(_FONT_CANDIDATES["bold"])
    if not regular:
        log.warning(
            "DejaVuSans.ttf bulunamadi; PDF'te Turkce karakterler bozuk cikabilir. "
            "Docker imajinda 'fonts-dejavu-core' paketinin kurulu oldugundan emin olun."
        )
        return
    try:
        pdfmetrics.registerFont(TTFont("DejaVuSans", regular))
        _BASE_FONT = "DejaVuSans"
        if bold:
            pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", bold))
            _BOLD_FONT = "DejaVuSans-Bold"
        else:
            # Kalin surum yoksa duzenli fontu kalin rol icin de kullan.
            _BOLD_FONT = "DejaVuSans"
    except Exception:  # noqa: BLE001
        log.exception("Unicode font kaydi basarisiz; varsayilan fonta donuluyor")


def entries_to_csv(entries: Iterable[Entry]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "id", "vardiya_id", "yazar_id", "tur",
        "baslik", "icerik", "sayisal_deger", "planlanan_zaman",
        "kaynak", "olay_id", "olusturulma",
    ])
    for e in entries:
        writer.writerow([
            e.id, e.shift_id, e.author_id,
            ENTRY_TYPE_LABEL_TR.get(e.entry_type, e.entry_type.value),
            e.title or "", e.body or "",
            e.numeric_value if e.numeric_value is not None else "",
            e.occurs_at.isoformat() if e.occurs_at else "",
            e.source or "",
            e.incident_id or "",
            e.created_at.isoformat() if e.created_at else "",
        ])
    # UTF-8 BOM ekliyoruz ki Excel Turkce karakterleri dogru acsin.
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


def _html_escape(text: str) -> str:
    """reportlab Paragraph icin basit HTML escape."""
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def report_to_pdf(report: Report, entries: list[Entry]) -> bytes:
    _register_unicode_fonts()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=report.title,
    )
    styles = getSampleStyleSheet()

    # Turkce uyumlu ozel stiller.
    h1 = ParagraphStyle(
        "TR_H1", parent=styles["Heading1"],
        fontName=_BOLD_FONT, fontSize=18, leading=22,
        textColor=colors.HexColor("#111827"),
    )
    h2 = ParagraphStyle(
        "TR_H2", parent=styles["Heading2"],
        fontName=_BOLD_FONT, fontSize=13, leading=16,
        textColor=colors.HexColor("#111827"),
    )
    body = ParagraphStyle(
        "TR_Body", parent=styles["BodyText"],
        fontName=_BASE_FONT, fontSize=10, leading=13,
    )
    small = ParagraphStyle(
        "TR_Small", parent=body,
        fontSize=8, leading=10, textColor=colors.grey,
    )
    cell = ParagraphStyle(
        "TR_Cell", parent=body,
        fontName=_BASE_FONT, fontSize=8, leading=11,
        wordWrap="CJK",  # uzun kelimeler de kirilsin, hucre disina tasmasin
    )
    cell_header = ParagraphStyle(
        "TR_CellHeader", parent=cell,
        fontName=_BOLD_FONT, textColor=colors.white,
    )

    # Oluşturulma zamanını yerel saate (Europe/Istanbul, GMT+3) çevir.
    tz = ZoneInfo(_settings.scheduler_timezone)
    created_at = report.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    created_local = created_at.astimezone(tz)

    flow = [Paragraph(_html_escape(report.title), h1)]
    flow.append(Paragraph(
        f"Durum: {report.status.value} &nbsp;|&nbsp; "
        f"Oluşturuldu: {created_local:%Y-%m-%d %H:%M} (GMT+3)",
        small,
    ))
    flow.append(Spacer(1, 8))
    flow.append(Paragraph("Yönetici Özeti", h2))
    summary_text = _html_escape(report.summary or "(özet yok)").replace("\n", "<br/>")
    flow.append(Paragraph(summary_text, body))
    flow.append(Spacer(1, 8))

    if entries:
        flow.append(Paragraph("Girişler", h2))

        # Başlık satırı
        data = [[
            Paragraph("#", cell_header),
            Paragraph("Tür", cell_header),
            Paragraph("Planlanan", cell_header),
            Paragraph("İçerik / Sayı", cell_header),
            Paragraph("Yazar", cell_header),
        ]]

        for e in entries:
            tur = ENTRY_TYPE_LABEL_TR.get(e.entry_type, e.entry_type.value)
            if e.occurs_at is not None:
                occ = e.occurs_at
                if occ.tzinfo is None:
                    occ = occ.replace(tzinfo=timezone.utc)
                planlanan = occ.astimezone(tz).strftime("%d.%m %H:%M")
            else:
                planlanan = "—"
            if e.entry_type in NUMERIC_ENTRY_TYPES and e.numeric_value is not None:
                icerik_raw = f"Adet: {e.numeric_value}"
            else:
                # Artik kirpmiyoruz; Paragraph otomatik satir sarmalayacak.
                icerik_raw = (e.body or e.title or "").strip() or "—"
            if e.source:
                icerik_raw = f"[{e.source}] " + icerik_raw

            icerik_html = _html_escape(icerik_raw).replace("\n", "<br/>")
            yazar = e.author.full_name if e.author else "—"

            data.append([
                Paragraph(str(e.id), cell),
                Paragraph(_html_escape(tur), cell),
                Paragraph(_html_escape(planlanan), cell),
                Paragraph(icerik_html, cell),
                Paragraph(_html_escape(yazar), cell),
            ])

        # Toplam yazilabilir genislik: A4 210mm - 2*18mm kenar = 174mm.
        col_widths = [10 * mm, 30 * mm, 24 * mm, 80 * mm, 30 * mm]

        t = Table(data, repeatRows=1, colWidths=col_widths)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, -1), _BASE_FONT),
            ("FONTNAME", (0, 0), (-1, 0), _BOLD_FONT),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        flow.append(t)

    doc.build(flow)
    return buf.getvalue()
