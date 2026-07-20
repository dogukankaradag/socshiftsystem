// Dağıtıcı Listesi — v0.8.1 (otomasyonlu, tek sayfa).
//
// Aylık Vardiya'dan veri çekerek otomatik üretilir:
//   - Sadece hafta içi (Pzt-Cu)
//   - Her gün: 1 Dağıtıcı + 1 Öğlen Nöbetçi
//   - O gün A vardiyasında olan kişiler arasından seçim
//   - Config'teki `excluded_from_daily_duty` hariç tüm eligible personel
//   - Hedef: her aktif personele ayda ≥2 dağıtıcı + ≥2 öğlen
//
// Standart kullanıcı: takvimi okur, CSV indirir.
// Super Admin: Otomatik Üret + hücreye tıklayarak manuel düzenleme.
import { FormEvent, useEffect, useMemo, useState } from 'react';
import {
  api,
  DailyDuty,
  DailyDutyType,
  DUTY_LABEL,
  GenerateDailyDutyResult,
  Personnel,
} from '../api/client';
import { useAuth } from '../auth/AuthContext';

const MONTH_NAMES_TR = [
  'Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran',
  'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık',
];

function weekdayDates(year: number, month: number): Date[] {
  const out: Date[] = [];
  const daysInMonth = new Date(year, month, 0).getDate();
  for (let d = 1; d <= daysInMonth; d++) {
    const date = new Date(year, month - 1, d);
    if (date.getDay() !== 0 && date.getDay() !== 6) out.push(date);
  }
  return out;
}

function fmtDay(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

const DAY_NAMES_TR = ['Pazar', 'Pzt', 'Sal', 'Çar', 'Per', 'Cuma', 'Cmt'];

export default function Distributors() {
  const { user } = useAuth();
  const isSuperAdmin = user?.role === 'super_admin';

  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);

  const [duties, setDuties] = useState<DailyDuty[]>([]);
  const [personnel, setPersonnel] = useState<Personnel[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  // v0.8.3+: (day, duty_type) için TÜM atamaları düzenle.
  // v0.8.4: expectedCount → Cuma öğleninde 1, diğer durumlarda 2.
  const [editing, setEditing] = useState<{
    day: string;
    duty_type: DailyDutyType;
    existingList: DailyDuty[];
    expectedCount: number;
  } | null>(null);

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const [d, p] = await Promise.all([
        api.get<DailyDuty[]>('/daily-duty', { params: { year, month } }),
        api.get<Personnel[]>('/personnel', { params: { only_active: true } }),
      ]);
      setDuties(d.data);
      setPersonnel(p.data);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Yüklenemedi');
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [year, month]);

  // v0.8.3: {date_string: {distributor: DailyDuty[], lunch: DailyDuty[]}}
  // (2 kişi/slot). Array, gün × tür için 0-2 atama tutar.
  const dayMap = useMemo(() => {
    const m = new Map<string, Record<DailyDutyType, DailyDuty[]>>();
    for (const d of duties) {
      if (!m.has(d.day)) m.set(d.day, { distributor: [], lunch: [] });
      m.get(d.day)![d.duty_type].push(d);
    }
    // Her hücreyi id'ye göre stabil sırala
    for (const v of m.values()) {
      v.distributor.sort((a, b) => a.id - b.id);
      v.lunch.sort((a, b) => a.id - b.id);
    }
    return m;
  }, [duties]);

  // Per-person sayım (alt özet için)
  const counts = useMemo(() => {
    const dist = new Map<string, number>();
    const lunch = new Map<string, number>();
    for (const d of duties) {
      const name = d.personnel_name || `#${d.personnel_id}`;
      if (d.duty_type === 'distributor') {
        dist.set(name, (dist.get(name) || 0) + 1);
      } else {
        lunch.set(name, (lunch.get(name) || 0) + 1);
      }
    }
    return { dist, lunch };
  }, [duties]);

  async function runGenerate(overwriteManual: boolean) {
    if (!isSuperAdmin) return;
    if (
      overwriteManual &&
      !confirm(
        `${MONTH_NAMES_TR[month - 1]} ${year} dağıtıcı/öğlen çizelgesinin TÜM atamaları (manueller dahil) silinip yeniden üretilecek. Onaylıyor musunuz?`,
      )
    ) return;
    setMsg(null);
    setErr(null);
    setLoading(true);
    try {
      const r = await api.post<GenerateDailyDutyResult>('/daily-duty/generate', {
        year, month, overwrite_manual: overwriteManual,
      });
      const d = r.data;
      const lowDist = Object.entries(d.per_person_distributor || {})
        .filter(([, c]) => c < 2)
        .map(([n]) => n);
      const lowLunch = Object.entries(d.per_person_lunch || {})
        .filter(([, c]) => c < 2)
        .map(([n]) => n);
      const lowMsg = (lowDist.length || lowLunch.length)
        ? ` ⚠ <2 hedef: dağıtıcı(${lowDist.join(', ') || '—'}), öğlen(${lowLunch.join(', ') || '—'})`
        : '';
      setMsg(
        `${d.assignments_created} atama oluşturuldu, ${d.assignments_preserved} manuel korundu (${d.weekdays_generated} hafta içi gün).${lowMsg}`
          + (d.warnings.length ? ` — ${d.warnings.join(' / ')}` : ''),
      );
      load();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Generate başarısız');
    } finally {
      setLoading(false);
    }
  }

  function downloadCsv() {
    const dates = weekdayDates(year, month);
    const rows: string[][] = [
      ['Tarih', 'Gün', 'Dağıtıcı 1', 'Dağıtıcı 2', 'Öğlen Nöbetçi 1', 'Öğlen Nöbetçi 2'],
    ];
    for (const dt of dates) {
      const dkey = fmtDay(dt);
      const cell = dayMap.get(dkey);
      const dList = cell?.distributor || [];
      const lList = cell?.lunch || [];
      rows.push([
        dkey,
        DAY_NAMES_TR[dt.getDay()],
        dList[0]?.personnel_name || '',
        dList[1]?.personnel_name || '',
        lList[0]?.personnel_name || '',
        lList[1]?.personnel_name || '',
      ]);
    }
    const csv = rows.map((r) =>
      r.map((c) => `"${(c || '').replace(/"/g, '""')}"`).join(','),
    ).join('\n');
    const blob = new Blob([`﻿${csv}`], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `dagitici-listesi-${year}-${String(month).padStart(2, '0')}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const dates = weekdayDates(year, month);

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-slate-100">
            Dağıtıcı Listesi
          </h1>
          <p className="text-sm text-gray-500 dark:text-slate-400">
            Hafta içi günlük <b>Aylık Dağıtıcı</b> + <b>Öğlen Nöbetçi</b> atamaları.
            Aylık Vardiya'da A vardiyasında olan kişiler arasından otomatik
            üretilir; her personele ayda ≥2 dağıtıcı + ≥2 öğlen düşürülür.
            {' '}{isSuperAdmin
              ? 'Hücreye tıklayarak manuel düzenleyebilirsiniz.'
              : 'Sadece okuma yetkisi.'}
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
          <button className="btn-ghost text-sm" onClick={downloadCsv}>CSV İndir</button>
          {isSuperAdmin && (
            <>
              <button
                className="btn-primary text-sm"
                onClick={() => runGenerate(false)}
                disabled={loading}
                title="Manuel atamalar korunur, geri kalan yeniden üretilir."
              >
                Otomatik Üret
              </button>
              <button
                className="btn-ghost text-sm text-red-600"
                onClick={() => runGenerate(true)}
                disabled={loading}
                title="Manueller dahil tüm atamaları silip yeniden üretir."
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
        {loading && duties.length === 0 ? (
          <div className="p-4 text-sm text-gray-500">Yükleniyor…</div>
        ) : dates.length === 0 ? (
          <div className="p-4 text-sm text-gray-500">Bu ayda hafta içi gün yok.</div>
        ) : (
          <table className="w-full text-base">
            <thead className="bg-gray-50 dark:bg-slate-900 text-sm uppercase font-bold text-gray-700 dark:text-slate-300">
              <tr>
                <th className="px-4 py-3 text-left">Tarih</th>
                <th className="px-4 py-3 text-left">Gün</th>
                <th className="px-4 py-3 text-left">Aylık Dağıtıcı</th>
                <th className="px-4 py-3 text-left">Öğlen Nöbetçi</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-slate-700">
              {dates.map((dt) => {
                const dkey = fmtDay(dt);
                // v0.8.7: Açık tip annotation — boş fallback {} 'ı TS index
                // imzasıyla uyumlu hale getiriyor (`cell['distributor']` çalışsın).
                const cell: Partial<Record<DailyDutyType, DailyDuty[]>> =
                  dayMap.get(dkey) || {};
                return (
                  <tr key={dkey} className="hover:bg-gray-50 dark:hover:bg-slate-800">
                    <td className="px-4 py-3 font-semibold text-gray-900 dark:text-slate-100">
                      {dt.toLocaleDateString('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric' })}
                    </td>
                    <td className="px-4 py-3 text-gray-700 dark:text-slate-300">
                      {DAY_NAMES_TR[dt.getDay()]}
                    </td>
                    {(['distributor', 'lunch'] as DailyDutyType[]).map((t) => {
                      const list = cell[t] || [];
                      const hasManual = list.some((x) => x.modified_by_user_id);
                      // v0.8.4: Cuma öğlen sadece 1 kişi olur (özel havuz).
                      // Hedef sayı: distributor=2 her gün, lunch=1 Cuma / 2 diğer
                      const isFridayLunchSlot = t === 'lunch' && dt.getDay() === 5;
                      const expectedCount = isFridayLunchSlot ? 1 : 2;
                      return (
                        <td
                          key={t}
                          className={`px-4 py-3 align-top ${isSuperAdmin ? 'cursor-pointer hover:bg-amber-50 dark:hover:bg-slate-700' : ''} ${
                            hasManual ? 'border-l-4 border-red-400' : ''
                          }`}
                          onClick={() => {
                            if (!isSuperAdmin) return;
                            setEditing({
                              day: dkey,
                              duty_type: t,
                              existingList: list,
                              expectedCount,
                            });
                          }}
                          title={
                            list.length
                              ? list.map((x) =>
                                  `${x.personnel_name}${x.note ? ' — ' + x.note : ''}${x.modified_by_user_id ? ' (manuel)' : ''}`,
                                ).join(' / ')
                              : 'Atanmamış'
                          }
                        >
                          {list.length === 0 ? (
                            <span className="text-gray-400 italic">—</span>
                          ) : (
                            <div className="space-y-0.5">
                              {list.map((x) => (
                                <div key={x.id} className="font-medium text-gray-800 dark:text-slate-100">
                                  {x.personnel_name}
                                  {x.modified_by_user_id && (
                                    <span className="ml-1 text-xs text-red-600">●</span>
                                  )}
                                </div>
                              ))}
                              {list.length < expectedCount && (
                                <div className="text-xs italic text-amber-700 dark:text-amber-300">
                                  — {expectedCount}. kişi atanmadı —
                                </div>
                              )}
                            </div>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Per-person özet (adalet kontrolü) */}
      {duties.length > 0 && (
        <div className="card">
          <h2 className="text-sm font-bold text-gray-800 dark:text-slate-100 mb-2">
            Kişi Bazlı Atama Özeti
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <div className="text-xs uppercase text-gray-500 mb-1">Aylık Dağıtıcı</div>
              <ul className="text-sm divide-y divide-gray-100 dark:divide-slate-700">
                {personnel
                  .filter((p) => p.is_active)
                  .map((p) => {
                    const c = counts.dist.get(p.full_name) || 0;
                    return (
                      <li key={p.id} className={`py-1 flex justify-between ${c < 2 ? 'text-red-600 font-medium' : ''}`}>
                        <span>{p.full_name}</span>
                        <span>{c}</span>
                      </li>
                    );
                  })}
              </ul>
            </div>
            <div>
              <div className="text-xs uppercase text-gray-500 mb-1">Öğlen Nöbetçi</div>
              <ul className="text-sm divide-y divide-gray-100 dark:divide-slate-700">
                {personnel
                  .filter((p) => p.is_active)
                  .map((p) => {
                    const c = counts.lunch.get(p.full_name) || 0;
                    return (
                      <li key={p.id} className={`py-1 flex justify-between ${c < 2 ? 'text-red-600 font-medium' : ''}`}>
                        <span>{p.full_name}</span>
                        <span>{c}</span>
                      </li>
                    );
                  })}
              </ul>
            </div>
          </div>
          <p className="text-xs text-gray-500 dark:text-slate-400 mt-2">
            Kırmızı satırlar hedef olan ≥2 atamasına ulaşılamamış kişileri gösterir.
            Manuel düzenleme ile takviye edebilirsiniz.
          </p>
        </div>
      )}

      {editing && (
        <DutyEditModal
          day={editing.day}
          dutyType={editing.duty_type}
          existingList={editing.existingList}
          expectedCount={editing.expectedCount}
          personnel={personnel.filter((p) => p.is_active)}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }}
        />
      )}
    </div>
  );
}


/**
 * v0.8.3: Hücre düzenleme modalı — 2 seat'e kadar.
 *
 * 2 seat dropdown'ı + her seat için not alanı. Boş seat → mevcutsa silinir,
 * boştuysa atlanır. Dolu seat → mevcut yok ise POST, mevcut farklı kişi ise
 * PATCH. Aynı seat = aynı personnel + aynı not ise no-op.
 *
 * Öğlen lokasyon kısıtı UI'da uyarı olarak gösterilir; super admin yine de
 * isterse override edebilir (backend yalnızca duplicate engelleme + max 2
 * yapar).
 */
function DutyEditModal({
  day, dutyType, existingList, expectedCount, personnel, onClose, onSaved,
}: {
  day: string;
  dutyType: DailyDutyType;
  existingList: DailyDuty[];
  expectedCount: number;  // v0.8.4: Cuma öğlen için 1, diğer durumlarda 2
  personnel: Personnel[];
  onClose: () => void;
  onSaved: () => void;
}) {
  // İki seat için state — mevcut atamalar varsa onlardan başla
  const seat0 = existingList[0];
  const seat1 = existingList[1];

  const [pid0, setPid0] = useState<number | ''>(seat0?.personnel_id ?? '');
  const [note0, setNote0] = useState(seat0?.note || '');
  const [pid1, setPid1] = useState<number | ''>(seat1?.personnel_id ?? '');
  const [note1, setNote1] = useState(seat1?.note || '');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Lokasyon uyarısı (sadece öğlen için anlamlı)
  const personById = useMemo(() => {
    const m = new Map<number, Personnel>();
    for (const p of personnel) m.set(p.id, p);
    return m;
  }, [personnel]);

  const locWarning = useMemo(() => {
    if (dutyType !== 'lunch') return null;
    if (!pid0 || !pid1) return null;
    const a = personById.get(Number(pid0));
    const b = personById.get(Number(pid1));
    if (!a || !b) return null;
    if (a.location !== b.location) {
      return 'İki öğlen nöbetçisi farklı lokasyondan; öğlen için aynı lokasyon önerilir (kayıt yine de yapılabilir).';
    }
    return null;
  }, [dutyType, pid0, pid1, personById]);

  async function save(e: FormEvent) {
    e.preventDefault();
    setErr(null);

    // Same-person duplicate check (frontend)
    if (pid0 && pid1 && Number(pid0) === Number(pid1)) {
      setErr('İki seat aynı kişi olamaz.');
      return;
    }

    setSaving(true);
    try {
      // Seat 0 işle
      await syncSeat(seat0, pid0 === '' ? null : Number(pid0), note0);
      // Seat 1 işle
      await syncSeat(seat1, pid1 === '' ? null : Number(pid1), note1);
      onSaved();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Kayıt başarısız');
    } finally {
      setSaving(false);
    }
  }

  /**
   * Tek bir seat'i sync et: mevcut atama × yeni state'e göre POST/PATCH/DELETE.
   */
  async function syncSeat(
    existing: DailyDuty | undefined,
    newPid: number | null,
    newNote: string,
  ) {
    if (!existing && newPid == null) return;        // boş × boş: no-op
    if (existing && newPid == null) {
      // Sil
      await api.delete(`/daily-duty/${existing.id}`);
      return;
    }
    if (!existing && newPid != null) {
      // Yeni ekle
      await api.post('/daily-duty', {
        day, duty_type: dutyType,
        personnel_id: newPid,
        note: newNote || null,
      });
      return;
    }
    // existing && newPid != null
    if (
      existing!.personnel_id === newPid &&
      (existing!.note || '') === newNote
    ) {
      // Değişiklik yok
      return;
    }
    await api.patch(`/daily-duty/${existing!.id}`, {
      personnel_id: newPid,
      note: newNote || null,
    });
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <form
        onSubmit={save}
        className="bg-white dark:bg-slate-800 rounded-lg shadow-xl w-full max-w-lg p-5 space-y-3"
      >
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-gray-900 dark:text-slate-100">
            {DUTY_LABEL[dutyType]} — {day}
          </h2>
          <button type="button" className="text-gray-500 dark:text-slate-400" onClick={onClose}>✕</button>
        </div>

        <SeatField
          label="1. Kişi"
          personnel={personnel}
          pid={pid0} setPid={setPid0}
          note={note0} setNote={setNote0}
        />
        {expectedCount >= 2 && (
          <SeatField
            label="2. Kişi"
            personnel={personnel}
            pid={pid1} setPid={setPid1}
            note={note1} setNote={setNote1}
          />
        )}

        {dutyType === 'lunch' && expectedCount >= 2 && (
          <p className="text-xs text-gray-500 dark:text-slate-400 -mt-1">
            <b>Öğlen nöbet kuralı:</b> 2 kişi mutlaka aynı lokasyondan olmalı
            (Ank-Ank veya İst-İst).
          </p>
        )}
        {dutyType === 'lunch' && expectedCount === 1 && (
          <p className="text-xs text-gray-500 dark:text-slate-400 -mt-1">
            <b>Cuma öğlen kuralı:</b> Sadece 1 kişi atanır; havuz config'teki
            <code> friday_lunch_pool </code>listesiyle sınırlıdır.
          </p>
        )}
        {locWarning && (
          <div className="text-xs text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-700 rounded px-2 py-1">
            ⚠ {locWarning}
          </div>
        )}

        {err && <div className="text-sm text-red-600 dark:text-red-400">{err}</div>}

        <div className="flex justify-end gap-2 pt-1">
          <button type="button" className="btn-ghost" onClick={onClose}>İptal</button>
          <button type="submit" className="btn-primary" disabled={saving}>
            {saving ? 'Kaydediliyor…' : 'Kaydet'}
          </button>
        </div>
        <p className="text-[10px] text-gray-500 dark:text-slate-400 pt-1">
          Dolu seat'i temizleyip kaydederseniz silinir. Manuel atamalar
          "Otomatik Üret" çağrısında korunur; "Sıfırla &amp; Üret" tümünü siler.
        </p>
      </form>
    </div>
  );
}


function SeatField({
  label, personnel, pid, setPid, note, setNote,
}: {
  label: string;
  personnel: Personnel[];
  pid: number | '';
  setPid: (v: number | '') => void;
  note: string;
  setNote: (v: string) => void;
}) {
  return (
    <div className="border border-gray-200 dark:border-slate-700 rounded p-2 space-y-2">
      <div className="text-xs font-semibold text-gray-700 dark:text-slate-200">{label}</div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <select
          className="input text-sm"
          value={pid}
          onChange={(e) => setPid(e.target.value === '' ? '' : Number(e.target.value))}
        >
          <option value="">— Boş —</option>
          {personnel.map((p) => (
            <option key={p.id} value={p.id}>
              {p.full_name} ({p.location === 'istanbul' ? 'İst' : 'Ank'})
            </option>
          ))}
        </select>
        <input
          className="input text-sm"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Not (opsiyonel)"
        />
      </div>
    </div>
  );
}
