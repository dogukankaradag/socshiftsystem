import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import {
  api,
  ROSTER_TEAM_LABEL,
  RosterEntry,
  RosterTeam,
  RosterUploadResult,
} from '../api/client';
import { useAuth } from '../auth/AuthContext';

const TEAMS: RosterTeam[] = ['l2', 'mssp'];

function fmtDate(s: string): string {
  // s: YYYY-MM-DD
  const [y, m, d] = s.split('-');
  return `${d}.${m}.${y}`;
}

function todayISO(): string {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}

export default function Roster() {
  const { user } = useAuth();
  const canEdit = user?.role === 'supervisor' || user?.role === 'admin';

  const [team, setTeam] = useState<RosterTeam>('l2');
  const [items, setItems] = useState<RosterEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [editing, setEditing] = useState<RosterEntry | null>(null);

  // filters
  const [from, setFrom] = useState<string>('');
  const [to, setTo] = useState<string>('');
  const [activeOnly, setActiveOnly] = useState(true);

  const fileRef = useRef<HTMLInputElement>(null);

  async function load() {
    setLoading(true);
    try {
      const params: any = { team };
      if (from) params.start_to = to || from;
      if (from) params.start_from = from;
      const r = await api.get('/roster', { params });
      let data: RosterEntry[] = r.data;
      if (activeOnly) {
        const today = todayISO();
        data = data.filter((x) => x.end_date >= today);
      }
      setItems(data);
    } catch (err: any) {
      setMsg(err?.response?.data?.detail || 'Yüklenemedi');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [team, from, to, activeOnly]);

  async function handleUpload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = fileRef.current?.files?.[0];
    if (!f) return;
    setUploading(true);
    setMsg(null);
    setWarnings([]);
    try {
      const fd = new FormData();
      fd.append('team', team);
      fd.append('file', f);
      const r = await api.post<RosterUploadResult>('/roster/upload', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setMsg(
        `${r.data.parsed_count} satır yüklendi. Grup: ${r.data.upload_batch || '—'}`,
      );
      setWarnings(r.data.warnings || []);
      if (fileRef.current) fileRef.current.value = '';
      load();
    } catch (err: any) {
      setMsg(err?.response?.data?.detail || 'Yükleme başarısız');
    } finally {
      setUploading(false);
    }
  }

  async function deleteOne(id: number) {
    if (!confirm('Bu kaydı silmek istiyor musunuz?')) return;
    await api.delete(`/roster/${id}`);
    load();
  }

  async function deleteBatch(batch: string | null) {
    if (!batch) return;
    if (!confirm('Bu yükleme grubundaki tüm kayıtları silmek istiyor musunuz?')) return;
    await api.delete(`/roster/batch/${batch}`);
    load();
  }

  const groupedByBatch = useMemo(() => {
    const map = new Map<string, RosterEntry[]>();
    for (const it of items) {
      const key = it.upload_batch || '_manual';
      const arr = map.get(key) || [];
      arr.push(it);
      map.set(key, arr);
    }
    return map;
  }, [items]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-semibold">Nöbetçi Listesi</h1>
          <p className="text-sm text-gray-500">
            L2 ekibi ve MSSP aylık vardiya çizelgesi. XLSX/PDF yükleyerek toplu
            olarak ekleyebilir veya elle satır girebilirsiniz.
          </p>
        </div>
        {canEdit && (
          <div className="flex gap-2">
            <button className="btn-ghost" onClick={() => setShowAdd((s) => !s)}>
              {showAdd ? 'Formu Kapat' : '+ Elle Ekle'}
            </button>
          </div>
        )}
      </div>

      <div className="card space-y-3">
        <div className="flex gap-2">
          {TEAMS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTeam(t)}
              className={`px-3 py-1.5 rounded-md border text-sm font-medium ${
                team === t
                  ? 'border-brand-600 bg-brand-50 text-brand-700'
                  : 'border-gray-300 text-gray-700 hover:bg-gray-50'
              }`}
            >
              {ROSTER_TEAM_LABEL[t]}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div>
            <label className="label">Başlangıç (en erken)</label>
            <input
              type="date"
              className="input"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
            />
          </div>
          <div>
            <label className="label">Bitiş (en geç)</label>
            <input
              type="date"
              className="input"
              value={to}
              onChange={(e) => setTo(e.target.value)}
            />
          </div>
          <label className="flex items-center gap-2 text-sm text-gray-700 mt-6">
            <input
              type="checkbox"
              checked={activeOnly}
              onChange={(e) => setActiveOnly(e.target.checked)}
            />
            Sadece bugün ve sonrası
          </label>
          <div className="flex items-end">
            <button className="btn-ghost" onClick={load}>
              Yenile
            </button>
          </div>
        </div>

        {canEdit && (
          <form
            onSubmit={handleUpload}
            className="flex flex-wrap items-end gap-3 bg-gray-50 border border-dashed border-gray-300 rounded-md p-3"
          >
            <div>
              <label className="label">Dosya Yükle (.xlsx / .pdf)</label>
              <input
                ref={fileRef}
                type="file"
                accept=".xlsx,.xlsm,.pdf"
                className="text-sm"
              />
              <p className="text-xs text-gray-500 mt-1">
                Seçili ekip: <b>{ROSTER_TEAM_LABEL[team]}</b>. Dosya saklanmaz,
                yalnızca satırlar veritabanına yazılır.
              </p>
            </div>
            <button type="submit" className="btn-primary" disabled={uploading}>
              {uploading ? 'Yükleniyor…' : 'Yükle ve Parse Et'}
            </button>
          </form>
        )}

        {msg && <div className="text-sm text-gray-700">{msg}</div>}
        {warnings.length > 0 && (
          <details className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded p-2">
            <summary className="cursor-pointer">
              Uyarılar ({warnings.length})
            </summary>
            <ul className="mt-1 list-disc pl-5 space-y-0.5">
              {warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </details>
        )}
      </div>

      {showAdd && canEdit && (
        <AddRosterForm
          team={team}
          onDone={() => {
            setShowAdd(false);
            load();
          }}
        />
      )}

      {editing && canEdit && (
        <EditRosterModal
          entry={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}

      <div className="card p-0 overflow-hidden">
        {loading ? (
          <div className="p-6 text-gray-500">Yükleniyor…</div>
        ) : items.length === 0 ? (
          <div className="p-6 text-gray-500">
            Bu ekipte görüntülenecek kayıt yok.
          </div>
        ) : (
          <div>
            {[...groupedByBatch.entries()].map(([batch, rows]) => (
              <div key={batch}>
                <div className="flex items-center justify-between px-4 py-2 bg-gray-50 border-b text-xs text-gray-600">
                  <span>
                    {batch === '_manual'
                      ? 'Elle eklenen'
                      : `Yükleme grubu: ${batch.slice(0, 8)}…`}{' '}
                    · {rows.length} kayıt
                  </span>
                  {canEdit && batch !== '_manual' && (
                    <button
                      className="btn-ghost text-xs"
                      onClick={() => deleteBatch(batch)}
                    >
                      Grubu Sil
                    </button>
                  )}
                </div>
                <table className="w-full text-sm">
                  <thead className="text-left text-xs uppercase text-gray-500">
                    <tr>
                      <th className="px-4 py-2">Ad Soyad</th>
                      <th className="px-4 py-2">Başlangıç</th>
                      <th className="px-4 py-2">Bitiş</th>
                      {team === 'mssp' && <th className="px-4 py-2">Vardiya</th>}
                      <th className="px-4 py-2">Not</th>
                      {canEdit && <th className="px-4 py-2"></th>}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {rows.map((r) => (
                      <tr key={r.id}>
                        <td className="px-4 py-2 font-medium text-gray-900">
                          {r.person_name}
                        </td>
                        <td className="px-4 py-2 text-gray-700">
                          {fmtDate(r.start_date)}
                        </td>
                        <td className="px-4 py-2 text-gray-700">
                          {fmtDate(r.end_date)}
                        </td>
                        {team === 'mssp' && (
                          <td className="px-4 py-2 text-gray-700">
                            {r.shift_label || '—'}
                          </td>
                        )}
                        <td className="px-4 py-2 text-gray-500">
                          {r.notes || '—'}
                        </td>
                        {canEdit && (
                          <td className="px-4 py-2 text-right whitespace-nowrap space-x-2">
                            <button
                              className="text-xs text-gray-700 hover:text-brand-700"
                              onClick={() => setEditing(r)}
                            >
                              Düzenle
                            </button>
                            <button
                              className="text-xs text-red-600 hover:underline"
                              onClick={() => deleteOne(r.id)}
                            >
                              Sil
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function AddRosterForm({
  team,
  onDone,
}: {
  team: RosterTeam;
  onDone: () => void;
}) {
  const [personName, setPersonName] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [shiftLabel, setShiftLabel] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setSaving(true);
    try {
      await api.post('/roster', {
        team,
        person_name: personName.trim(),
        start_date: startDate,
        end_date: endDate || startDate,
        shift_label: shiftLabel.trim() || null,
        notes: notes.trim() || null,
      });
      onDone();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Kayıt başarısız');
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="card space-y-3">
      <h2 className="font-semibold text-gray-900">
        Elle kayıt ekle — {ROSTER_TEAM_LABEL[team]}
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className="label">Ad Soyad</label>
          <input
            className="input"
            value={personName}
            onChange={(e) => setPersonName(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="label">Başlangıç Tarihi</label>
          <input
            className="input"
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="label">Bitiş Tarihi</label>
          <input
            className="input"
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
          />
        </div>
        {team === 'mssp' && (
          <div>
            <label className="label">Vardiya Etiketi (A/B/C)</label>
            <input
              className="input"
              maxLength={16}
              value={shiftLabel}
              onChange={(e) => setShiftLabel(e.target.value)}
              placeholder="A"
            />
          </div>
        )}
        <div className="md:col-span-2">
          <label className="label">Not (opsiyonel)</label>
          <input
            className="input"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            maxLength={512}
          />
        </div>
      </div>
      {err && <div className="text-sm text-red-600">{err}</div>}
      <div className="flex gap-2 justify-end">
        <button type="button" className="btn-ghost" onClick={onDone}>
          İptal
        </button>
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? 'Kaydediliyor…' : 'Kaydet'}
        </button>
      </div>
    </form>
  );
}

function EditRosterModal({
  entry,
  onClose,
  onSaved,
}: {
  entry: RosterEntry;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [team, setTeam] = useState<RosterTeam>(entry.team);
  const [personName, setPersonName] = useState(entry.person_name);
  const [startDate, setStartDate] = useState(entry.start_date);
  const [endDate, setEndDate] = useState(entry.end_date);
  const [shiftLabel, setShiftLabel] = useState(entry.shift_label || '');
  const [notes, setNotes] = useState(entry.notes || '');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setSaving(true);
    try {
      await api.patch(`/roster/${entry.id}`, {
        team,
        person_name: personName.trim(),
        start_date: startDate,
        end_date: endDate || startDate,
        shift_label: shiftLabel.trim() || null,
        notes: notes.trim() || null,
      });
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
        className="bg-white rounded-lg shadow-xl w-full max-w-lg p-5 space-y-3"
      >
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">
            Nöbet Kaydını Düzenle — #{entry.id}
          </h2>
          <button type="button" className="text-gray-500" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className="label">Ekip</label>
            <select
              className="input"
              value={team}
              onChange={(e) => setTeam(e.target.value as RosterTeam)}
            >
              {(['l2', 'mssp'] as RosterTeam[]).map((t) => (
                <option key={t} value={t}>
                  {ROSTER_TEAM_LABEL[t]}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Ad Soyad</label>
            <input
              className="input"
              value={personName}
              onChange={(e) => setPersonName(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="label">Başlangıç Tarihi</label>
            <input
              type="date"
              className="input"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="label">Bitiş Tarihi</label>
            <input
              type="date"
              className="input"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </div>
          {team === 'mssp' && (
            <div>
              <label className="label">Vardiya Etiketi (A/B/C)</label>
              <input
                className="input"
                maxLength={16}
                value={shiftLabel}
                onChange={(e) => setShiftLabel(e.target.value)}
              />
            </div>
          )}
          <div className="md:col-span-2">
            <label className="label">Not</label>
            <input
              className="input"
              maxLength={512}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>
        </div>

        {err && <div className="text-sm text-red-600">{err}</div>}

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
