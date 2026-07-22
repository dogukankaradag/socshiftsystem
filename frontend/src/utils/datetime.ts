// v0.9.4: Merkezi datetime yardımcıları — her yerde tr-TR + Europe/Istanbul.
// Kullanıcı tarayıcısının timezone'una bakılmaz; sistem hep Türkiye saatinde.

const TZ = 'Europe/Istanbul';
const LOCALE = 'tr-TR';

/** ISO string → "dd.mm.yyyy HH:MM" (Europe/Istanbul) */
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(LOCALE, {
    timeZone: TZ,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** ISO string → "dd.mm HH:MM" (Europe/Istanbul) — kısa (yıl yok) */
export function fmtShort(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(LOCALE, {
    timeZone: TZ,
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** ISO string → "dd.mm.yyyy" (Europe/Istanbul, sadece tarih) */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString(LOCALE, {
    timeZone: TZ,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

/**
 * "YYYY-MM-DDTHH:mm" (yerel Europe/Istanbul) girişini UTC ISO string'e çevirir.
 * `<input type="datetime-local">` output'unu backend'e göndermek için kullanılır.
 * Europe/Istanbul sabit +03:00 (DST yok).
 */
export function localInputToUtcIso(v: string): string | null {
  if (!v) return null;
  const iso = v.length === 16 ? `${v}:00+03:00` : `${v}+03:00`;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  return d.toISOString();
}

/**
 * UTC ISO string → `<input type="datetime-local">` value ("YYYY-MM-DDTHH:mm")
 * Europe/Istanbul saatinde gösterilecek şekilde.
 */
export function isoToLocalInput(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  // Europe/Istanbul = UTC+3 sabit (DST yok)
  const tr = new Date(d.getTime() + 3 * 60 * 60 * 1000);
  return tr.toISOString().slice(0, 16);
}

/** TZ label — footer/report metadata için */
export const TZ_LABEL = TZ;
