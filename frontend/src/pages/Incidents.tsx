import { FormEvent, useEffect, useState } from 'react';
import { api, Incident, IncidentStatus, PRIORITY_LABEL, Priority } from '../api/client';
import PriorityBadge from '../components/PriorityBadge';
import { useAuth } from '../auth/AuthContext';

const STATUSES: IncidentStatus[] = ['open', 'in_progress', 'resolved', 'closed'];
const PRIORITIES: Priority[] = ['low', 'medium', 'high', 'critical'];

const STATUS_LABEL: Record<IncidentStatus, string> = {
  open: 'açık',
  in_progress: 'devam ediyor',
  resolved: 'çözüldü',
  closed: 'kapalı',
};

const STATUS_CLASS: Record<IncidentStatus, string> = {
  open: 'bg-red-100 text-red-800',
  in_progress: 'bg-yellow-100 text-yellow-800',
  resolved: 'bg-green-100 text-green-800',
  closed: 'bg-gray-100 text-gray-700',
};

export default function Incidents() {
  const { user } = useAuth();
  const canDelete = user?.role === 'supervisor' || user?.role === 'admin';

  const [items, setItems] = useState<Incident[]>([]);
  const [filterStatus, setFilterStatus] = useState<IncidentStatus | ''>('');
  const [showNew, setShowNew] = useState(false);
  const [editing, setEditing] = useState<Incident | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    const r = await api.get('/incidents', {
      params: filterStatus ? { status: filterStatus } : {},
    });
    setItems(r.data);
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, [filterStatus]);

  async function setStatus(id: number, status: IncidentStatus) {
    await api.patch(`/incidents/${id}`, { status });
    load();
  }

  async function deleteIncident(inc: Incident) {
    if (
      !confirm(
        `Olay #${inc.id} "${inc.title}" silinecek. Bağlı girişler korunur ama olay referansını kaybeder. Onaylıyor musunuz?`,
      )
    )
      return;
    setBusyId(inc.id);
    try {
      await api.delete(`/incidents/${inc.id}`);
      load();
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Silme başarısız');
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Olaylar</h1>
        <div className="flex gap-2 items-center">
          <select
            className="input w-48"
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value as IncidentStatus | '')}
          >
            <option value="">Tüm durumlar</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABEL[s]}
              </option>
            ))}
          </select>
          <button className="btn-primary" onClick={() => setShowNew(true)}>
            + Yeni Olay
          </button>
        </div>
      </div>

      {showNew && <NewIncidentForm onDone={() => { setShowNew(false); load(); }} />}

      <div className="card p-0 overflow-hidden">
        {loading ? (
          <div className="p-6 text-gray-500">Yükleniyor…</div>
        ) : items.length === 0 ? (
          <div className="p-6 text-gray-500">Bu filtreye uygun olay yok.</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
              <tr>
                <th className="px-4 py-2">#</th>
                <th className="px-4 py-2">Başlık</th>
                <th className="px-4 py-2">Öncelik</th>
                <th className="px-4 py-2">Durum</th>
                <th className="px-4 py-2">Açılış</th>
                <th className="px-4 py-2">Girişler</th>
                <th className="px-4 py-2">İşlem</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {items.map((i) => (
                <tr key={i.id}>
                  <td className="px-4 py-2 text-gray-500">#{i.id}</td>
                  <td className="px-4 py-2">
                    <div className="font-medium text-gray-900">{i.title}</div>
                    <div className="text-gray-500 line-clamp-1">{i.description}</div>
                  </td>
                  <td className="px-4 py-2"><PriorityBadge priority={i.priority} /></td>
                  <td className="px-4 py-2">
                    <span className={`pill ${STATUS_CLASS[i.status]}`}>{STATUS_LABEL[i.status]}</span>
                  </td>
                  <td className="px-4 py-2 text-gray-500">
                    {new Date(i.opened_at).toLocaleDateString('tr-TR')}
                  </td>
                  <td className="px-4 py-2 text-gray-500">{i.entry_count}</td>
                  <td className="px-4 py-2 whitespace-nowrap space-x-2">
                    <select
                      className="input py-1 text-xs inline-block w-auto"
                      value={i.status}
                      onChange={(e) => setStatus(i.id, e.target.value as IncidentStatus)}
                    >
                      {STATUSES.map((s) => (
                        <option key={s} value={s}>
                          {STATUS_LABEL[s]}
                        </option>
                      ))}
                    </select>
                    <button
                      className="text-xs text-gray-600 hover:text-brand-700"
                      onClick={() => setEditing(i)}
                    >
                      Düzenle
                    </button>
                    {canDelete && (
                      <button
                        className="text-xs text-red-600 hover:underline"
                        onClick={() => deleteIncident(i)}
                        disabled={busyId === i.id}
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
        <IncidentEditModal
          incident={editing}
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

function NewIncidentForm({ onDone }: { onDone: () => void }) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<Priority>('high');
  const [saving, setSaving] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post('/incidents', { title, description, priority });
      onDone();
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="card space-y-3">
      <h2 className="font-semibold text-gray-900">Yeni olay</h2>
      <input
        className="input"
        placeholder="Başlık"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        required
      />
      <textarea
        className="input min-h-[90px]"
        placeholder="Açıklama"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        required
      />
      <div>
        <label className="label">Öncelik</label>
        <select
          className="input"
          value={priority}
          onChange={(e) => setPriority(e.target.value as Priority)}
        >
          {PRIORITIES.map((p) => (
            <option key={p} value={p}>
              {PRIORITY_LABEL[p]}
            </option>
          ))}
        </select>
      </div>
      <div className="flex gap-2 justify-end">
        <button type="button" className="btn-ghost" onClick={onDone}>
          İptal
        </button>
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? 'Kaydediliyor…' : 'Olayı Aç'}
        </button>
      </div>
    </form>
  );
}

function IncidentEditModal({
  incident,
  onClose,
  onSaved,
}: {
  incident: Incident;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [title, setTitle] = useState(incident.title);
  const [description, setDescription] = useState(incident.description);
  const [priority, setPriority] = useState<Priority>(incident.priority);
  const [resolutionNotes, setResolutionNotes] = useState(incident.resolution_notes || '');
  const [tags, setTags] = useState(incident.tags || '');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setSaving(true);
    try {
      await api.patch(`/incidents/${incident.id}`, {
        title,
        description,
        priority,
        resolution_notes: resolutionNotes || null,
        tags: tags || null,
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
        className="bg-white rounded-lg shadow-xl w-full max-w-lg p-5 space-y-3 max-h-[90vh] overflow-y-auto"
      >
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">Olayı Düzenle — #{incident.id}</h2>
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
          />
        </div>
        <div>
          <label className="label">Açıklama</label>
          <textarea
            className="input min-h-[100px]"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="label">Öncelik</label>
          <select
            className="input"
            value={priority}
            onChange={(e) => setPriority(e.target.value as Priority)}
          >
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {PRIORITY_LABEL[p]}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Çözüm Notu (opsiyonel)</label>
          <textarea
            className="input min-h-[70px]"
            value={resolutionNotes}
            onChange={(e) => setResolutionNotes(e.target.value)}
          />
        </div>
        <div>
          <label className="label">Etiketler (virgülle, opsiyonel)</label>
          <input
            className="input"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder="ddos, banka, dış"
          />
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
