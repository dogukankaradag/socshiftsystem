import { FormEvent, useEffect, useState } from 'react';
import { api, ROLE_LABEL, Role, ShiftType, SHIFT_TYPE_LABEL, User } from '../api/client';
import { useAuth } from '../auth/AuthContext';

const ROLES: Role[] = ['operator', 'supervisor', 'admin'];

interface MailingList {
  id: number;
  name: string;
  recipients: string;
  cc_recipients: string | null;
  is_default: boolean;
  shift_type: ShiftType | null;
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
  const { user: me } = useAuth();
  const [showNew, setShowNew] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);

  async function toggleActive(u: User) {
    if (u.id === me?.id) {
      alert('Kendi hesabınızı pasifleştiremezsiniz.');
      return;
    }
    if (u.is_active) {
      if (!confirm(`${u.full_name} pasifleştirilecek (giriş yapamayacak). Onaylıyor musunuz?`))
        return;
      await api.delete(`/users/${u.id}`);
    } else {
      await api.patch(`/users/${u.id}`, { is_active: true });
    }
    reload();
  }

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
              <th className="px-4 py-2">İşlem</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {users.map((u) => (
              <tr key={u.id} className={u.is_active ? '' : 'opacity-60'}>
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
                <td className="px-4 py-2">
                  <span
                    className={`pill ${
                      u.is_active
                        ? 'bg-green-100 text-green-800'
                        : 'bg-gray-100 text-gray-700'
                    }`}
                  >
                    {u.is_active ? 'Aktif' : 'Pasif'}
                  </span>
                </td>
                <td className="px-4 py-2 whitespace-nowrap space-x-2">
                  <button
                    className="text-xs text-gray-700 hover:text-brand-700"
                    onClick={() => setEditing(u)}
                  >
                    Düzenle
                  </button>
                  <button
                    className={`text-xs ${
                      u.is_active ? 'text-red-600' : 'text-green-700'
                    } hover:underline`}
                    onClick={() => toggleActive(u)}
                    disabled={u.id === me?.id}
                    title={u.id === me?.id ? 'Kendi hesabınız' : ''}
                  >
                    {u.is_active ? 'Pasifleştir' : 'Aktifleştir'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing && (
        <UserEditModal
          user={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
        />
      )}
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

function UserEditModal({
  user,
  onClose,
  onSaved,
}: {
  user: User;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(user.full_name);
  const [role, setRole] = useState<Role>(user.role);
  const [pw, setPw] = useState('');
  const [active, setActive] = useState(user.is_active);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setSaving(true);
    try {
      const payload: any = { full_name: name, role, is_active: active };
      if (pw) {
        if (pw.length < 8) {
          setErr('Parola en az 8 karakter olmalı.');
          setSaving(false);
          return;
        }
        payload.password = pw;
      }
      await api.patch(`/users/${user.id}`, payload);
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
        className="bg-white rounded-lg shadow-xl w-full max-w-md p-5 space-y-3"
      >
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">Kullanıcıyı Düzenle</h2>
          <button type="button" className="text-gray-500" onClick={onClose}>
            ✕
          </button>
        </div>

        <div>
          <label className="label">E-posta</label>
          <input className="input bg-gray-50" value={user.email} disabled />
          <p className="text-xs text-gray-500 mt-1">E-posta değiştirilemez.</p>
        </div>
        <div>
          <label className="label">Ad Soyad</label>
          <input
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="label">Rol</label>
          <select
            className="input"
            value={role}
            onChange={(e) => setRole(e.target.value as Role)}
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {ROLE_LABEL[r]}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Yeni Parola (boş bırakırsanız değişmez)</label>
          <input
            className="input"
            type="password"
            value={pw}
            onChange={(e) => setPw(e.target.value)}
            placeholder="en az 8 karakter"
          />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={active}
            onChange={(e) => setActive(e.target.checked)}
          />
          Aktif
        </label>

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

function MailingTab({ lists, reload }: { lists: MailingList[]; reload: () => void }) {
  const [name, setName] = useState('');
  const [recipients, setRecipients] = useState('');
  const [ccRecipients, setCcRecipients] = useState('');
  const [isDefault, setIsDefault] = useState(false);
  const [editing, setEditing] = useState<MailingList | null>(null);

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
              <th className="px-4 py-2">Vardiya</th>
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
                <td className="px-4 py-2 text-gray-600">
                  {l.shift_type ? SHIFT_TYPE_LABEL[l.shift_type] : '—'}
                </td>
                <td className="px-4 py-2">{l.is_default ? '✓' : ''}</td>
                <td className="px-4 py-2 text-right whitespace-nowrap space-x-2">
                  <button
                    className="text-xs text-gray-700 hover:text-brand-700"
                    onClick={() => setEditing(l)}
                  >
                    Düzenle
                  </button>
                  <button
                    className="text-xs text-red-600 hover:underline"
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

      {editing && (
        <MailingEditModal
          list={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
        />
      )}
    </div>
  );
}

const SHIFT_TYPES: ShiftType[] = ['a', 'b', 'c'];

function MailingEditModal({
  list,
  onClose,
  onSaved,
}: {
  list: MailingList;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(list.name);
  const [recipients, setRecipients] = useState(list.recipients);
  const [ccRecipients, setCcRecipients] = useState(list.cc_recipients || '');
  const [shiftType, setShiftType] = useState<ShiftType | ''>(list.shift_type || '');
  const [isDefault, setIsDefault] = useState(list.is_default);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setSaving(true);
    try {
      await api.patch(`/mailing-lists/${list.id}`, {
        name,
        recipients,
        cc_recipients: ccRecipients || null,
        is_default: isDefault,
        shift_type: shiftType || null,
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
          <h2 className="font-semibold text-gray-900">Mail Listesini Düzenle</h2>
          <button type="button" className="text-gray-500" onClick={onClose}>
            ✕
          </button>
        </div>

        <div>
          <label className="label">İsim</label>
          <input
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="label">TO Alıcıları (virgülle)</label>
          <input
            className="input"
            value={recipients}
            onChange={(e) => setRecipients(e.target.value)}
            required
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
        <div>
          <label className="label">Vardiya (opsiyonel — A/B/C, sadece bu vardiya için)</label>
          <select
            className="input"
            value={shiftType}
            onChange={(e) => setShiftType(e.target.value as ShiftType | '')}
          >
            <option value="">— Tüm vardiyalar —</option>
            {SHIFT_TYPES.map((t) => (
              <option key={t} value={t}>
                {SHIFT_TYPE_LABEL[t]}
              </option>
            ))}
          </select>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={isDefault}
            onChange={(e) => setIsDefault(e.target.checked)}
          />
          Varsayılan liste (eski varsayılan otomatik kaldırılır)
        </label>

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
