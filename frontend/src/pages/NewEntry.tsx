import { FormEvent, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  api,
  CustomerOrg,
  ENTRY_TYPE_LABEL,
  EntryType,
  MplsTeam,
  NUMERIC_ENTRY_TYPES,
} from '../api/client';

const TYPES: EntryType[] = [
  'ddos_transfer',
  'info',
  'important_work',
  'l2_escalation',
  'callers',
  'dhs',
  'iys',
];

// "YYYY-MM-DDTHH:mm" (yerel, GMT+3) girişini UTC ISO string'e çevir.
function localInputToUtcIso(v: string): string | null {
  if (!v) return null;
  const iso = v.length === 16 ? `${v}:00+03:00` : `${v}+03:00`;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  return d.toISOString();
}

export default function NewEntry() {
  const nav = useNavigate();
  const [entryType, setEntryType] = useState<EntryType>('ddos_transfer');
  const [body, setBody] = useState('');
  const [numericValue, setNumericValue] = useState<string>('');
  const [occursAt, setOccursAt] = useState<string>(''); // "YYYY-MM-DDTHH:mm" yerel
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // "Arayanlar" alanları (v0.6.1)
  const [callerOrg, setCallerOrg] = useState('');
  const [callerContact, setCallerContact] = useState('');
  const [callerPhone, setCallerPhone] = useState('');
  const [orgs, setOrgs] = useState<CustomerOrg[]>([]);

  // "DDoS Taşıma" MPLS ekibi + otomatik hatırlatma (v0.8.14)
  const [mplsReminder, setMplsReminder] = useState(false);
  const [mplsTeamId, setMplsTeamId] = useState<number | ''>('');
  const [mplsTeams, setMplsTeams] = useState<MplsTeam[]>([]);

  const isNumeric = NUMERIC_ENTRY_TYPES.includes(entryType);
  const isCallers = entryType === 'callers';
  // "Planlanan zaman" alanı yalnızca DDoS Taşıma için açık.
  const allowsOccursAt = entryType === 'ddos_transfer';

  // Müşteri İrtibat Listesi'ni autocomplete için yükle.
  useEffect(() => {
    api.get<CustomerOrg[]>('/customers/orgs')
      .then((r) => setOrgs(r.data))
      .catch(() => {/* sessizce yut — autocomplete olmaması formu bozmamalı */});
  }, []);

  // v0.8.14: MPLS ekipleri dropdown için
  useEffect(() => {
    api.get<MplsTeam[]>('/mpls-teams', { params: { only_active: true } })
      .then((r) => setMplsTeams(r.data))
      .catch(() => {/* sessizce yut */});
  }, []);

  // Seçili (veya tip eşleşen) kurumun irtibatları — kişi datalist için.
  const matchedOrg = useMemo(() => {
    const trimmed = callerOrg.trim().toLowerCase();
    if (!trimmed) return null;
    return orgs.find((o) => o.name.toLowerCase() === trimmed) || null;
  }, [callerOrg, orgs]);

  // Kullanıcı kişi adını yazınca, kuruma ait kayıtlı kişiyse telefonu otomatik doldur.
  useEffect(() => {
    if (!matchedOrg || !callerContact.trim()) return;
    const c = matchedOrg.contacts.find(
      (x) => x.name.toLowerCase() === callerContact.trim().toLowerCase(),
    );
    if (c && c.phone && !callerPhone) {
      setCallerPhone(c.phone);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matchedOrg, callerContact]);

  /**
   * Çağrı girişi başarıyla kaydedildikten sonra: girilen kurum/kişi
   * kayıtlı değilse Müşteri İrtibat Listesi'ne ekle (autocomplete büyür).
   */
  async function persistContactIfNew() {
    const orgName = callerOrg.trim();
    const contactName = callerContact.trim();
    const phone = callerPhone.trim() || null;
    if (!orgName || !contactName) return;

    try {
      let org = matchedOrg;
      if (!org) {
        const r = await api.post<CustomerOrg>('/customers/orgs', {
          name: orgName,
          initial_contact: { name: contactName, phone },
        });
        org = r.data;
      } else {
        const existing = org.contacts.find(
          (x) => x.name.toLowerCase() === contactName.toLowerCase(),
        );
        if (!existing) {
          await api.post(`/customers/orgs/${org.id}/contacts`, {
            name: contactName,
            phone,
          });
        }
      }
    } catch {
      /* Autocomplete kaydı best-effort; hata olsa bile giriş zaten kaydedildi */
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (isNumeric) {
      const n = Number(numericValue);
      if (!Number.isFinite(n) || n < 0 || !Number.isInteger(n)) {
        setError('Lütfen geçerli bir adet (tam sayı) girin.');
        return;
      }
    } else if (isCallers) {
      if (!callerOrg.trim()) {
        setError('Kurum ismini girin.');
        return;
      }
      if (!callerContact.trim()) {
        setError('İrtibat kişisinin adını girin.');
        return;
      }
    } else if (!body.trim()) {
      setError('Lütfen detay alanını doldurun.');
      return;
    }

    setSubmitting(true);
    try {
      await api.post('/entries', {
        entry_type: entryType,
        title: null,
        body: isNumeric ? '' : body.trim(),
        numeric_value: isNumeric ? Number(numericValue) : null,
        occurs_at: allowsOccursAt ? localInputToUtcIso(occursAt) : null,
        caller_org_name: isCallers ? callerOrg.trim() : null,
        caller_contact_name: isCallers ? callerContact.trim() : null,
        caller_contact_phone: isCallers ? (callerPhone.trim() || null) : null,
        // v0.8.14: DDoS Taşıma MPLS ekibi + otomatik hatırlatma
        mpls_team_id: allowsOccursAt && mplsReminder && mplsTeamId
          ? Number(mplsTeamId) : null,
        mpls_reminder_enabled: allowsOccursAt && mplsReminder && !!mplsTeamId,
      });
      if (isCallers) {
        await persistContactIfNew();
      }
      nav('/');
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Kayıt başarısız oldu');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-4">
      <h1 className="text-2xl font-semibold text-gray-900 dark:text-slate-100">Yeni Vardiya Girişi</h1>
      <form onSubmit={onSubmit} className="card space-y-4">
        <div className={`grid gap-4 ${allowsOccursAt ? 'grid-cols-2' : 'grid-cols-1'}`}>
          <div>
            <label className="label">Tür</label>
            <select
              className="input"
              value={entryType}
              onChange={(e) => {
                const next = e.target.value as EntryType;
                setEntryType(next);
                if (NUMERIC_ENTRY_TYPES.includes(next)) {
                  setBody('');
                } else {
                  setNumericValue('');
                }
                if (next !== 'ddos_transfer') {
                  setOccursAt('');
                }
                if (next !== 'callers') {
                  setCallerOrg('');
                  setCallerContact('');
                  setCallerPhone('');
                }
              }}
            >
              {TYPES.map((t) => (
                <option key={t} value={t}>
                  {ENTRY_TYPE_LABEL[t]}
                </option>
              ))}
            </select>
          </div>
          {allowsOccursAt && (
            <div>
              <label className="label">Planlanan Zaman (opsiyonel)</label>
              <input
                type="datetime-local"
                className="input"
                value={occursAt}
                onChange={(e) => setOccursAt(e.target.value)}
              />
              <p className="text-xs text-gray-500 dark:text-slate-400 mt-1">
                Taşıma ileride bir tarihte gerçekleşecekse saat (GMT+3) seçin.
                Tarih gelene kadar tüm vardiya raporlarında hatırlatılır.
              </p>
            </div>
          )}
        </div>

        {/* v0.8.14: DDoS Taşıma için MPLS ekibi + otomatik hatırlatma */}
        {allowsOccursAt && (
          <div className="border-t border-gray-200 dark:border-slate-700 pt-3 space-y-2">
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={mplsReminder}
                onChange={(e) => setMplsReminder(e.target.checked)}
              />
              <span>
                <b>Otomatik olarak hatırlatma maili iletilsin</b>
                <span className="text-xs text-gray-500 dark:text-slate-400 block">
                  Taşıma tarihine 30 dk kala aşağıda seçilen MPLS ekibinin
                  mail adresine hatırlatma gönderilir. Mail konusu bu formda
                  gireceğiniz devre no/müşteri adı olacaktır.
                </span>
              </span>
            </label>
            {mplsReminder && (
              <div className="ml-6">
                <label className="label">MPLS Ekibi *</label>
                <select
                  className="input"
                  value={mplsTeamId}
                  onChange={(e) =>
                    setMplsTeamId(e.target.value === '' ? '' : Number(e.target.value))
                  }
                  required
                >
                  <option value="">— Seçin —</option>
                  {mplsTeams.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} ({t.email})
                    </option>
                  ))}
                </select>
                {mplsTeams.length === 0 && (
                  <p className="text-xs text-amber-700 dark:text-amber-300 mt-1">
                    Sistemde MPLS ekibi tanımlı değil. Önce
                    <b> Yönetim → MPLS Ekipleri</b>'nden ekip ekleyin.
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {isNumeric ? (
          <div>
            <label className="label">Adet / Sayı</label>
            <input
              type="number"
              min={0}
              step={1}
              className="input"
              value={numericValue}
              onChange={(e) => setNumericValue(e.target.value)}
              required
              placeholder="örn. 11"
            />
            <p className="text-xs text-gray-500 dark:text-slate-400 mt-1">
              Bu vardiyada işlem yapılan {ENTRY_TYPE_LABEL[entryType]} case sayısını girin.
            </p>
          </div>
        ) : isCallers ? (
          // --- "Arayanlar" özel formu (v0.6.1) ---
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="label">Kurum İsmi *</label>
                <input
                  className="input"
                  list="caller-orgs"
                  value={callerOrg}
                  onChange={(e) => setCallerOrg(e.target.value)}
                  required
                  placeholder="Garanti BBVA"
                  autoComplete="off"
                />
                <datalist id="caller-orgs">
                  {orgs.map((o) => (
                    <option key={o.id} value={o.name} />
                  ))}
                </datalist>
                <p className="text-xs text-gray-500 dark:text-slate-400 mt-1">
                  Listeden seçin ya da yeni kurum adı yazın — yeni isim Müşteri
                  İrtibat Listesi'ne otomatik kaydedilir.
                </p>
              </div>
              <div>
                <label className="label">İrtibat Kişisi *</label>
                <input
                  className="input"
                  list="caller-contacts"
                  value={callerContact}
                  onChange={(e) => setCallerContact(e.target.value)}
                  required
                  placeholder="Ali Yılmaz"
                  autoComplete="off"
                />
                <datalist id="caller-contacts">
                  {(matchedOrg?.contacts || []).map((c) => (
                    <option key={c.id} value={c.name} />
                  ))}
                </datalist>
                <p className="text-xs text-gray-500 dark:text-slate-400 mt-1">
                  Kurum seçili ise kayıtlı kişiler önerilir.
                </p>
              </div>
            </div>
            <div>
              <label className="label">İrtibat Numarası</label>
              <input
                className="input"
                value={callerPhone}
                onChange={(e) => setCallerPhone(e.target.value)}
                placeholder="0532 123 45 67"
                autoComplete="off"
              />
              <p className="text-xs text-gray-500 dark:text-slate-400 mt-1">
                Kayıtlı bir kişi seçtiyseniz numara otomatik doldurulur; gerekirse düzeltin.
              </p>
            </div>
            <div>
              <label className="label">Notlar (opsiyonel)</label>
              <textarea
                className="input min-h-[80px]"
                value={body}
                onChange={(e) => setBody(e.target.value)}
                placeholder="Çağrı hakkında ek bilgi…"
              />
            </div>
          </>
        ) : (
          <div>
            <label className="label">Detay</label>
            <textarea
              className="input min-h-[160px]"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              required
              placeholder="Neler oldu, hangi aksiyonlar alındı, sonraki adımlar…"
            />
          </div>
        )}

        {error && <div className="text-sm text-red-600 dark:text-red-400">{error}</div>}
        <div className="flex gap-2 justify-end">
          <button type="button" className="btn-ghost" onClick={() => nav(-1)}>
            İptal
          </button>
          <button type="submit" disabled={submitting} className="btn-primary">
            {submitting ? 'Kaydediliyor…' : 'Kaydet'}
          </button>
        </div>
      </form>
    </div>
  );
}
