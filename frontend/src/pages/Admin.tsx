import { FormEvent, useEffect, useState } from 'react';
import {
  api, extractApiError, MplsTeam, ROLE_LABEL, Role, ShiftType, SHIFT_TYPE_LABEL, User,
} from '../api/client';
import { useAuth } from '../auth/AuthContext';

// v0.6.2: 2 rollü sistem. super_admin opsiyonu sadece super_admin
// kullanıcılara gösterilir; standart kullanıcı super_admin oluşturamaz.
const ALL_ROLES: Role[] = ['standard', 'super_admin'];
const STANDARD_ONLY_ROLES: Role[] = ['standard'];

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
  const [mplsTeams, setMplsTeams] = useState<MplsTeam[]>([]);
  const [tab, setTab] = useState<'users' | 'mailing' | 'mpls'>('users');
  // v0.9.14: load hatası olursa sayfa beyaz kalmasın
  const [loadError, setLoadError] = useState<string | null>(null);

  async function load() {
    // v0.9.14: bir API başarısız olsa bile diğerleri denensin ve UI'da
    // hata göster. Promise.all reject olursa React crash oluyordu (beyaz sayfa).
    setLoadError(null);
    const results = await Promise.allSettled([
      api.get('/users'),
      api.get('/mailing-lists'),
      api.get('/mpls-teams', { params: { only_active: false } }),
    ]);
    const errs: string[] = [];
    if (results[0].status === 'fulfilled') {
      setUsers(Array.isArray(results[0].value.data) ? results[0].value.data : []);
    } else {
      errs.push('Kullanıcı listesi yüklenemedi');
    }
    if (results[1].status === 'fulfilled') {
      setLists(Array.isArray(results[1].value.data) ? results[1].value.data : []);
    } else {
      errs.push('Mail listeleri yüklenemedi');
    }
    if (results[2].status === 'fulfilled') {
      setMplsTeams(Array.isArray(results[2].value.data) ? results[2].value.data : []);
    } else {
      errs.push('MPLS ekipleri yüklenemedi');
    }
    if (errs.length) setLoadError(errs.join(' · '));
  }
  useEffect(() => {
    load();
  }, []);

  const TAB_LABEL: Record<'users' | 'mailing' | 'mpls', string> = {
    users: 'Kullanıcılar',
    mailing: 'Mail Listeleri',
    mpls: 'MPLS Ekipleri',
  };

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Yönetim</h1>
      {loadError && (
        <div className="card border-l-4 border-red-400 text-sm text-red-700 dark:text-red-300">
          <b>Yükleme uyarısı:</b> {loadError}
        </div>
      )}
      <div className="flex gap-2 border-b border-gray-200">
        {(['users', 'mailing', 'mpls'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-2 text-sm font-medium ${
              tab === t ? 'text-brand-700 border-b-2 border-brand-700' : 'text-gray-500'
            }`}
          >
            {TAB_LABEL[t]}
          </button>
        ))}
      </div>
      {tab === 'users' ? (
        <UsersTab users={users} reload={load} />
      ) : tab === 'mailing' ? (
        <MailingTab lists={lists} reload={load} />
      ) : (
        <MplsTab teams={mplsTeams} reload={load} />
      )}
    </div>
  );
}


function MplsTab({ teams, reload }: { teams: MplsTeam[]; reload: () => void }) {
  const { user: me } = useAuth();
  const canDelete = me?.role === 'super_admin';
  const [showNew, setShowNew] = useState(false);
  const [editing, setEditing] = useState<MplsTeam | null>(null);

  async function remove(t: MplsTeam) {
    if (!confirm(
      `"${t.name}" MPLS ekibi silinecek. Bu ekibi referans veren DDoS Taşıma ` +
      `girişleri varsa ekip pasifleştirilir (soft-delete). Onaylıyor musunuz?`,
    )) return;
    try {
      await api.delete(`/mpls-teams/${t.id}`);
      reload();
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Silme başarısız');
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex justify-between items-start">
        <p className="text-sm text-gray-500 dark:text-slate-400 max-w-2xl">
          DDoS Taşıma girişlerinde "Otomatik hatırlatma" seçildiğinde, taşıma
          zamanına 30 dk kala bu listeden seçilen MPLS ekibinin mail adresine
          hatırlatma gönderilir. Mail konusu: giriş içeriği (devre no / müşteri
          adı). İçerik: "İlgili taşıma işlemi için hatırlatma mailidir."
        </p>
        <button className="btn-primary shrink-0" onClick={() => setShowNew(true)}>
          + Yeni MPLS Ekibi
        </button>
      </div>
      {showNew && (
        <NewMplsTeamForm onDone={() => { setShowNew(false); reload(); }} />
      )}
      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-2">#</th>
              <th className="px-4 py-2">Ad</th>
              <th className="px-4 py-2">E-posta</th>
              <th className="px-4 py-2">Not</th>
              <th className="px-4 py-2">Durum</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {teams.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-gray-500">
                  Henüz MPLS ekibi eklenmedi.
                </td>
              </tr>
            ) : teams.map((t) => (
              <tr key={t.id} className={t.is_active ? '' : 'opacity-60'}>
                <td className="px-4 py-2 text-gray-500">#{t.id}</td>
                <td className="px-4 py-2 font-medium">{t.name}</td>
                <td className="px-4 py-2 text-gray-700">{t.email}</td>
                <td className="px-4 py-2 text-gray-500 text-xs">{t.notes || '—'}</td>
                <td className="px-4 py-2">
                  <span className={`pill ${t.is_active
                    ? 'bg-green-100 text-green-800'
                    : 'bg-gray-200 text-gray-700'}`}>
                    {t.is_active ? 'Aktif' : 'Pasif'}
                  </span>
                </td>
                <td className="px-4 py-2 text-right whitespace-nowrap space-x-2">
                  <button
                    className="text-xs text-brand-700 hover:underline"
                    onClick={() => setEditing(t)}
                  >
                    Düzenle
                  </button>
                  {canDelete && (
                    <button
                      className="text-xs text-red-600 hover:underline"
                      onClick={() => remove(t)}
                    >
                      Sil
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editing && (
        <MplsTeamEditModal
          team={editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); reload(); }}
        />
      )}
    </div>
  );
}


function NewMplsTeamForm({ onDone }: { onDone: () => void }) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setSaving(true);
    try {
      await api.post('/mpls-teams', {
        name: name.trim(),
        email: email.trim(),
        notes: notes.trim() || null,
        is_active: true,
      });
      onDone();
    } catch (e: any) {
      setErr(extractApiError(e, 'Ekleme başarısız'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="card grid grid-cols-1 md:grid-cols-3 gap-3">
      <input
        className="input"
        placeholder="MPLS Ekip Adı (örn. MPLS-1)"
        value={name}
        onChange={(e) => setName(e.target.value)}
        required
      />
      <input
        className="input"
        placeholder="E-posta"
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        required
      />
      <input
        className="input"
        placeholder="Not (opsiyonel)"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />
      {err && <div className="col-span-3 text-sm text-red-600">{err}</div>}
      <div className="col-span-3 flex justify-end gap-2">
        <button type="button" className="btn-ghost" onClick={onDone}>İptal</button>
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? 'Ekleniyor…' : 'Ekle'}
        </button>
      </div>
    </form>
  );
}


function MplsTeamEditModal({
  team, onClose, onSaved,
}: {
  team: MplsTeam;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(team.name);
  const [email, setEmail] = useState(team.email);
  const [notes, setNotes] = useState(team.notes || '');
  const [active, setActive] = useState(team.is_active);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setSaving(true);
    try {
      await api.patch(`/mpls-teams/${team.id}`, {
        name: name.trim(),
        email: email.trim(),
        notes: notes.trim() || null,
        is_active: active,
      });
      onSaved();
    } catch (e: any) {
      setErr(extractApiError(e, 'Güncelleme başarısız'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <form onSubmit={submit} className="bg-white dark:bg-slate-800 rounded-lg shadow-xl w-full max-w-md p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-gray-900 dark:text-slate-100">
            MPLS Ekibini Düzenle
          </h2>
          <button type="button" className="text-gray-500" onClick={onClose}>✕</button>
        </div>
        <div>
          <label className="label">Ad</label>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
        <div>
          <label className="label">E-posta</label>
          <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </div>
        <div>
          <label className="label">Not (opsiyonel)</label>
          <input className="input" value={notes} onChange={(e) => setNotes(e.target.value)} />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
          Aktif
        </label>
        {err && <div className="text-sm text-red-600">{err}</div>}
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" className="btn-ghost" onClick={onClose}>İptal</button>
          <button type="submit" className="btn-primary" disabled={saving}>
            {saving ? 'Kaydediliyor…' : 'Kaydet'}
          </button>
        </div>
      </form>
    </div>
  );
}

function UsersTab({ users, reload }: { users: User[]; reload: () => void }) {
  const { user: me } = useAuth();
  const isSuper = me?.role === 'super_admin';
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
      try {
        await api.delete(`/users/${u.id}`);
      } catch (err: any) {
        alert(err?.response?.data?.detail || 'Pasifleştirme başarısız');
      }
    } else {
      try {
        await api.patch(`/users/${u.id}`, { is_active: true });
      } catch (err: any) {
        alert(err?.response?.data?.detail || 'Aktifleştirme başarısız');
      }
    }
    reload();
  }

  // v0.9.11: HARD-DELETE (kalıcı silme) — sadece Super Admin.
  async function hardDelete(u: User) {
    if (u.id === me?.id) {
      alert('Kendi hesabınızı silemezsiniz.');
      return;
    }
    if (!confirm(
      `${u.full_name} (${u.email}) KALICI OLARAK silinecek.\n\n` +
      `Bu işlem GERİ ALINAMAZ. Kullanıcının vardiya girişleri / olay ` +
      `kayıtları varsa silme başarısız olur; o durumda 'Pasifleştir' ` +
      `seçeneğini kullanın.\n\nDevam etmek istediğinize emin misiniz?`
    )) return;
    try {
      await api.delete(`/users/${u.id}/hard`);
      reload();
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Silme başarısız');
    }
  }

  return (
    <div className="space-y-3">
      {isSuper && (
        <div className="flex justify-end">
          <button className="btn-primary" onClick={() => setShowNew(true)}>
            + Yeni Kullanıcı
          </button>
        </div>
      )}
      {showNew && isSuper && (
        <NewUserForm onDone={() => { setShowNew(false); reload(); }} />
      )}
      {!isSuper && (
        <div className="card text-sm text-gray-600 dark:text-slate-300">
          Standart kullanıcı olarak yalnızca kendi profilinizi
          görüntüleyebilir ve parolanızı değiştirebilirsiniz.
        </div>
      )}
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
            {users.map((u) => {
              const isSelf = u.id === me?.id;
              // v0.9.11: Standart user rol/aktiflik değiştiremez; sadece kendi
              // parolasını "Düzenle" ile değiştirebilir.
              const canChangeRole = isSuper;
              const canToggle = isSuper;
              const canEdit = isSuper || isSelf;
              const canDelete = isSuper && !isSelf;
              return (
              <tr key={u.id} className={u.is_active ? '' : 'opacity-60'}>
                <td className="px-4 py-2 text-gray-500">#{u.id}</td>
                <td className="px-4 py-2">{u.email}</td>
                <td className="px-4 py-2">{u.full_name}</td>
                <td className="px-4 py-2">
                  {canChangeRole ? (
                    <select
                      className="input py-1 text-xs"
                      value={u.role}
                      onChange={async (e) => {
                        try {
                          await api.patch(`/users/${u.id}`, { role: e.target.value });
                          reload();
                        } catch (err: any) {
                          alert(err?.response?.data?.detail || 'Rol değiştirilemedi');
                          reload();
                        }
                      }}
                    >
                      {ALL_ROLES.map((r) => (
                        <option key={r} value={r}>
                          {ROLE_LABEL[r]}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span className="text-xs">{ROLE_LABEL[u.role]}</span>
                  )}
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
                  {canEdit && (
                    <button
                      className="text-xs text-gray-700 hover:text-brand-700"
                      onClick={() => setEditing(u)}
                    >
                      Düzenle
                    </button>
                  )}
                  {canToggle && (
                    <button
                      className={`text-xs ${
                        u.is_active ? 'text-orange-600' : 'text-green-700'
                      } hover:underline`}
                      onClick={() => toggleActive(u)}
                      disabled={isSelf}
                      title={isSelf ? 'Kendi hesabınız' : ''}
                    >
                      {u.is_active ? 'Pasifleştir' : 'Aktifleştir'}
                    </button>
                  )}
                  {canDelete && (
                    <button
                      className="text-xs text-red-600 hover:underline font-medium"
                      onClick={() => hardDelete(u)}
                      title="Kullanıcıyı KALICI olarak sil (geri alınamaz)"
                    >
                      Sil
                    </button>
                  )}
                </td>
              </tr>
              );
            })}
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
  const { user: me } = useAuth();
  const availableRoles = me?.role === 'super_admin' ? ALL_ROLES : STANDARD_ONLY_ROLES;
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [pw, setPw] = useState('');
  const [role, setRole] = useState<Role>('standard');
  // v0.9.13: standard user için oluşturulacak Personnel kaydının lokasyonu
  const [personnelLocation, setPersonnelLocation] = useState<'istanbul' | 'ankara'>('istanbul');
  const [error, setError] = useState<string | null>(null);
  // v0.9.14: double-submit önleme — beyaz sayfa bug'ının kökeni buydu
  const [saving, setSaving] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (saving) return;  // v0.9.14: aynı anda iki istek atma
    setError(null);
    setSaving(true);
    try {
      const payload: any = {
        email,
        full_name: name,
        password: pw,
        role,
      };
      // Sadece standard rolde Personnel oluşturulacağı için lokasyonu o
      // durumda gönderiyoruz (super_admin'de backend zaten göz ardı eder).
      if (role === 'standard') {
        payload.personnel_location = personnelLocation;
      }
      await api.post('/users', payload);
      onDone();
    } catch (err: any) {
      setError(extractApiError(err, 'Kullanıcı oluşturulamadı'));
    } finally {
      setSaving(false);
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
        placeholder="ad soyad (ör: Doğukan Karadağ)"
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
        {availableRoles.map((r) => (
          <option key={r} value={r}>
            {ROLE_LABEL[r]}
          </option>
        ))}
      </select>
      {role === 'standard' && (
        <div className="col-span-2">
          <label className="label text-xs">
            Lokasyon (Aylık Vardiya + Dağıtıcı Listesi için)
          </label>
          <select
            className="input"
            value={personnelLocation}
            onChange={(e) => setPersonnelLocation(e.target.value as 'istanbul' | 'ankara')}
          >
            <option value="istanbul">İstanbul</option>
            <option value="ankara">Ankara</option>
          </select>
          <p className="text-xs text-gray-500 mt-1">
            Kullanıcının adının ilk kelimesi Personel olarak eklenir (ör.
            "Doğukan Karadağ" → "Doğukan"). Sonradan Personel Yönet'ten
            değiştirilebilir.
          </p>
        </div>
      )}
      {error && <div className="col-span-2 text-sm text-red-600">{error}</div>}
      <div className="col-span-2 flex justify-end gap-2">
        <button type="button" className="btn-ghost" onClick={onDone} disabled={saving}>
          İptal
        </button>
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? 'Oluşturuluyor…' : 'Oluştur'}
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
  const { user: me } = useAuth();
  // v0.9.11: Standard user yalnızca kendi parolasını değiştirebilir.
  // Super Admin herkesi tüm alanlarda düzenler.
  const isSuper = me?.role === 'super_admin';
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
      const payload: any = {};
      if (isSuper) {
        payload.full_name = name;
        payload.role = role;
        payload.is_active = active;
      }
      if (pw) {
        if (pw.length < 8) {
          setErr('Parola en az 8 karakter olmalı.');
          setSaving(false);
          return;
        }
        payload.password = pw;
      }
      if (Object.keys(payload).length === 0) {
        setErr('Değiştirilecek bir şey seçmediniz.');
        setSaving(false);
        return;
      }
      await api.patch(`/users/${user.id}`, payload);
      onSaved();
    } catch (e: any) {
      setErr(extractApiError(e, 'Güncelleme başarısız'));
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
          <h2 className="font-semibold text-gray-900">
            {isSuper ? 'Kullanıcıyı Düzenle' : 'Parolamı Değiştir'}
          </h2>
          <button type="button" className="text-gray-500" onClick={onClose}>
            ✕
          </button>
        </div>

        <div>
          <label className="label">E-posta</label>
          <input className="input bg-gray-50" value={user.email} disabled />
          <p className="text-xs text-gray-500 mt-1">E-posta değiştirilemez.</p>
        </div>
        {isSuper && (
          <>
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
                {ALL_ROLES.map((r) => (
                  <option key={r} value={r}>
                    {ROLE_LABEL[r]}
                  </option>
                ))}
              </select>
            </div>
          </>
        )}
        {!isSuper && (
          <>
            <div>
              <label className="label">Ad Soyad</label>
              <input className="input bg-gray-50" value={user.full_name} disabled />
              <p className="text-xs text-gray-500 mt-1">
                Ad Soyad değişikliği için Super Admin ile iletişime geçin.
              </p>
            </div>
            <div>
              <label className="label">Rol</label>
              <input
                className="input bg-gray-50"
                value={ROLE_LABEL[user.role]}
                disabled
              />
            </div>
          </>
        )}
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
        {isSuper && (
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={active}
              onChange={(e) => setActive(e.target.checked)}
            />
            Aktif
          </label>
        )}

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
      setErr(extractApiError(e, 'Güncelleme başarısız'));
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
