// Aylık Vardiya Listesi — v0.7.1 (gerçek takvim).
//
// Layout:
//   - Üst bar: Yıl + Ay seçici, "Otomatik Üret" butonu (super_admin),
//     "Personel Yönet" linki, CSV indir.
//   - Grid: satırlar = personel, sütunlar = ayın günleri.
//     Her hücre o personelin o günkü atamasının slot kısaltmasını gösterir.
//     Manuel müdahale yapılmışsa hücrenin sağ üstünde küçük • işareti.
//   - Hücreye tıkla → düzenleme modal (super_admin); slot değişir,
//     not yazılabilir, kayıt manuel-lock'lanır (bir sonraki generate korur).
//   - Açıklayıcı renk legend'i altta.
//
// Yetki:
//   - Sayfa zaten ProtectedRoute requireRole={['super_admin']} ile gardlanmış.
//   - Yine de "Otomatik Üret" ve hücre düzenleme butonları rol kontrolüyle
//     açılır (defense in depth).

import { FormEvent, useEffect, useMemo, useState } from 'react';
import {
  api,
  GenerateMonthlyShiftResult,
  GROUP_LABEL,
  LOCATION_LABEL,
  MonthlyShiftAssignment,
  MonthlyShiftSlot,
  Personnel,
  SLOT_BG,
  SLOT_LABEL,
  SLOT_SHORT,
} from '../api/client';
import { useAuth } from '../auth/AuthContext';

const MONTH_NAMES_TR = [
  'Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran',
  'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık',
];

const SLOT_OPTIONS: MonthlyShiftSlot[] = [
  'a_fixed', 'a_ankara', 'a_istanbul', 'b_shift', 'c_shift',
  'oncall', 'leave', 'off', 'wfh',
];

function daysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate(); // month is 1-based
}

function fmtDay(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function dayKey(year: number, month: number, day: number): string {
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

export default function AylikVardiya() {
  const { user } = useAuth();
  const isSuperAdmin = user?.role === 'super_admin';

  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);

  const [personnel, setPersonnel] = useState<Personnel[]>([]);
  const [assignments, setAssignments] = useState<MonthlyShiftAssignment[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const [editing, setEditing] = useState<{
    personnelId: number;
    personnelName: string;
    day: string;
    existing: MonthlyShiftAssignment | null;
  } | null>(null);
  const [personnelOpen, setPersonnelOpen] = useState(false);

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const [p, a] = await Promise.all([
        api.get<Personnel[]>('/personnel', { params: { only_active: true } }),
        api.get<MonthlyShiftAssignment[]>('/monthly-shifts', { params: { year, month } }),
      ]);
      setPersonnel(p.data);
      setAssignments(a.data);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Veri yüklenemedi');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year, month]);

  // {personnel_id: {day_string: assignment}} hızlı arama tablosu
  const grid = useMemo(() => {
    const m = new Map<number, Map<string, MonthlyShiftAssignment>>();
    for (const a of assignments) {
      if (!m.has(a.personnel_id)) m.set(a.personnel_id, new Map());
      m.get(a.personnel_id)!.set(a.day, a);
    }
    return m;
  }, [assignments]);

  async function runGenerate(overwriteManual: boolean) {
    if (!isSuperAdmin) return;
    if (
      overwriteManual &&
      !confirm(
        `${MONTH_NAMES_TR[month - 1]} ${year} için TÜM atamalar (manuel müdahaleler dahil) silinip yeniden üretilecek. Onaylıyor musunuz?`,
      )
    )
      return;
    setMsg(null);
    setErr(null);
    setLoading(true);
    try {
      const r = await api.post<GenerateMonthlyShiftResult>('/monthly-shifts/generate', {
        year, month, overwrite_manual: overwriteManual,
      });
      const d = r.data;
      setMsg(
        `Çizelge oluşturuldu: ${d.assignments_created} atama, ${d.assignments_preserved} manuel kayıt korundu (${d.days_generated} gün).` +
          (d.warnings.length ? ` Uyarılar: ${d.warnings.join(', ')}` : ''),
      );
      load();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Generate başarısız');
    } finally {
      setLoading(false);
    }
  }

  function downloadCsv() {
    const days = daysInMonth(year, month);
    const header = ['Personel', 'Lokasyon', 'Grup'];
    for (let i = 1; i <= days; i++) header.push(String(i));
    const rows: string[][] = [header];
    for (const p of personnel) {
      const row = [p.full_name, LOCATION_LABEL[p.location], GROUP_LABEL[p.group]];
      for (let i = 1; i <= days; i++) {
        const a = grid.get(p.id)?.get(dayKey(year, month, i));
        row.push(a ? SLOT_SHORT[a.slot] : '');
      }
      rows.push(row);
    }
    const csv = rows
      .map((r) => r.map((c) => `"${(c || '').replace(/"/g, '""')}"`).join(','))
      .join('\n');
    const blob = new Blob([`﻿${csv}`], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `aylik-vardiya-${year}-${String(month).padStart(2, '0')}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const days = daysInMonth(year, month);
  const dayHeaders = Array.from({ length: days }, (_, i) => i + 1);

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-slate-100">
            Aylık Vardiya Listesi
          </h1>
          <p className="text-sm text-gray-500 dark:text-slate-400">
            Otomatik oluşturulan aylık çizelge.
            {isSuperAdmin
              ? ' Hücreye tıklayarak manuel düzenleyebilirsiniz; düzenlenen hücreler bir sonraki otomatik üretimden korunur.'
              : ' Sadece okuma yetkisi. Düzenleme için Super Admin yetkisi gerekir.'}
          </p>
        </div>
        <div className="flex items-end gap-2 flex-wrap">
          <label className="text-xs">
            Yıl
            <select
              className="input ml-1 py-1 text-sm w-24"
              value={year}
              onChange={(e) => setYear(Number(e.target.value))}
            >
              {[year - 1, year, year + 1, year + 2].map((y) => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
          </label>
          <label className="text-xs">
            Ay
            <select
              className="input ml-1 py-1 text-sm w-28"
              value={month}
              onChange={(e) => setMonth(Number(e.target.value))}
            >
              {MONTH_NAMES_TR.map((n, i) => (
                <option key={i + 1} value={i + 1}>{n}</option>
              ))}
            </select>
          </label>
          <button className="btn-ghost text-sm" onClick={downloadCsv}>
            CSV İndir
          </button>
          {isSuperAdmin && (
            <>
              <button className="btn-ghost text-sm" onClick={() => setPersonnelOpen(true)}>
                Personel Yönet
              </button>
              <button
                className="btn-primary text-sm"
                onClick={() => runGenerate(false)}
                disabled={loading}
              >
                Otomatik Üret
              </button>
              <button
                className="btn-ghost text-sm text-red-600"
                onClick={() => runGenerate(true)}
                disabled={loading}
                title="Manuel müdahaleler dahil tüm atamaları silip yeniden üretir."
              >
                Sıfırla & Üret
              </button>
            </>
          )}
        </div>
      </div>

      {msg && (
        <div className="card text-sm text-emerald-700 dark:text-emerald-300 border-l-4 border-emerald-400">
          {msg}
        </div>
      )}
      {err && (
        <div className="card text-sm text-red-600 dark:text-red-400 border-l-4 border-red-400">
          {err}
        </div>
      )}

      <div className="card p-0 overflow-x-auto">
        {loading && personnel.length === 0 ? (
          <div className="p-4 text-sm text-gray-500">Yükleniyor…</div>
        ) : personnel.length === 0 ? (
          <div className="p-4 text-sm text-gray-500">
            Personel yok. {isSuperAdmin ? '"Personel Yönet" ile ekleyin.' : ''}
          </div>
        ) : assignments.length === 0 ? (
          // v0.8.6: Veri yoksa boş tablo göstermek yerine açıklayıcı placeholder.
          <div className="p-6 text-center space-y-2">
            <div className="text-2xl">📅</div>
            <div className="text-sm text-gray-600 dark:text-slate-300">
              <b>{MONTH_NAMES_TR[month - 1]} {year}</b> için henüz çizelge oluşturulmadı.
            </div>
            {isSuperAdmin ? (
              <div className="text-xs text-gray-500 dark:text-slate-400">
                Üst bardaki <b>Otomatik Üret</b> butonuna basın — algoritma
                rotasyon kurallarına göre tüm ayı hazırlar.
              </div>
            ) : (
              <div className="text-xs text-gray-500 dark:text-slate-400">
                Henüz Super Admin tarafından çizelge oluşturulmamış.
              </div>
            )}
          </div>
        ) : (
          <table className="text-sm border-collapse w-full">
            <thead className="bg-gray-50 dark:bg-slate-900 sticky top-0 z-10">
              <tr>
                {/* v0.8.9: Lokasyon sütunu kaldırıldı, personel adı yanında
                    küçük badge olarak gösterilir. Bu sayede tablo ekrana
                    daha kolay sığar (~%30 daha kompakt). */}
                <th className="px-2 py-2 text-left sticky left-0 bg-gray-50 dark:bg-slate-900 z-20 border-b border-r border-gray-200 dark:border-slate-700 w-[140px] min-w-[140px] font-bold text-gray-800 dark:text-slate-100">
                  Personel
                </th>
                {dayHeaders.map((d) => {
                  const date = new Date(year, month - 1, d);
                  const dow = date.getDay(); // 0=Sun, 6=Sat
                  const isWeekend = dow === 0 || dow === 6;
                  return (
                    <th
                      key={d}
                      className={`px-0.5 py-1.5 text-center border-b border-gray-200 dark:border-slate-700 font-bold ${
                        isWeekend ? 'bg-blue-50 text-blue-700 dark:bg-slate-800 dark:text-blue-300' : 'text-gray-800 dark:text-slate-100'
                      }`}
                    >
                      <div className="text-sm leading-tight">{d}</div>
                      <div className="text-[10px] font-medium text-gray-500 dark:text-slate-400 leading-none">
                        {['Pa', 'Pt', 'Sa', 'Ça', 'Pe', 'Cu', 'Ct'][dow]}
                      </div>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {personnel.map((p) => (
                <tr key={p.id} className="hover:bg-gray-50 dark:hover:bg-slate-800">
                  <td className="px-2 py-1.5 sticky left-0 bg-white dark:bg-slate-800 border-r border-b border-gray-200 dark:border-slate-700 font-semibold text-gray-900 dark:text-slate-100 z-10 w-[140px] min-w-[140px]">
                    <div className="flex items-center gap-1 flex-wrap">
                      <span>{p.full_name}</span>
                      <span className={`text-[9px] px-1 py-0 rounded font-medium ${
                        p.location === 'istanbul'
                          ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-200'
                          : 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-200'
                      }`}>
                        {p.location === 'istanbul' ? 'İst' : 'Ank'}
                      </span>
                      {p.is_fixed_a && (
                        <span className="text-[9px] font-normal text-gray-400">sabit</span>
                      )}
                      {p.is_oncall_only && (
                        <span className="text-[9px] font-normal text-gray-400">on-call</span>
                      )}
                    </div>
                  </td>
                  {dayHeaders.map((d) => {
                    const dkey = dayKey(year, month, d);
                    const a = grid.get(p.id)?.get(dkey);
                    const cellClass = a
                      ? SLOT_BG[a.slot]
                      : 'bg-white dark:bg-slate-800';
                    return (
                      <td
                        key={d}
                        className={`px-0.5 py-1.5 text-center border-b border-gray-100 dark:border-slate-700 text-xs font-bold ${cellClass} ${
                          isSuperAdmin ? 'cursor-pointer' : ''
                        }`}
                        title={
                          a
                            ? `${SLOT_LABEL[a.slot]}${a.note ? ` — ${a.note}` : ''}${a.modified_by_user_id ? ' (manuel)' : ''}`
                            : 'Atama yok'
                        }
                        onClick={() => {
                          if (!isSuperAdmin) return;
                          setEditing({
                            personnelId: p.id,
                            personnelName: p.full_name,
                            day: dkey,
                            existing: a || null,
                          });
                        }}
                      >
                        <span className="relative inline-block">
                          {a ? SLOT_SHORT[a.slot] : ''}
                          {a?.modified_by_user_id && (
                            <span className="absolute -top-0.5 -right-2 text-[8px] text-red-600">
                              ●
                            </span>
                          )}
                        </span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card text-xs text-gray-600 dark:text-slate-400">
        <div className="font-medium mb-2 text-gray-800 dark:text-slate-100">
          Hücre Renk / Sembol Kılavuzu
        </div>
        <div className="flex flex-wrap gap-2">
          {SLOT_OPTIONS.map((s) => (
            <div
              key={s}
              className={`inline-flex items-center gap-1 px-2 py-1 rounded ${SLOT_BG[s]}`}
            >
              <span className="font-mono">{SLOT_SHORT[s]}</span>
              <span>= {SLOT_LABEL[s]}</span>
            </div>
          ))}
          <div className="inline-flex items-center gap-1 px-2 py-1">
            <span className="text-red-600">●</span>
            <span>= manuel düzenleme (jeneratör korur)</span>
          </div>
        </div>
      </div>

      {editing && (
        <CellEditModal
          year={year}
          month={month}
          personnelId={editing.personnelId}
          personnelName={editing.personnelName}
          day={editing.day}
          existing={editing.existing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }}
        />
      )}
      {personnelOpen && (
        <PersonnelManagerModal
          onClose={() => setPersonnelOpen(false)}
          onSaved={() => { setPersonnelOpen(false); load(); }}
        />
      )}
    </div>
  );
}


function CellEditModal({
  year, month, personnelId, personnelName, day, existing, onClose, onSaved,
}: {
  year: number; month: number;
  personnelId: number; personnelName: string;
  day: string;
  existing: MonthlyShiftAssignment | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [slot, setSlot] = useState<MonthlyShiftSlot>(existing?.slot || 'a_istanbul');
  const [note, setNote] = useState(existing?.note || '');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setSaving(true);
    try {
      if (existing) {
        await api.patch(`/monthly-shifts/${existing.id}`, { slot, note: note || null });
      } else {
        await api.post('/monthly-shifts', {
          personnel_id: personnelId,
          day, slot, note: note || null,
        });
      }
      onSaved();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Kayıt başarısız');
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!existing) return;
    if (!confirm('Bu atamayı silmek istediğinize emin misiniz?')) return;
    setSaving(true);
    try {
      await api.delete(`/monthly-shifts/${existing.id}`);
      onSaved();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Silme başarısız');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <form
        onSubmit={save}
        className="bg-white dark:bg-slate-800 rounded-lg shadow-xl w-full max-w-md p-5 space-y-3"
      >
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-gray-900 dark:text-slate-100">
            Atama Düzenle
          </h2>
          <button type="button" className="text-gray-500 dark:text-slate-400" onClick={onClose}>✕</button>
        </div>
        <div className="text-sm text-gray-600 dark:text-slate-300">
          <b>{personnelName}</b> &middot; {day}
        </div>
        <div>
          <label className="label">Slot</label>
          <select
            className="input"
            value={slot}
            onChange={(e) => setSlot(e.target.value as MonthlyShiftSlot)}
          >
            {SLOT_OPTIONS.map((s) => (
              <option key={s} value={s}>{SLOT_LABEL[s]}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Not (opsiyonel)</label>
          <input
            className="input"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="örn. yıllık izin, eğitim, vb."
          />
        </div>
        {err && <div className="text-sm text-red-600 dark:text-red-400">{err}</div>}
        <div className="flex justify-between items-center pt-1">
          {existing ? (
            <button type="button" className="btn-ghost text-xs text-red-600" onClick={remove}>
              Sil
            </button>
          ) : <span />}
          <div className="flex gap-2">
            <button type="button" className="btn-ghost" onClick={onClose}>İptal</button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Kaydediliyor…' : 'Kaydet'}
            </button>
          </div>
        </div>
        <p className="text-[10px] text-gray-500 dark:text-slate-400 pt-1">
          Bu kayıt manuel olarak işaretlenir. Bir sonraki "Otomatik Üret" çağrısı
          bu hücreyi korur. "Sıfırla &amp; Üret" ise tüm manuel kayıtları siler.
        </p>
      </form>
    </div>
  );
}


function PersonnelManagerModal({
  onClose, onSaved,
}: {
  onClose: () => void;
  onSaved: () => void;
}) {
  const [list, setList] = useState<Personnel[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [newLoc, setNewLoc] = useState<'istanbul' | 'ankara'>('ankara');
  const [newGroup, setNewGroup] = useState<'fixed_a' | 'istanbul' | 'ankara'>('ankara');
  const [newOncall, setNewOncall] = useState(false);
  const [newFixed, setNewFixed] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const r = await api.get<Personnel[]>('/personnel', { params: { only_active: false } });
      setList(r.data);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Yüklenemedi');
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); }, []);

  async function create(e: FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    setErr(null);
    try {
      await api.post('/personnel', {
        full_name: newName.trim(),
        location: newLoc,
        group: newGroup,
        is_oncall_only: newOncall,
        is_fixed_a: newFixed,
        is_active: true,
      });
      setNewName('');
      load();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Ekleme başarısız');
    } finally {
      setCreating(false);
    }
  }

  async function toggleActive(p: Personnel) {
    try {
      if (p.is_active) {
        await api.delete(`/personnel/${p.id}`);
      } else {
        await api.patch(`/personnel/${p.id}`, { is_active: true });
      }
      load();
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'İşlem başarısız');
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4 overflow-y-auto">
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow-xl w-full max-w-3xl my-8">
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-slate-700">
          <h2 className="font-semibold text-gray-900 dark:text-slate-100">Personel Yönetimi</h2>
          <button type="button" className="text-gray-500 dark:text-slate-400" onClick={onClose}>✕</button>
        </div>
        <div className="p-5 space-y-4">
          <form onSubmit={create} className="grid grid-cols-1 md:grid-cols-6 gap-2 items-end">
            <input
              className="input md:col-span-2"
              placeholder="Ad soyad"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              required
            />
            <select className="input" value={newLoc} onChange={(e) => setNewLoc(e.target.value as any)}>
              <option value="istanbul">İstanbul</option>
              <option value="ankara">Ankara</option>
            </select>
            <select className="input" value={newGroup} onChange={(e) => setNewGroup(e.target.value as any)}>
              <option value="fixed_a">Sabit A</option>
              <option value="istanbul">İstanbul (mavi)</option>
              <option value="ankara">Ankara (kırmızı)</option>
            </select>
            <label className="flex items-center gap-1 text-xs">
              <input type="checkbox" checked={newOncall} onChange={(e) => setNewOncall(e.target.checked)} />
              On-call only
            </label>
            <label className="flex items-center gap-1 text-xs">
              <input type="checkbox" checked={newFixed} onChange={(e) => setNewFixed(e.target.checked)} />
              Sabit A
            </label>
            <button type="submit" className="btn-primary text-sm md:col-span-6" disabled={creating || !newName.trim()}>
              Ekle
            </button>
          </form>

          {err && <div className="text-sm text-red-600">{err}</div>}

          {loading ? (
            <div className="text-sm text-gray-500">Yükleniyor…</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-xs uppercase text-gray-500">
                <tr>
                  <th className="text-left px-2 py-1">Ad</th>
                  <th className="text-left px-2 py-1">Lokasyon</th>
                  <th className="text-left px-2 py-1">Grup</th>
                  <th className="text-left px-2 py-1">Bayraklar</th>
                  <th className="text-left px-2 py-1">Durum</th>
                  <th className="px-2 py-1"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-slate-700">
                {list.map((p) => (
                  <tr key={p.id} className={p.is_active ? '' : 'opacity-50'}>
                    <td className="px-2 py-1">{p.full_name}</td>
                    <td className="px-2 py-1">{LOCATION_LABEL[p.location]}</td>
                    <td className="px-2 py-1">{GROUP_LABEL[p.group]}</td>
                    <td className="px-2 py-1 text-xs text-gray-500 dark:text-slate-400">
                      {p.is_fixed_a && 'sabit '}{p.is_oncall_only && 'on-call'}
                    </td>
                    <td className="px-2 py-1">{p.is_active ? 'Aktif' : 'Pasif'}</td>
                    <td className="px-2 py-1 text-right">
                      <button
                        className="text-xs text-brand-700 dark:text-brand-400 hover:underline"
                        onClick={() => toggleActive(p)}
                      >
                        {p.is_active ? 'Pasifleştir' : 'Aktifleştir'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="px-5 py-3 border-t border-gray-200 dark:border-slate-700 flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={onClose}>Kapat</button>
          <button type="button" className="btn-primary" onClick={() => { onSaved(); }}>
            Bitti
          </button>
        </div>
      </div>
    </div>
  );
}
