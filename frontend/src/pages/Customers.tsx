// Müşteri İrtibat Listesi (v0.6.1)
//
// "Arayanlar" giriş türünde operatörün seçeceği kurum + kişi + numara
// kayıtlarını yönetir. Her kurum birden fazla kişi içerebilir.
//
// Akış:
//  - Kurumlar kart şeklinde listelenir, her kart altında irtibatlar.
//  - Tek tıkla yeni kurum, tek tıkla yeni kişi.
//  - Inline düzenle / sil (kişi: operator+, kurum silme: admin).
//  - Filtreleme için arama kutusu (kurum + kişi adı + numara üzerinde).
import { FormEvent, useEffect, useMemo, useState } from 'react';
import { api, CustomerOrg } from '../api/client';
import { useAuth } from '../auth/AuthContext';

export default function Customers() {
  const { user } = useAuth();
  // v0.6.2: Standart ve Super Admin'in tüm CRUD yetkisi var (kullanıcının
  // istediği "tüm sistem üzerinde tam yetki" semantiği). Geriye dönük
  // uyum için eski isim korundu.
  const isAdmin = user?.role === 'standard' || user?.role === 'super_admin';

  const [orgs, setOrgs] = useState<CustomerOrg[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [editingContact, setEditingContact] = useState<{
    orgId: number;
    contactId: number;
    name: string;
    phone: string;
  } | null>(null);
  const [newOrgOpen, setNewOrgOpen] = useState(false);

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const r = await api.get<CustomerOrg[]>('/customers/orgs');
      setOrgs(r.data);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Liste yüklenemedi');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return orgs;
    return orgs
      .map((o) => {
        if (o.name.toLowerCase().includes(q)) return o;
        const matchingContacts = o.contacts.filter(
          (c) =>
            c.name.toLowerCase().includes(q) ||
            (c.phone || '').toLowerCase().includes(q),
        );
        if (matchingContacts.length === 0) return null;
        return { ...o, contacts: matchingContacts };
      })
      .filter(Boolean) as CustomerOrg[];
  }, [orgs, search]);

  async function deleteOrg(id: number, name: string) {
    if (
      !confirm(
        `"${name}" kurumunu ve tüm irtibatlarını silmek istediğinizden emin misiniz? Tarihsel kayıtlardaki kurum adları (snapshot) etkilenmez.`,
      )
    )
      return;
    try {
      await api.delete(`/customers/orgs/${id}`);
      load();
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Silme başarısız');
    }
  }

  async function deleteContact(id: number, name: string) {
    if (!confirm(`"${name}" irtibatını silmek istediğinizden emin misiniz?`)) return;
    try {
      await api.delete(`/customers/contacts/${id}`);
      load();
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Silme başarısız');
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-slate-100">
            Müşteri İrtibat Listesi
          </h1>
          <p className="text-sm text-gray-500 dark:text-slate-400">
            "Arayanlar" girişi yapılırken bu listeden kurum + kişi seçilir. Yeni
            kurum/kişi girişi sırasında listeye otomatik eklenir; buradan da
            elle düzenlenebilir.
          </p>
        </div>
        <button className="btn-primary" onClick={() => setNewOrgOpen(true)}>
          + Yeni Kurum
        </button>
      </div>

      <div className="card">
        <input
          type="search"
          className="input max-w-md"
          placeholder="Kurum / kişi / numara ara…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {err && <div className="text-sm text-red-600 dark:text-red-400">{err}</div>}

      {loading ? (
        <div className="text-sm text-gray-500 dark:text-slate-400">Yükleniyor…</div>
      ) : filtered.length === 0 ? (
        <div className="card text-sm text-gray-500 dark:text-slate-400">
          {search ? 'Arama sonucu bulunamadı.' : 'Henüz kurum eklenmedi.'}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filtered.map((o) => (
            <div key={o.id} className="card space-y-2">
              <div className="flex items-start justify-between gap-2">
                <h2 className="font-semibold text-gray-900 dark:text-slate-100">
                  {o.name}
                </h2>
                <div className="flex gap-2 text-xs">
                  {isAdmin && (
                    <button
                      className="text-red-600 hover:underline"
                      onClick={() => deleteOrg(o.id, o.name)}
                    >
                      Kurumu Sil
                    </button>
                  )}
                </div>
              </div>
              {o.notes && (
                <p className="text-xs text-gray-500 dark:text-slate-400">{o.notes}</p>
              )}
              <ul className="divide-y divide-gray-100 dark:divide-slate-700">
                {o.contacts.length === 0 ? (
                  <li className="text-xs text-gray-400 dark:text-slate-500 py-2">
                    Henüz irtibat eklenmedi.
                  </li>
                ) : (
                  o.contacts.map((c) => (
                    <li key={c.id} className="py-2 flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-gray-800 dark:text-slate-100">
                          {c.name}
                        </div>
                        {c.phone && (
                          <div className="text-xs text-gray-500 dark:text-slate-400">
                            {c.phone}
                          </div>
                        )}
                      </div>
                      <div className="flex gap-2 text-xs">
                        <button
                          className="text-brand-700 hover:underline dark:text-brand-400"
                          onClick={() =>
                            setEditingContact({
                              orgId: o.id,
                              contactId: c.id,
                              name: c.name,
                              phone: c.phone || '',
                            })
                          }
                        >
                          Düzenle
                        </button>
                        <button
                          className="text-red-600 hover:underline"
                          onClick={() => deleteContact(c.id, c.name)}
                        >
                          Sil
                        </button>
                      </div>
                    </li>
                  ))
                )}
              </ul>
              <NewContactForm orgId={o.id} onSaved={load} />
            </div>
          ))}
        </div>
      )}

      {newOrgOpen && (
        <NewOrgModal onClose={() => setNewOrgOpen(false)} onSaved={() => { setNewOrgOpen(false); load(); }} />
      )}

      {editingContact && (
        <EditContactModal
          contact={editingContact}
          onClose={() => setEditingContact(null)}
          onSaved={() => { setEditingContact(null); load(); }}
        />
      )}
    </div>
  );
}

function NewContactForm({ orgId, onSaved }: { orgId: number; onSaved: () => void }) {
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [saving, setSaving] = useState(false);

  async function add(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    try {
      await api.post(`/customers/orgs/${orgId}/contacts`, {
        name: name.trim(),
        phone: phone.trim() || null,
      });
      setName('');
      setPhone('');
      onSaved();
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Ekleme başarısız');
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={add} className="flex gap-2 pt-2 border-t border-gray-100 dark:border-slate-700 mt-2">
      <input
        className="input flex-1 text-sm"
        placeholder="Yeni kişi adı"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <input
        className="input w-40 text-sm"
        placeholder="Telefon"
        value={phone}
        onChange={(e) => setPhone(e.target.value)}
      />
      <button type="submit" className="btn-primary text-sm" disabled={saving || !name.trim()}>
        Ekle
      </button>
    </form>
  );
}

function NewOrgModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState('');
  const [notes, setNotes] = useState('');
  const [contactName, setContactName] = useState('');
  const [contactPhone, setContactPhone] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    if (!name.trim()) {
      setErr('Kurum adı zorunlu.');
      return;
    }
    setSaving(true);
    try {
      const payload: any = {
        name: name.trim(),
        notes: notes.trim() || null,
      };
      if (contactName.trim()) {
        payload.initial_contact = {
          name: contactName.trim(),
          phone: contactPhone.trim() || null,
        };
      }
      await api.post('/customers/orgs', payload);
      onSaved();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Kayıt başarısız');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <form
        onSubmit={submit}
        className="bg-white dark:bg-slate-800 rounded-lg shadow-xl w-full max-w-md p-5 space-y-3"
      >
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-gray-900 dark:text-slate-100">
            Yeni Kurum
          </h2>
          <button type="button" className="text-gray-500 dark:text-slate-400" onClick={onClose}>✕</button>
        </div>
        <div>
          <label className="label">Kurum Adı *</label>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
        <div>
          <label className="label">Notlar (opsiyonel)</label>
          <textarea className="input min-h-[60px]" value={notes} onChange={(e) => setNotes(e.target.value)} />
        </div>
        <div className="border-t border-gray-200 dark:border-slate-700 pt-3 space-y-2">
          <div className="text-sm font-medium text-gray-700 dark:text-slate-200">İlk İrtibat (opsiyonel)</div>
          <input
            className="input"
            placeholder="Kişi adı"
            value={contactName}
            onChange={(e) => setContactName(e.target.value)}
          />
          <input
            className="input"
            placeholder="Telefon"
            value={contactPhone}
            onChange={(e) => setContactPhone(e.target.value)}
          />
        </div>
        {err && <div className="text-sm text-red-600 dark:text-red-400">{err}</div>}
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

function EditContactModal({
  contact, onClose, onSaved,
}: {
  contact: { orgId: number; contactId: number; name: string; phone: string };
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(contact.name);
  const [phone, setPhone] = useState(contact.phone);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setSaving(true);
    try {
      await api.patch(`/customers/contacts/${contact.contactId}`, {
        name: name.trim(),
        phone: phone.trim() || null,
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
        className="bg-white dark:bg-slate-800 rounded-lg shadow-xl w-full max-w-md p-5 space-y-3"
      >
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-gray-900 dark:text-slate-100">
            İrtibatı Düzenle
          </h2>
          <button type="button" className="text-gray-500 dark:text-slate-400" onClick={onClose}>✕</button>
        </div>
        <div>
          <label className="label">Adı *</label>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
        <div>
          <label className="label">Telefon</label>
          <input className="input" value={phone} onChange={(e) => setPhone(e.target.value)} />
        </div>
        {err && <div className="text-sm text-red-600 dark:text-red-400">{err}</div>}
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
