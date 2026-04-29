import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  api,
  ENTRY_TYPE_LABEL,
  EntryType,
  NUMERIC_ENTRY_TYPES,
} from '../api/client';

const TYPES: EntryType[] = [
  'ddos_transfer',
  'info',
  'important_work',
  'l2_escalation',
  'callers',
  'dhs',
  'iys',
];

// "YYYY-MM-DDTHH:mm" (yerel, GMT+3) girişini UTC ISO string'e çevir.
// datetime-local input'u tarayıcının yerel saatinde döner; biz bunu operatörün
// Europe/Istanbul saati olarak kabul edip +03:00 offset'i ile ISO string'e
// dönüştürüyoruz. Böylece backend her zaman tutarlı UTC alır.
function localInputToUtcIso(v: string): string | null {
  if (!v) return null;
  // v örn: "2026-04-21T14:30"
  // GMT+3 olarak yorumlayıp UTC'ye çevir:
  const iso = v.length === 16 ? `${v}:00+03:00` : `${v}+03:00`;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  return d.toISOString();
}

export default function NewEntry() {
  const nav = useNavigate();
  const [entryType, setEntryType] = useState<EntryType>('ddos_transfer');
  const [body, setBody] = useState('');
  const [numericValue, setNumericValue] = useState<string>('');
  const [occursAt, setOccursAt] = useState<string>(''); // "YYYY-MM-DDTHH:mm" yerel
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isNumeric = NUMERIC_ENTRY_TYPES.includes(entryType);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (isNumeric) {
      const n = Number(numericValue);
      if (!Number.isFinite(n) || n < 0 || !Number.isInteger(n)) {
        setError('Lütfen geçerli bir adet (tam sayı) girin.');
        return;
      }
    } else if (!body.trim()) {
      setError('Lütfen detay alanını doldurun.');
      return;
    }

    setSubmitting(true);
    try {
      await api.post('/entries', {
        entry_type: entryType,
        title: null,
        body: isNumeric ? '' : body.trim(),
        numeric_value: isNumeric ? Number(numericValue) : null,
        occurs_at: localInputToUtcIso(occursAt),
      });
      nav('/');
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Kayıt başarısız oldu');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-4">
      <h1 className="text-2xl font-semibold text-gray-900 dark:text-slate-100">Yeni Vardiya Girişi</h1>
      <form onSubmit={onSubmit} className="card space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label">Tür</label>
            <select
              className="input"
              value={entryType}
              onChange={(e) => {
                const next = e.target.value as EntryType;
                setEntryType(next);
                if (NUMERIC_ENTRY_TYPES.includes(next)) {
                  setBody('');
                } else {
                  setNumericValue('');
                }
              }}
            >
              {TYPES.map((t) => (
                <option key={t} value={t}>
                  {ENTRY_TYPE_LABEL[t]}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Planlanan Zaman (opsiyonel)</label>
            <input
              type="datetime-local"
              className="input"
              value={occursAt}
              onChange={(e) => setOccursAt(e.target.value)}
            />
            <p className="text-xs text-gray-500 dark:text-slate-400 mt-1">
              Olay ileride bir tarihte gerçekleşecekse saat (GMT+3) seçin.
              Tarih gelene kadar tüm vardiya raporlarında hatırlatılır.
            </p>
          </div>
        </div>

        {isNumeric ? (
          <div>
            <label className="label">Adet / Sayı</label>
            <input
              type="number"
              min={0}
              step={1}
              className="input"
              value={numericValue}
              onChange={(e) => setNumericValue(e.target.value)}
              required
              placeholder="örn. 11"
            />
            <p className="text-xs text-gray-500 dark:text-slate-400 mt-1">
              Bu vardiyada işlem yapılan {ENTRY_TYPE_LABEL[entryType]} case sayısını girin.
            </p>
          </div>
        ) : (
          <div>
            <label className="label">Detay</label>
            <textarea
              className="input min-h-[160px]"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              required
              placeholder="Neler oldu, hangi aksiyonlar alındı, sonraki adımlar…"
            />
          </div>
        )}

        {error && <div className="text-sm text-red-600 dark:text-red-400">{error}</div>}
        <div className="flex gap-2 justify-end">
          <button type="button" className="btn-ghost" onClick={() => nav(-1)}>
            İptal
          </button>
          <button type="submit" disabled={submitting} className="btn-primary">
            {submitting ? 'Kaydediliyor…' : 'Kaydet'}
          </button>
        </div>
      </form>
    </div>
  );
}
