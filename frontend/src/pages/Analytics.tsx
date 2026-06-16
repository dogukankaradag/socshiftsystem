import { useEffect, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  api,
  AnalyticsOverview,
  ENTRY_TYPE_LABEL,
  EntryType,
  NUMERIC_ENTRY_TYPES,
} from '../api/client';

export default function Analytics() {
  const [data, setData] = useState<AnalyticsOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get('/analytics/overview')
      .then((r) => setData(r.data))
      .catch((e) => setError(e?.response?.data?.detail || 'Yükleme başarısız'));
  }, []);

  if (error) return <div className="text-red-600">{error}</div>;
  if (!data) return <div className="text-gray-500">Yükleniyor…</div>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Analitik</h1>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card ring-1 ring-gray-200">
          <div className="text-sm text-gray-500">Toplam giriş</div>
          <div className="text-3xl font-semibold mt-1">{data.total_entries}</div>
        </div>
        <div className="card ring-1 ring-orange-200 text-orange-700">
          <div className="text-sm text-gray-500">Açık olaylar</div>
          <div className="text-3xl font-semibold mt-1">{data.open_incidents}</div>
        </div>
        <div className="card ring-1 ring-blue-200 text-blue-700">
          <div className="text-sm text-gray-500">Planlı / yaklaşan</div>
          <div className="text-3xl font-semibold mt-1">{data.upcoming_count}</div>
        </div>
      </div>

      <div className="card">
        <h2 className="font-semibold mb-3">Son 30 Gün — Tür Bazlı Toplamlar</h2>
        <p className="text-xs text-gray-500 mb-3">
          DHS ve İYS için "toplam" alanı son 30 günde işlenen toplam case sayısını
          (sayısal değerlerin toplamı) gösterir. Diğer türler için toplam = kayıt sayısıdır.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {data.totals_30d.map((t) => {
            const isNumeric = NUMERIC_ENTRY_TYPES.includes(t.entry_type as EntryType);
            return (
              <div
                key={t.entry_type}
                className={`rounded-lg border p-3 ${
                  isNumeric
                    ? 'bg-blue-50 border-blue-200'
                    : 'bg-gray-50 border-gray-200'
                }`}
              >
                <div className="text-xs uppercase text-gray-500 truncate">
                  {ENTRY_TYPE_LABEL[t.entry_type as EntryType] || t.entry_type}
                </div>
                <div className="text-2xl font-semibold text-gray-900 mt-1">
                  {t.total}
                  {isNumeric && (
                    <span className="text-xs font-normal text-gray-500 ml-1">case</span>
                  )}
                </div>
                <div className="text-xs text-gray-500 mt-1">kayıt: {t.count}</div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="card">
        <h2 className="font-semibold mb-2">Günlük Giriş Sayısı (son 14 gün)</h2>
        <div className="h-64">
          <ResponsiveContainer>
            <BarChart data={data.trend_14d}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" tickFormatter={(d) => d.slice(5)} fontSize={11} />
              <YAxis allowDecimals={false} fontSize={11} />
              <Tooltip />
              <Legend />
              <Bar dataKey="total" fill="#2563eb" name="Toplam" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="card">
        <h2 className="font-semibold mb-2">Türe Göre Giriş Dağılımı (tüm zaman)</h2>
        {data.entries_by_type.length === 0 ? (
          <div className="text-gray-500 text-sm">Henüz giriş yok.</div>
        ) : (
          <ul className="divide-y divide-gray-100">
            {data.entries_by_type.map((t) => (
              <li
                key={t.entry_type}
                className="py-2 flex justify-between text-sm"
              >
                <span className="text-gray-800">
                  {ENTRY_TYPE_LABEL[t.entry_type as EntryType] || t.entry_type}
                </span>
                <span className="text-gray-500">{t.count}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* v0.6.1: Çağrı yanıtlayan operatör dağılımı (son 30 gün) */}
      <div className="card">
        <h2 className="font-semibold mb-2">
          Telefon Çağrıları — Kullanıcı Dağılımı (son 30 gün)
        </h2>
        <p className="text-xs text-gray-500 mb-3">
          Hangi operatör kaç telefon çağrısı yanıtladı? "Arayanlar" türündeki
          girişlerin author bazlı sayımı. Performans metriği olarak kullanılır.
        </p>
        {!data.callers_by_user_30d || data.callers_by_user_30d.length === 0 ? (
          <div className="text-gray-500 text-sm">
            Son 30 günde "Arayanlar" girişi yok.
          </div>
        ) : (
          <ul className="divide-y divide-gray-100">
            {data.callers_by_user_30d.map((c) => (
              <li
                key={c.user_id}
                className="py-2 flex justify-between text-sm"
              >
                <span className="text-gray-800">{c.user_name}</span>
                <span className="text-gray-500">
                  {c.count} çağrı
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="card">
        <h2 className="font-semibold mb-2">Tekrarlayan Konular (son 30 gün)</h2>
        {data.recurring_titles.length === 0 ? (
          <div className="text-gray-500 text-sm">Tekrarlayan konu tespit edilmedi.</div>
        ) : (
          <ul className="divide-y divide-gray-100">
            {data.recurring_titles.map((t) => (
              <li key={t.title} className="py-2 flex justify-between text-sm">
                <span className="text-gray-800 truncate max-w-[70%]">{t.title}</span>
                <span className="text-gray-500">{t.count}×</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
