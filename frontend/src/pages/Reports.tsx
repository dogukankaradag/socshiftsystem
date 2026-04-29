import { FormEvent, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  api,
  detectShiftType,
  downloadFile,
  REPORT_STATUS_LABEL,
  Report,
  ReportStatus,
  Shift,
  SHIFT_TYPE_LABEL,
  ShiftType,
} from '../api/client';
import { useAuth } from '../auth/AuthContext';

function splitListInput(v: string): string[] {
  return v
    .split(/[,;\s]+/)
    .map((x) => x.trim())
    .filter(Boolean);
}

function isoToLocalInput(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  const tr = new Date(d.getTime() + 3 * 60 * 60 * 1000);
  return tr.toISOString().slice(0, 16);
}

const STATUS_CLASS: Record<ReportStatus, string> = {
  draft: 'bg-gray-100 text-gray-700',
  scheduled: 'bg-blue-100 text-blue-800',
  dispatched: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
};

// Geriye dönük uyum: alttaki kodlar splitList kullanıyor.
const splitList = splitListInput;

export default function Reports() {
  const { user } = useAuth();
  const canGenerate = user?.role === 'supervisor' || user?.role === 'admin';
  const [shifts, setShifts] = useState<Shift[]>([]);
  const [selectedShift, setSelectedShift] = useState<number | ''>('');
  const [reports, setReports] = useState<Report[]>([]);
  const [working, setWorking] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [editing, setEditing] = useState<Report | null>(null);

  // Son aşamada A/B/C hangi vardiya raporu oluşturulacağı seçilir.
  // Varsayılan olarak geçerli saate göre (GMT+3) tahmin edilir.
  const [shiftTypeChoice, setShiftTypeChoice] = useState<ShiftType>(detectShiftType());
  const [toInput, setToInput] = useState('');
  const [ccInput, setCcInput] = useState('');
  const [scheduleAt, setScheduleAt] = useState(''); // local datetime (GMT+3)
  const [subjectOverride, setSubjectOverride] = useState('');

  async function load() {
    const [s, r] = await Promise.all([
      api.get('/shifts', { params: { limit: 20 } }),
      api.get('/reports', { params: { limit: 30 } }),
    ]);
    setShifts(s.data);
    setReports(r.data);
    if (!selectedShift && s.data.length) setSelectedShift(s.data[0].id);
  }

  useEffect(() => {
    load();
  }, []);

  async function generate(options: { dispatch: boolean; schedule: boolean }) {
    if (!selectedShift) return;
    setWorking(true);
    setMsg(null);
    try {
      const payload: any = { shift_id: selectedShift, shift_type: shiftTypeChoice };

      if (subjectOverride.trim()) {
        payload.subject_override = subjectOverride.trim();
      }

      const toList = splitList(toInput);
      const ccList = splitList(ccInput);
      if (toList.length) payload.to_recipients = toList;
      if (ccList.length) payload.cc_recipients = ccList;

      if (options.schedule) {
        if (!scheduleAt) {
          setMsg('Lütfen planlama zamanını seçin (GMT+3).');
          setWorking(false);
          return;
        }
        // Send naive local datetime; backend interprets it as Europe/Istanbul (GMT+3)
        payload.scheduled_at = scheduleAt;
        payload.dispatch = false;
      } else {
        payload.dispatch = options.dispatch;
      }

      const r = await api.post('/reports/generate', payload);

      if (options.schedule) {
        setMsg(
          `Rapor #${r.data.id} ${scheduleAt} (GMT+3) zamanına planlandı.`,
        );
      } else if (options.dispatch) {
        setMsg(
          `Rapor #${r.data.id} oluşturuldu — durum: ${
            REPORT_STATUS_LABEL[r.data.status as ReportStatus] || r.data.status
          }.`,
        );
      } else {
        setMsg(`Rapor #${r.data.id} taslak olarak oluşturuldu.`);
      }
      load();
    } catch (err: any) {
      setMsg(err?.response?.data?.detail || 'Rapor oluşturma başarısız');
    } finally {
      setWorking(false);
    }
  }

  async function dispatchExisting(id: number) {
    setWorking(true);
    try {
      await api.post(`/reports/${id}/dispatch`);
      load();
    } finally {
      setWorking(false);
    }
  }

  async function cancelSchedule(id: number) {
    if (!confirm('Bu zamanlamayı iptal etmek istiyor musunuz?')) return;
    setWorking(true);
    try {
      await api.post(`/reports/${id}/cancel-schedule`);
      load();
    } finally {
      setWorking(false);
    }
  }

  async function deleteReport(r: Report) {
    if (r.status === 'dispatched') {
      alert('Gönderilmiş rapor denetim kaydı için silinemez.');
      return;
    }
    if (
      !confirm(
        `Rapor #${r.id} silinecek (${REPORT_STATUS_LABEL[r.status]}). Onaylıyor musunuz?`,
      )
    )
      return;
    setWorking(true);
    try {
      await api.delete(`/reports/${r.id}`);
      load();
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Silme başarısız');
    } finally {
      setWorking(false);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Raporlar</h1>

      {canGenerate && (
        <div className="card space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="label">Vardiya (veritabanı)</label>
              <select
                className="input"
                value={selectedShift}
                onChange={(e) => setSelectedShift(Number(e.target.value))}
              >
                {shifts.map((s) => (
                  <option key={s.id} value={s.id}>
                    #{s.id} · {SHIFT_TYPE_LABEL[s.shift_type]} ·{' '}
                    {new Date(s.started_at).toLocaleString('tr-TR')} ({s.entry_count})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="label">Rapor Vardiyası (son seçim)</label>
              <div className="flex gap-2">
                {(['a', 'b', 'c'] as ShiftType[]).map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setShiftTypeChoice(t)}
                    className={`flex-1 rounded-md border px-3 py-2 text-sm font-medium transition ${
                      shiftTypeChoice === t
                        ? 'border-brand-600 bg-brand-50 text-brand-700'
                        : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
                    }`}
                  >
                    {SHIFT_TYPE_LABEL[t]}
                  </button>
                ))}
              </div>
              <p className="text-xs text-gray-500 mt-1">
                A: 07:30–15:30 · B: 15:30–23:30 · C: 23:30–07:30 (GMT+3). Rapor bu etiketle
                oluşturulur; gerekirse seçimi değiştirin.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="label">TO — Alıcılar (virgül / boşluk ile ayırın)</label>
              <input
                className="input"
                value={toInput}
                onChange={(e) => setToInput(e.target.value)}
                placeholder="ops@sirket.com, noc@sirket.com"
              />
              <p className="text-xs text-gray-500 mt-1">
                Boş bırakılırsa varsayılan mail listesi kullanılır.
              </p>
            </div>
            <div>
              <label className="label">CC — Bilgi Alıcıları (opsiyonel)</label>
              <input
                className="input"
                value={ccInput}
                onChange={(e) => setCcInput(e.target.value)}
                placeholder="yonetici@sirket.com"
              />
            </div>
          </div>

          <div>
            <label className="label">Mail Konusu (opsiyonel)</label>
            <input
              className="input"
              value={subjectOverride}
              onChange={(e) => setSubjectOverride(e.target.value)}
              placeholder={`Varsayılan: MSSP Vardiya Raporu — ${SHIFT_TYPE_LABEL[shiftTypeChoice]} (tarih)`}
              maxLength={255}
            />
            <p className="text-xs text-gray-500 mt-1">
              Boş bırakılırsa "MSSP Vardiya Raporu — {SHIFT_TYPE_LABEL[shiftTypeChoice]} (tarih)"
              biçiminde oluşturulur.
            </p>
          </div>

          <div>
            <label className="label">Zamanlama (GMT+3) — opsiyonel</label>
            <input
              type="datetime-local"
              className="input"
              value={scheduleAt}
              onChange={(e) => setScheduleAt(e.target.value)}
            />
            <p className="text-xs text-gray-500 mt-1">
              Zamanlanmış raporlar belirtilen saatte otomatik olarak gönderilir (örn. 18:00).
            </p>
          </div>

          <div className="flex flex-wrap gap-2 justify-end">
            <button
              className="btn-ghost"
              disabled={working}
              onClick={() => generate({ dispatch: false, schedule: false })}
            >
              Taslak oluştur
            </button>
            <button
              className="btn-ghost"
              disabled={working || !scheduleAt}
              onClick={() => generate({ dispatch: false, schedule: true })}
            >
              Planla (GMT+3)
            </button>
            <button
              className="btn-primary"
              disabled={working}
              onClick={() => generate({ dispatch: true, schedule: false })}
            >
              Oluştur & Gönder
            </button>
          </div>
        </div>
      )}

      {msg && <div className="text-sm text-gray-700">{msg}</div>}

      <div className="card p-0 overflow-hidden">
        {reports.length === 0 ? (
          <div className="p-6 text-gray-500">Henüz rapor yok.</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
              <tr>
                <th className="px-4 py-2">#</th>
                <th className="px-4 py-2">Başlık</th>
                <th className="px-4 py-2">Durum</th>
                <th className="px-4 py-2">Planlandı</th>
                <th className="px-4 py-2">Gönderildi</th>
                <th className="px-4 py-2">Oluşturuldu</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {reports.map((r) => (
                <tr key={r.id}>
                  <td className="px-4 py-2 text-gray-500">#{r.id}</td>
                  <td className="px-4 py-2">
                    <Link
                      to={`/reports/${r.id}`}
                      className="font-medium text-brand-700 hover:underline"
                    >
                      {r.title}
                    </Link>
                    {r.error_message && (
                      <div className="text-xs text-red-600">{r.error_message}</div>
                    )}
                  </td>
                  <td className="px-4 py-2">
                    <span className={`pill ${STATUS_CLASS[r.status] || ''}`}>
                      {REPORT_STATUS_LABEL[r.status]}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-gray-500">
                    {r.scheduled_at ? new Date(r.scheduled_at).toLocaleString('tr-TR') : '—'}
                  </td>
                  <td className="px-4 py-2 text-gray-500">
                    {r.dispatched_at ? new Date(r.dispatched_at).toLocaleString('tr-TR') : '—'}
                  </td>
                  <td className="px-4 py-2 text-gray-500">
                    {new Date(r.created_at).toLocaleString('tr-TR')}
                  </td>
                  <td className="px-4 py-2 text-right space-x-2 whitespace-nowrap">
                    {canGenerate && r.status === 'scheduled' && (
                      <button
                        className="btn-ghost text-xs"
                        onClick={() => cancelSchedule(r.id)}
                      >
                        Planlamayı İptal
                      </button>
                    )}
                    {canGenerate &&
                      r.status !== 'dispatched' &&
                      r.status !== 'scheduled' && (
                        <button
                          className="btn-ghost text-xs"
                          onClick={() => dispatchExisting(r.id)}
                        >
                          Gönder
                        </button>
                      )}
                    {canGenerate && r.status !== 'dispatched' && (
                      <button
                        className="btn-ghost text-xs"
                        onClick={() => setEditing(r)}
                      >
                        Düzenle
                      </button>
                    )}
                    <button
                      className="btn-ghost text-xs"
                      onClick={() =>
                        downloadFile(`/reports/${r.id}/export.pdf`, `rapor_${r.id}.pdf`)
                      }
                    >
                      PDF
                    </button>
                    {canGenerate && r.status !== 'dispatched' && (
                      <button
                        className="btn-ghost text-xs text-red-600"
                        onClick={() => deleteReport(r)}
                      >
                        Sil
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {editing && (
        <ReportEditModal
          report={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}
    </div>
  );
}

function ReportEditModal({
  report,
  onClose,
  onSaved,
}: {
  report: Report;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [title, setTitle] = useState(report.title);
  const [summary, setSummary] = useState(report.summary || '');
  const [body, setBody] = useState(report.body_markdown || '');
  const [recipients, setRecipients] = useState(report.recipients || '');
  const [ccRecipients, setCcRecipients] = useState(report.cc_recipients || '');
  const [scheduledAt, setScheduledAt] = useState(isoToLocalInput(report.scheduled_at));
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setSaving(true);
    try {
      const payload: any = {
        title,
        summary,
        body_markdown: body,
      };
      const toList = splitListInput(recipients);
      const ccList = splitListInput(ccRecipients);
      payload.recipients = toList.length ? toList : null;
      payload.cc_recipients = ccList.length ? ccList : null;
      // scheduledAt: '' -> null (planlamayı kaldır), dolu -> backend GMT+3 -> UTC
      payload.scheduled_at = scheduledAt || null;

      await api.patch(`/reports/${report.id}`, payload);
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
        className="bg-white rounded-lg shadow-xl w-full max-w-2xl p-5 space-y-3 max-h-[90vh] overflow-y-auto"
      >
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">
            Raporu Düzenle — #{report.id}
          </h2>
          <button type="button" className="text-gray-500" onClick={onClose}>
            ✕
          </button>
        </div>

        <div>
          <label className="label">Başlık</label>
          <input
            className="input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            maxLength={255}
          />
        </div>

        <div>
          <label className="label">Özet</label>
          <textarea
            className="input min-h-[80px]"
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
          />
        </div>

        <div>
          <label className="label">Gövde (Markdown)</label>
          <textarea
            className="input min-h-[200px] font-mono text-xs"
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          <p className="text-xs text-gray-500 mt-1">
            HTML/PDF önbelleği temizlenir; bir sonraki önizlemede yeniden render
            edilir.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className="label">TO Alıcıları (virgülle)</label>
            <input
              className="input"
              value={recipients}
              onChange={(e) => setRecipients(e.target.value)}
              placeholder="ops@sirket.com, noc@sirket.com"
            />
          </div>
          <div>
            <label className="label">CC Alıcıları (opsiyonel)</label>
            <input
              className="input"
              value={ccRecipients}
              onChange={(e) => setCcRecipients(e.target.value)}
            />
          </div>
        </div>

        <div>
          <label className="label">Planlama (GMT+3, opsiyonel)</label>
          <div className="flex gap-2">
            <input
              type="datetime-local"
              className="input"
              value={scheduledAt}
              onChange={(e) => setScheduledAt(e.target.value)}
            />
            {scheduledAt && (
              <button
                type="button"
                className="btn-ghost text-xs"
                onClick={() => setScheduledAt('')}
              >
                Planlamayı kaldır
              </button>
            )}
          </div>
          <p className="text-xs text-gray-500 mt-1">
            Boş bırakılırsa planlama iptal edilir; durum "taslak"a düşer.
            Tarih girilirse durum "zamanlandı"ya yükselir.
          </p>
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
