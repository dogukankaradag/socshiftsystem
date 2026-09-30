// v0.9.17+v0.9.18: Zaman aralığı seçici + aylık dağılım + telefon çağrıları
// bazlı kişi performansı. Dark mode uyumlu tüm renkler.
import { useEffect, useState } from 'react';
import {
  Bar, BarChart, CartesianGrid, Cell,
  Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend,
} from 'recharts';
import {
  api, ENTRY_TYPE_LABEL, EntryType, extractApiError, NUMERIC_ENTRY_TYPES,
} from '../api/client';

type RangeKey = 'week' | 'month' | '3month' | '6month' | 'year' | 'all';

const RANGE_LABEL: Record<RangeKey, string> = {
  week: 'Haftalık',
  month: 'Aylık',
  '3month': '3 Aylık',
  '6month': '6 Aylık',
  year: 'Yıllık',
  all: 'Tüm Zamanlar',
};

interface TypeCountItem {
  entry_type: EntryType;
  count: number;
  numeric_total: number;
}
interface MonthlyBucket { month: string; total: number; }
interface UserPerfItem {
  user_id: number;
  user_name: string;
  total_entries: number;
  by_type: Record<string, number>;
}
interface CallerStat { user_id: number; user_name: string; count: number; }
interface RangedAnalytics {
  range: string;
  start_date: string | null;
  end_date: string;
  total_entries: number;
  open_incidents: number;
  upcoming_count: number;
  entries_by_type: TypeCountItem[];
  monthly_distribution: MonthlyBucket[];
  per_user: UserPerfItem[];
  top_callers: CallerStat[];
  recurring_titles: Array<{ title: string; count: number }>;
}

const PIE_COLORS = [
  '#2563eb', '#dc2626', '#16a34a', '#f59e0b', '#7c3aed',
  '#0891b2', '#db2777', '#65a30d',
];

export default function Analytics() {
  const [range, setRange] = useState<RangeKey>('month');
  const [data, setData] = useState<RangedAnalytics | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .get<RangedAnalytics>('/analytics/ranged', { params: { range } })
      .then((r) => setData(r.data))
      .catch((e) => setError(extractApiError(e, 'Analitik yüklenemedi')))
      .finally(() => setLoading(false));
  }, [range]);

  const dateRangeLabel = !data
    ? ''
    : data.start_date
    ? `${new Date(data.start_date).toLocaleDateString('tr-TR', { timeZone: 'Europe/Istanbul' })} → bugün`
    : 'Tüm zamanlar';

  const totalCallers = data?.top_callers.reduce((s, c) => s + c.count, 0) || 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-slate-100">Analitik</h1>
          <p className="text-xs text-gray-500 dark:text-slate-400">{dateRangeLabel}</p>
        </div>
        <div className="flex gap-2 items-center">
          <label className="text-sm text-gray-600 dark:text-slate-300">Aralık:</label>
          <select
            className="input py-1 text-sm"
            value={range}
            onChange={(e) => setRange(e.target.value as RangeKey)}
          >
            {(Object.keys(RANGE_LABEL) as RangeKey[]).map((k) => (
              <option key={k} value={k}>{RANGE_LABEL[k]}</option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <div className="card border-l-4 border-red-400 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}
      {loading && !data && (
        <div className="text-gray-500 dark:text-slate-400 text-sm">Yükleniyor…</div>
      )}

      {data && (
        <>
          {/* Üst özet kartları */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label={`Toplam giriş (${RANGE_LABEL[range]})`} value={data.total_entries} />
            <StatCard label="Açık olaylar" value={data.open_incidents} tone="warn" />
            <StatCard label="Planlı / yaklaşan" value={data.upcoming_count} tone="info" />
            <StatCard label="Aktif kullanıcı" value={data.per_user.length} tone="info" />
          </div>

          {/* Aylık dağılım */}
          <div className="card">
            <h2 className="font-semibold mb-3 text-gray-900 dark:text-slate-100">
              Aylık Giriş Dağılımı
            </h2>
            {data.monthly_distribution.length === 0 ? (
              <div className="text-sm text-gray-500 dark:text-slate-400">Bu aralıkta veri yok.</div>
            ) : (
              <div className="h-72">
                <ResponsiveContainer>
                  <BarChart data={data.monthly_distribution}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#94a3b8" strokeOpacity={0.3} />
                    <XAxis dataKey="month" fontSize={11} stroke="#64748b" />
                    <YAxis allowDecimals={false} fontSize={11} stroke="#64748b" />
                    <Tooltip
                      contentStyle={{
                        background: 'rgba(30, 41, 59, 0.95)',
                        border: '1px solid #475569',
                        borderRadius: '6px',
                        color: '#f1f5f9',
                      }}
                    />
                    <Legend wrapperStyle={{ color: '#64748b' }} />
                    <Bar dataKey="total" fill="#2563eb" name="Toplam giriş" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          {/* Tür bazlı dağılım — kart + pie */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="card">
              <h2 className="font-semibold mb-3 text-gray-900 dark:text-slate-100">
                Tür Bazlı Toplamlar
              </h2>
              <div className="grid grid-cols-2 gap-2">
                {data.entries_by_type.map((t) => {
                  const isNumeric = NUMERIC_ENTRY_TYPES.includes(t.entry_type as EntryType);
                  return (
                    <div
                      key={t.entry_type}
                      className={`rounded-lg border p-2 ${
                        isNumeric
                          ? 'bg-blue-50 border-blue-200 dark:bg-slate-700 dark:border-slate-600'
                          : 'bg-gray-50 border-gray-200 dark:bg-slate-700/50 dark:border-slate-600'
                      }`}
                    >
                      <div className="text-xs uppercase text-gray-500 dark:text-slate-400 truncate">
                        {ENTRY_TYPE_LABEL[t.entry_type as EntryType] || t.entry_type}
                      </div>
                      <div className="text-xl font-semibold text-gray-900 dark:text-slate-100">
                        {isNumeric ? t.numeric_total : t.count}
                        {isNumeric && (
                          <span className="text-xs font-normal text-gray-500 dark:text-slate-400 ml-1">
                            case
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-gray-500 dark:text-slate-400">
                        kayıt: {t.count}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="card">
              <h2 className="font-semibold mb-3 text-gray-900 dark:text-slate-100">
                Tür Yüzdesi (kayıt sayısı)
              </h2>
              {data.total_entries === 0 ? (
                <div className="text-sm text-gray-500 dark:text-slate-400">
                  Bu aralıkta veri yok.
                </div>
              ) : (
                <div className="h-64">
                  <ResponsiveContainer>
                    <PieChart>
                      <Pie
                        data={data.entries_by_type.filter((t) => t.count > 0)}
                        dataKey="count"
                        nameKey="entry_type"
                        cx="50%"
                        cy="50%"
                        outerRadius={80}
                        label={(e: any) =>
                          `${ENTRY_TYPE_LABEL[e.entry_type as EntryType] || e.entry_type}: ${e.count}`
                        }
                      >
                        {data.entries_by_type
                          .filter((t) => t.count > 0)
                          .map((_, i) => (
                            <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                          ))}
                      </Pie>
                      <Tooltip
                        contentStyle={{
                          background: 'rgba(30, 41, 59, 0.95)',
                          border: '1px solid #475569',
                          borderRadius: '6px',
                          color: '#f1f5f9',
                        }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </div>

          {/* v0.9.18: Kişi Bazlı Performans — SADECE Telefon Çağrıları */}
          <div className="card">
            <h2 className="font-semibold mb-1 text-gray-900 dark:text-slate-100">
              Kişi Bazlı Performans — Telefon Çağrıları ({RANGE_LABEL[range]})
            </h2>
            <p className="text-xs text-gray-500 dark:text-slate-400 mb-3">
              Her operatörün {RANGE_LABEL[range].toLowerCase()} bazda karşıladığı
              telefon çağrı sayısı (Arayanlar tipi kayıtlar). Sıralama en çok
              çağrı alan üstte olacak şekilde.
              {totalCallers > 0 && (
                <> Toplam <b>{totalCallers}</b> çağrı bu aralıkta karşılandı.</>
              )}
            </p>
            {data.top_callers.length === 0 ? (
              <div className="text-gray-500 dark:text-slate-400 text-sm">
                Bu aralıkta "Arayanlar" girişi yok.
              </div>
            ) : (
              <>
                <div className="h-64 mb-4">
                  <ResponsiveContainer>
                    <BarChart data={data.top_callers} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke="#94a3b8" strokeOpacity={0.3} />
                      <XAxis type="number" allowDecimals={false} fontSize={11} stroke="#64748b" />
                      <YAxis type="category" dataKey="user_name" fontSize={11} width={140} stroke="#64748b" />
                      <Tooltip
                        contentStyle={{
                          background: 'rgba(30, 41, 59, 0.95)',
                          border: '1px solid #475569',
                          borderRadius: '6px',
                          color: '#f1f5f9',
                        }}
                      />
                      <Bar dataKey="count" fill="#dc2626" name="Çağrı sayısı" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 dark:bg-slate-700 text-left text-xs uppercase text-gray-500 dark:text-slate-300">
                      <tr>
                        <th className="px-3 py-2">#</th>
                        <th className="px-3 py-2">Kullanıcı</th>
                        <th className="px-3 py-2 text-right">Çağrı Sayısı</th>
                        <th className="px-3 py-2 text-right">Toplam Payı</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-slate-700">
                      {data.top_callers.map((c, i) => {
                        const pct = totalCallers > 0
                          ? ((c.count / totalCallers) * 100).toFixed(1)
                          : '0';
                        return (
                          <tr key={c.user_id}>
                            <td className="px-3 py-2 text-gray-500 dark:text-slate-400">
                              #{i + 1}
                            </td>
                            <td className="px-3 py-2 font-medium text-gray-800 dark:text-slate-100">
                              {c.user_name}
                            </td>
                            <td className="px-3 py-2 text-right font-semibold text-gray-900 dark:text-slate-100">
                              {c.count}
                            </td>
                            <td className="px-3 py-2 text-right text-gray-500 dark:text-slate-400">
                              %{pct}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>

          {/* Tekrarlayan başlıklar */}
          <div className="card">
            <h2 className="font-semibold mb-2 text-gray-900 dark:text-slate-100">
              Tekrarlayan Konular
            </h2>
            {data.recurring_titles.length === 0 ? (
              <div className="text-gray-500 dark:text-slate-400 text-sm">
                Bu aralıkta tekrarlayan konu tespit edilmedi.
              </div>
            ) : (
              <ul className="divide-y divide-gray-100 dark:divide-slate-700">
                {data.recurring_titles.map((t) => (
                  <li key={t.title} className="py-2 flex justify-between text-sm">
                    <span className="text-gray-800 dark:text-slate-200 truncate max-w-[70%]">
                      {t.title}
                    </span>
                    <span className="text-gray-500 dark:text-slate-400">{t.count}×</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function StatCard({ label, value, tone }: {
  label: string; value: number; tone?: 'warn' | 'info';
}) {
  const ring =
    tone === 'warn'
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
