import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  api,
  AnalyticsOverview,
  ENTRY_TYPE_LABEL,
  Entry,
  NUMERIC_ENTRY_TYPES,
  Shift,
  SHIFT_TYPE_LABEL,
} from '../api/client';

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

export default function Dashboard() {
  const [shift, setShift] = useState<Shift | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [upcoming, setUpcoming] = useState<Entry[]>([]);
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const s = await api.get('/shifts/current');
      setShift(s.data);
      const [e, u, o] = await Promise.all([
        api.get('/entries', { params: { shift_id: s.data.id, limit: 20 } }),
        api.get('/entries/upcoming', { params: { limit: 10 } }),
        api.get('/analytics/overview'),
      ]);
      setEntries(e.data);
      setUpcoming(u.data);
      setOverview(o.data);
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

  if (loading && !shift) return <div className="text-gray-500">Panel yükleniyor…</div>;
  if (error) return <div className="text-red-600">{error}</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Aktif Vardiya</h1>
          {shift && (
            <p className="text-sm text-gray-500">
              {SHIFT_TYPE_LABEL[shift.shift_type]} · başlangıç{' '}
              {new Date(shift.started_at).toLocaleString('tr-TR')} · {shift.entry_count} giriş
            </p>
          )}
        </div>
        <Link to="/new" className="btn-primary">
          + Yeni Giriş
        </Link>
      </div>

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
          <h2 className="font-semibold text-gray-900 mb-3">Yaklaşan Planlı İşler</h2>
          <ul className="divide-y divide-gray-100">
            {upcoming.map((e) => (
              <li key={e.id} className="py-2 flex gap-3 items-start">
                <span className="text-xs font-semibold text-blue-700 bg-blue-50 rounded px-2 py-0.5 whitespace-nowrap">
                  {e.occurs_at ? fmtLocal(e.occurs_at) : '—'}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-xs uppercase text-gray-500">
                    {ENTRY_TYPE_LABEL[e.entry_type]}
                  </div>
                  <div className="text-sm text-gray-700 line-clamp-2">
                    {entryDisplayBody(e)}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold text-gray-900">Son girişler</h2>
          <Link to="/reports" className="text-sm text-brand-700 hover:underline">
            Rapor oluştur →
          </Link>
        </div>
        {entries.length === 0 ? (
          <div className="text-gray-500 text-sm">
            Henüz giriş yok. Bir kayıt ekleyerek başlayın.
          </div>
        ) : (
          <ul className="divide-y divide-gray-100">
            {entries.map((e) => (
              <li key={e.id} className="py-3 flex gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs uppercase text-gray-500">
                      {ENTRY_TYPE_LABEL[e.entry_type]}
                    </span>
                    {e.occurs_at && (
                      <span className="text-xs font-semibold text-blue-700 bg-blue-50 rounded px-2 py-0.5">
                        Planlı: {fmtLocal(e.occurs_at)}
                      </span>
                    )}
                    {e.source && (
                      <span className="text-xs text-gray-500 bg-gray-100 rounded px-1.5 py-0.5">
                        {e.source}
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-gray-700 whitespace-pre-wrap line-clamp-3">
                    {entryDisplayBody(e)}
                  </div>
                  <div className="text-xs text-gray-400 mt-1">
                    {e.author_name || `#${e.author_id}`} ·{' '}
                    {new Date(e.created_at).toLocaleString('tr-TR')}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
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
      ? 'ring-red-200 text-red-700'
      : tone === 'warn'
      ? 'ring-orange-200 text-orange-700'
      : tone === 'info'
      ? 'ring-blue-200 text-blue-700'
      : 'ring-gray-200 text-gray-900';
  return (
    <div className={`card ring-1 ${ring}`}>
      <div className="text-sm text-gray-500">{label}</div>
      <div className="text-3xl font-semibold mt-1">{value}</div>
    </div>
  );
}
