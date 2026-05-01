import { FormEvent, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  api,
  AnalyticsOverview,
  ENTRY_TYPE_LABEL,
  Entry,
  EntryType,
  NUMERIC_ENTRY_TYPES,
  Shift,
  SHIFT_TYPE_LABEL,
} from '../api/client';
import { useAuth } from '../auth/AuthContext';
import ResolveScheduledModal from '../components/ResolveScheduledModal';

function entryDisplayBody(e: Entry): string {
  if (NUMERIC_ENTRY_TYPES.includes(e.entry_type) && e.numeric_value != null) {
    return `Adet: ${e.numeric_value}`;
  }
  return e.body || e.title || '';
}

function fmtLocal(iso: string): string {
  return new Date(iso).toLocaleString('tr-TR', {
    timeZone: 'Europe/Istanbul',
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// "2026-04-28T14:35:00.000Z" -> "2026-04-28T17:35" (Europe/Istanbul, datetime-local)
function isoToLocalInput(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  // Europe/Istanbul = UTC + 3 (sabit). DST yok.
  const tr = new Date(d.getTime() + 3 * 60 * 60 * 1000);
  return tr.toISOString().slice(0, 16);
}

function localInputToUtcIso(v: string): string | null {
  if (!v) return null;
  const iso = v.length === 16 ? `${v}:00+03:00` : `${v}+03:00`;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  return d.toISOString();
}

export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  // Tüm operatörler birbirinin girişini düzenleyebilir/silebilir
  // (vardiya devri sırasında plan değişiklikleri için). Her aksiyon
  // audit log'a yazıldığı için sorumluluk korunur.
  const canModifyAny = !!user;

  const [shift, setShift] = useState<Shift | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [upcoming, setUpcoming] = useState<Entry[]>([]);
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [pendingCount, setPendingCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Entry | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  // Bekleyen kararlar modalı: 'banner' = panelden açıldı, 'report' = "Rapor
  // oluştur" linkinden açıldı (kararlar bitince Reports sayfasına yönlendir).
  const [resolveOpen, setResolveOpen] = useState<null | 'banner' | 'report'>(null);

  async function load() {
    setLoading(true);
    try {
      const s = await api.get('/shifts/current');
      setShift(s.data);
      const [e, u, o, p] = await Promise.all([
        // Panel sade kalsın diye zamanı geçmiş planlamaları gizliyoruz.
        // Sadece occurs_at boş olanlar + henüz zamanı gelmemiş olanlar görünür.
        // Analitik sayfası ham veriyi kullanmaya devam eder. Bekleyen
        // (geçmiş planlı DDoS Taşıma + Bilgi) girişler ayrı banner'da gösterilir.
        api.get('/entries', {
          params: { shift_id: s.data.id, limit: 20, hide_past_scheduled: true },
        }),
        api.get('/entries/upcoming', { params: { limit: 10 } }),
        api.get('/analytics/overview'),
        api.get<Entry[]>('/entries/pending-resolution'),
      ]);
      setEntries(e.data);
      setUpcoming(u.data);
      setOverview(o.data);
      setPendingCount(p.data.length);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Yüklenemedi');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const interval = setInterval(load, 30000); // 30 sn'de bir tazele
    return () => clearInterval(interval);
  }, []);

  async function deleteEntry(id: number) {
    if (!confirm('Bu girişi silmek istiyor musunuz? İşlem geri alınamaz.')) return;
    setBusyId(id);
    try {
      await api.delete(`/entries/${id}`);
      await load();
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Silme başarısız');
    } finally {
      setBusyId(null);
    }
  }

  function canEdit(_e: Entry): boolean {
    return canModifyAny;
  }

  if (loading && !shift) return <div className="text-gray-500 dark:text-slate-400">Panel yükleniyor…</div>;
  if (error) return <div className="text-red-600 dark:text-red-400">{error}</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-slate-100">Aktif Vardiya</h1>
          {shift && (
            <p className="text-sm text-gray-500 dark:text-slate-400">
              {SHIFT_TYPE_LABEL[shift.shift_type]} · başlangıç{' '}
              {new Date(shift.started_at).toLocaleString('tr-TR')} · {shift.entry_count} giriş
            </p>
          )}
        </div>
        <Link to="/new" className="btn-primary">
          + Yeni Giriş
        </Link>
      </div>

      {pendingCount > 0 && (
        <div className="card flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-l-4 border-amber-400 dark:border-amber-500">
          <div className="flex-1">
            <div className="font-semibold text-amber-900 dark:text-amber-200">
              {pendingCount} bekleyen karar var
            </div>
            <p className="text-xs text-gray-600 dark:text-slate-300 mt-0.5">
              Bir önceki vardiyadan kalmış, tarihi geçmiş DDoS Taşıma ve Bilgi
              girişleri var. Yeni vardiya raporundan önce her biri için karar verin
              (tamamlandı / yeni tarih / tarih belli değil).
            </p>
          </div>
          <button
            type="button"
            className="btn-primary text-sm shrink-0"
            onClick={() => setResolveOpen('banner')}
          >
            Karar Ver
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard label="Bu vardiya girişleri" value={shift?.entry_count ?? 0} />
        <StatCard label="Açık olaylar" value={overview?.open_incidents ?? 0} tone="warn" />
        <StatCard
          label="Planlı / yaklaşan"
          value={overview?.upcoming_count ?? 0}
          tone="info"
        />
        <StatCard label="Toplam giriş" value={overview?.total_entries ?? 0} />
      </div>

      {upcoming.length > 0 && (
        <div className="card">
          <h2 className="font-semibold text-gray-900 dark:text-slate-100 mb-3">Yaklaşan Planlı İşler</h2>
          <ul className="divide-y divide-gray-100 dark:divide-slate-700">
            {upcoming.map((e) => (
              <li key={e.id} className="py-2 flex gap-3 items-start">
                <span className="text-xs font-semibold text-blue-700 bg-blue-50 rounded px-2 py-0.5 whitespace-nowrap dark:text-brand-400 dark:bg-slate-700">
                  {e.occurs_at ? fmtLocal(e.occurs_at) : '—'}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-xs uppercase text-gray-500 dark:text-slate-400">
                    {ENTRY_TYPE_LABEL[e.entry_type]}
                  </div>
                  <div className="text-sm text-gray-700 dark:text-slate-200 line-clamp-2">
                    {entryDisplayBody(e)}
                  </div>
                </div>
                {canEdit(e) && (
                  <div className="flex gap-1 shrink-0">
                    <button
                      className="text-xs text-gray-600 hover:text-brand-700 dark:text-slate-300 dark:hover:text-brand-400"
                      onClick={() => setEditing(e)}
                    >
                      Düzenle
                    </button>
                    {canModifyAny && (
                      <button
                        className="text-xs text-red-600 hover:underline dark:text-red-400"
                        disabled={busyId === e.id}
                        onClick={() => deleteEntry(e.id)}
                      >
                        Sil
                      </button>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="card">
        <div className="flex items-start justify-between mb-3 gap-3">
          <div>
            <h2 className="font-semibold text-gray-900 dark:text-slate-100">Aktif girişler</h2>
            <p className="text-xs text-gray-500 dark:text-slate-400">
              Yalnızca zamanı henüz gelmemiş veya zaman bilgisi girilmemiş girişler
              görünür. Geçmiş planlamalar Analitik sayfasında sayılmaya devam eder.
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              // Bekleyen karar varsa önce modalı aç; modal "tüm kararlar
              // bitti" sinyalini verirse Reports sayfasına yönlendiririz.
              if (pendingCount > 0) {
                setResolveOpen('report');
              } else {
                navigate('/reports');
              }
            }}
            className="text-sm text-brand-700 hover:underline dark:text-brand-400 shrink-0 mt-0.5 bg-transparent border-0 cursor-pointer p-0"
          >
            Rapor oluştur →
          </button>
        </div>
        {entries.length === 0 ? (
          <div className="text-gray-500 dark:text-slate-400 text-sm">
            Henüz giriş yok. Bir kayıt ekleyerek başlayın.
          </div>
        ) : (
          <ul className="divide-y divide-gray-100 dark:divide-slate-700">
            {entries.map((e) => (
              <li key={e.id} className="py-3 flex gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs uppercase text-gray-500 dark:text-slate-400">
                      {ENTRY_TYPE_LABEL[e.entry_type]}
                    </span>
                    {e.occurs_at && (
                      <span className="text-xs font-semibold text-blue-700 bg-blue-50 rounded px-2 py-0.5 dark:text-brand-400 dark:bg-slate-700">
                        Planlı: {fmtLocal(e.occurs_at)}
                      </span>
                    )}
                    {e.source && (
                      <span className="text-xs text-gray-500 bg-gray-100 rounded px-1.5 py-0.5 dark:text-slate-300 dark:bg-slate-700">
                        {e.source}
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-gray-700 dark:text-slate-200 whitespace-pre-wrap line-clamp-3">
                    {entryDisplayBody(e)}
                  </div>
                  <div className="text-xs text-gray-400 dark:text-slate-500 mt-1">
                    {e.author_name || `#${e.author_id}`} ·{' '}
                    {new Date(e.created_at).toLocaleString('tr-TR')}
                  </div>
                </div>
                <div className="flex flex-col gap-1 shrink-0 items-end">
                  {canEdit(e) && (
                    <button
                      className="text-xs text-gray-600 hover:text-brand-700 dark:text-slate-300 dark:hover:text-brand-400"
                      onClick={() => setEditing(e)}
                      disabled={busyId === e.id}
                    >
                      Düzenle
                    </button>
                  )}
                  {canModifyAny && (
                    <button
                      className="text-xs text-red-600 hover:underline dark:text-red-400"
                      onClick={() => deleteEntry(e.id)}
                      disabled={busyId === e.id}
                    >
                      Sil
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {editing && (
        <EntryEditModal
          entry={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}

      {resolveOpen && (
        <ResolveScheduledModal
          onClose={() => {
            setResolveOpen(null);
            // Modal kapanırken yeni sayım için yeniden çek.
            load();
          }}
          onChange={load}
          onAllResolved={() => {
            // Kararlar bittikten sonra "Rapor oluştur"dan açılmışsa
            // doğrudan Reports sayfasına götür.
            if (resolveOpen === 'report') {
              setResolveOpen(null);
              navigate('/reports');
            }
          }}
        />
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: 'warn' | 'danger' | 'info';
}) {
  const ring =
    tone === 'danger'
      ? 'ring-red-200 text-red-700 dark:ring-red-900 dark:text-red-300'
      : tone === 'warn'
      ? 'ring-orange-200 text-orange-700 dark:ring-orange-900 dark:text-orange-300'
      : tone === 'info'
      ? 'ring-blue-200 text-blue-700 dark:ring-blue-900 dark:text-brand-400'
      : 'ring-gray-200 text-gray-900 dark:ring-slate-700 dark:text-slate-100';
  return (
    <div className={`card ring-1 ${ring}`}>
      <div className="text-sm text-gray-500 dark:text-slate-400">{label}</div>
      <div className="text-3xl font-semibold mt-1">{value}</div>
    </div>
  );
}

function EntryEditModal({
  entry,
  onClose,
  onSaved,
}: {
  entry: Entry;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isNumeric = NUMERIC_ENTRY_TYPES.includes(entry.entry_type as EntryType);
  const [title, setTitle] = useState(entry.title || '');
  const [body, setBody] = useState(entry.body || '');
  const [numericValue, setNumericValue] = useState<string>(
    entry.numeric_value != null ? String(entry.numeric_value) : '',
  );
  const [occursAt, setOccursAt] = useState(isoToLocalInput(entry.occurs_at));
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setSaving(true);
    try {
      const payload: any = {
        title: title || null,
      };
      if (isNumeric) {
        const n = parseInt(numericValue, 10);
        if (isNaN(n) || n < 0) {
          setErr('Geçerli bir sayı girin.');
          setSaving(false);
          return;
        }
        payload.numeric_value = n;
      } else {
        payload.body = body;
      }
      // occurs_at: '' -> null (planlamayı kaldır), dolu -> UTC ISO
      payload.occurs_at = occursAt ? localInputToUtcIso(occursAt) : null;

      await api.patch(`/entries/${entry.id}`, payload);
      onSaved();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Güncelleme başarısız');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <form
        onSubmit={submit}
        className="bg-white dark:bg-slate-800 rounded-lg shadow-xl w-full max-w-lg p-5 space-y-3"
      >
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-gray-900 dark:text-slate-100">
            Girişi Düzenle — {ENTRY_TYPE_LABEL[entry.entry_type]}
          </h2>
          <button type="button" className="text-gray-500 dark:text-slate-400" onClick={onClose}>
            ✕
          </button>
        </div>

        <div>
          <label className="label">Başlık (opsiyonel)</label>
          <input
            className="input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={255}
          />
        </div>

        {isNumeric ? (
          <div>
            <label className="label">Adet</label>
            <input
              type="number"
              min={0}
              className="input"
              value={numericValue}
              onChange={(e) => setNumericValue(e.target.value)}
              required
            />
          </div>
        ) : (
          <div>
            <label className="label">Detay</label>
            <textarea
              className="input min-h-[120px]"
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </div>
        )}

        <div>
          <label className="label">Planlı zaman (GMT+3, opsiyonel)</label>
          <div className="flex gap-2">
            <input
              type="datetime-local"
              className="input"
              value={occursAt}
              onChange={(e) => setOccursAt(e.target.value)}
            />
            {occursAt && (
              <button
                type="button"
                className="btn-ghost text-xs"
                onClick={() => setOccursAt('')}
              >
                Planlamayı kaldır
              </button>
            )}
          </div>
          <p className="text-xs text-gray-500 dark:text-slate-400 mt-1">
            Tarih değiştirilirse hatırlatma yeniden gönderilir.
          </p>
        </div>

        {err && <div className="text-sm text-red-600 dark:text-red-400">{err}</div>}

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-ghost" onClick={onClose}>
            İptal
          </button>
          <button type="submit" className="btn-primary" disabled={saving}>
            {saving ? 'Kaydediliyor…' : 'Kaydet'}
          </button>
        </div>
      </form>
    </div>
  );
}
