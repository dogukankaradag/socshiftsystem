import { FormEvent, useEffect, useState } from 'react';
import { api, ROLE_LABEL, Role, User } from '../api/client';

const ROLES: Role[] = ['operator', 'supervisor', 'admin'];

interface MailingList {
  id: number;
  name: string;
  recipients: string;
  cc_recipients: string | null;
  is_default: boolean;
  shift_type: string | null;
}

export default function Admin() {
  const [users, setUsers] = useState<User[]>([]);
  const [lists, setLists] = useState<MailingList[]>([]);
  const [tab, setTab] = useState<'users' | 'mailing'>('users');

  async function load() {
    const [u, m] = await Promise.all([api.get('/users'), api.get('/mailing-lists')]);
    setUsers(u.data);
    setLists(m.data);
  }
  useEffect(() => {
    load();
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Yönetim</h1>
      <div className="flex gap-2 border-b border-gray-200">
        {(['users', 'mailing'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-2 text-sm font-medium ${
              tab === t ? 'text-brand-700 border-b-2 border-brand-700' : 'text-gray-500'
            }`}
          >
            {t === 'users' ? 'Kullanıcılar' : 'Mail Listeleri'}
          </button>
        ))}
      </div>
      {tab === 'users' ? (
        <UsersTab users={users} reload={load} />
      ) : (
        <MailingTab lists={lists} reload={load} />
      )}
    </div>
  );
}

function UsersTab({ users, reload }: { users: User[]; reload: () => void }) {
  const [showNew, setShowNew] = useState(false);
  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <button className="btn-primary" onClick={() => setShowNew(true)}>
          + Yeni Kullanıcı
        </button>
      </div>
      {showNew && <NewUserForm onDone={() => { setShowNew(false); reload(); }} />}
      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-2">#</th>
              <th className="px-4 py-2">E-posta</th>
              <th className="px-4 py-2">Ad Soyad</th>
              <th className="px-4 py-2">Rol</th>
              <th className="px-4 py-2">Aktif</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {users.map((u) => (
              <tr key={u.id}>
                <td className="px-4 py-2 text-gray-500">#{u.id}</td>
                <td className="px-4 py-2">{u.email}</td>
                <td className="px-4 py-2">{u.full_name}</td>
                <td className="px-4 py-2">
                  <select
                    className="input py-1 text-xs"
                    value={u.role}
                    onChange={async (e) => {
                      await api.patch(`/users/${u.id}`, { role: e.target.value });
                      reload();
                    }}
                  >
                    {ROLES.map((r) => (
                      <option key={r} value={r}>
                        {ROLE_LABEL[r]}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-4 py-2">{u.is_active ? '✓' : '✗'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function NewUserForm({ onDone }: { onDone: () => void }) {
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [pw, setPw] = useState('');
  const [role, setRole] = useState<Role>('operator');
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.post('/users', { email, full_name: name, password: pw, role });
      onDone();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Başarısız');
    }
  }
  return (
    <form onSubmit={submit} className="card grid grid-cols-2 gap-3">
      <input
        className="input"
        placeholder="e-posta"
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        required
      />
      <input
        className="input"
        placeholder="ad soyad"
        value={name}
        onChange={(e) => setName(e.target.value)}
        required
      />
      <input
        className="input"
        placeholder="parola (en az 8 karakter)"
        type="password"
        value={pw}
        onChange={(e) => setPw(e.target.value)}
        required
      />
      <select className="input" value={role} onChange={(e) => setRole(e.target.value as Role)}>
        {ROLES.map((r) => (
          <option key={r} value={r}>
            {ROLE_LABEL[r]}
          </option>
        ))}
      </select>
      {error && <div className="col-span-2 text-sm text-red-600">{error}</div>}
      <div className="col-span-2 flex justify-end gap-2">
        <button type="button" className="btn-ghost" onClick={onDone}>
          İptal
        </button>
        <button type="submit" className="btn-primary">
          Oluştur
        </button>
      </div>
    </form>
  );
}

function MailingTab({ lists, reload }: { lists: MailingList[]; reload: () => void }) {
  const [name, setName] = useState('');
  const [recipients, setRecipients] = useState('');
  const [ccRecipients, setCcRecipients] = useState('');
  const [isDefault, setIsDefault] = useState(false);

  async function add(e: FormEvent) {
    e.preventDefault();
    await api.post('/mailing-lists', {
      name,
      recipients,
      cc_recipients: ccRecipients || null,
      is_default: isDefault,
    });
    setName('');
    setRecipients('');
    setCcRecipients('');
    setIsDefault(false);
    reload();
  }

  async function remove(id: number) {
    if (!confirm('Bu listeyi silmek istediğinize emin misiniz?')) return;
    await api.delete(`/mailing-lists/${id}`);
    reload();
  }

  return (
    <div className="space-y-3">
      <form onSubmit={add} className="card grid grid-cols-3 gap-3 items-end">
        <div>
          <label className="label">İsim</label>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
        <div className="col-span-2">
          <label className="label">TO — Alıcılar (virgülle ayırın)</label>
          <input
            className="input"
            value={recipients}
            onChange={(e) => setRecipients(e.target.value)}
            required
            placeholder="ornek@sirket.com, ops@sirket.com"
          />
        </div>
        <div className="col-span-3">
          <label className="label">CC — Bilgi Alıcıları (opsiyonel, virgülle ayırın)</label>
          <input
            className="input"
            value={ccRecipients}
            onChange={(e) => setCcRecipients(e.target.value)}
            placeholder="yonetici@sirket.com"
          />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={isDefault}
            onChange={(e) => setIsDefault(e.target.checked)}
          />
          Varsayılan olarak ayarla
        </label>
        <div className="col-span-2 flex justify-end">
          <button className="btn-primary" type="submit">
            Liste Ekle
          </button>
        </div>
      </form>
      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-2">İsim</th>
              <th className="px-4 py-2">TO</th>
              <th className="px-4 py-2">CC</th>
              <th className="px-4 py-2">Varsayılan</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {lists.map((l) => (
              <tr key={l.id}>
                <td className="px-4 py-2">{l.name}</td>
                <td className="px-4 py-2 text-gray-600">{l.recipients}</td>
                <td className="px-4 py-2 text-gray-600">{l.cc_recipients || '—'}</td>
                <td className="px-4 py-2">{l.is_default ? '✓' : ''}</td>
                <td className="px-4 py-2 text-right">
                  <button
                    className="btn-ghost text-red-600 text-xs"
                    onClick={() => remove(l.id)}
                  >
                    Sil
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
