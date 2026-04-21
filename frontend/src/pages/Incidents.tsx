import { FormEvent, useEffect, useState } from 'react';
import { api, Incident, IncidentStatus, PRIORITY_LABEL, Priority } from '../api/client';
import PriorityBadge from '../components/PriorityBadge';

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
  const [items, setItems] = useState<Incident[]>([]);
  const [filterStatus, setFilterStatus] = useState<IncidentStatus | ''>('');
  const [showNew, setShowNew] = useState(false);
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
                  <td className="px-4 py-2">
                    <select
                      className="input py-1 text-xs"
                      value={i.status}
                      onChange={(e) => setStatus(i.id, e.target.value as IncidentStatus)}
                    >
                      {STATUSES.map((s) => (
                        <option key={s} value={s}>
                          {STATUS_LABEL[s]}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
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
