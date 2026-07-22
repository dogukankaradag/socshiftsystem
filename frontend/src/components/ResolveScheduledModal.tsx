// Karar bekleyen girişleri (DDoS Taşıma + Bilgi) tek pop-up'ta çözer.
//
// Kullanıcı yeni vardiya raporu hazırlamaya başlarken (ya da Panel'deki
// "Bekleyen kararlar" banner'ından) bu modal açılır.
//
// DDoS Taşıma (occurs_at < now olanlar) için 3 aksiyon:
//   1) completed         → giriş silinir
//   2) reschedule(date)  → occurs_at güncellenir
//   3) keep_unscheduled  → occurs_at NULL olur, açık iş olarak listede kalır
//
// Bilgi için 2 aksiyon (her vardiya raporu öncesi her Bilgi için sorulur):
//   1) keep      → "Evet, raporda kalmaya devam etsin" (state değişmez)
//   2) completed → "Hayır, silinsin"
//
// Modal kapanırken karar verilmemiş giriş kalmışsa kullanıcı "Sonra karar
// veririm" diyerek çıkabilir (banner görünmeye devam eder).
import { useEffect, useMemo, useState } from 'react';
import { api, ENTRY_TYPE_LABEL, Entry, NUMERIC_ENTRY_TYPES } from '../api/client';

type ResolveAction = 'completed' | 'reschedule' | 'keep_unscheduled' | 'keep';

function fmtLocal(iso: string): string {
  return new Date(iso).toLocaleString('tr-TR', {
    timeZone: 'Europe/Istanbul',
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// "YYYY-MM-DDTHH:mm" (yerel, Europe/Istanbul) → UTC ISO
function localInputToUtcIso(v: string): string | null {
  if (!v) return null;
  const iso = v.length === 16 ? `${v}:00+03:00` : `${v}+03:00`;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  return d.toISOString();
}

function entryDisplay(e: Entry): string {
  if (NUMERIC_ENTRY_TYPES.includes(e.entry_type) && e.numeric_value != null) {
    return `Adet: ${e.numeric_value}`;
  }
  return e.body || e.title || '(içerik yok)';
}

export interface ResolveScheduledModalProps {
  /** Modalı dış dünyadan kapatma. */
  onClose: () => void;
  /** Tüm kararlar tamamlandığında (liste boşaldığında) tetiklenir.
   *  "Rapor oluştur"a yönlendirme gibi sonraki adım için kullanılır. */
  onAllResolved?: () => void;
  /** Karar uygulandığında (her başarılı resolve sonrası) Dashboard'un
   *  yeniden yüklenmesi için tetiklenir. */
  onChange?: () => void;
}

export default function ResolveScheduledModal({
  onClose,
  onAllResolved,
  onChange,
}: ResolveScheduledModalProps) {
  const [items, setItems] = useState<Entry[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  // Her giriş için seçilen aksiyon ve (reschedule ise) yeni tarih
  const [actions, setActions] = useState<Record<number, ResolveAction>>({});
  const [newDates, setNewDates] = useState<Record<number, string>>({});
  const [busyId, setBusyId] = useState<number | null>(null);

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const r = await api.get<Entry[]>('/entries/pending-resolution');
      setItems(r.data);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Bekleyen kararlar yüklenemedi.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  // Liste boşaldığında dış dünyaya bildir.
  useEffect(() => {
    if (!loading && items.length === 0) {
      onAllResolved?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, items.length]);

  async function applyOne(id: number) {
    const action = actions[id];
    if (!action) {
      setErr('Lütfen önce bir aksiyon seçin.');
      return;
    }
    if (action === 'reschedule') {
      const v = newDates[id];
      if (!v) {
        setErr('Yeni tarih ve saat seçin.');
        return;
      }
    }
    setErr(null);
    setBusyId(id);
    try {
      const payload: any = { action };
      if (action === 'reschedule') {
        payload.new_occurs_at = localInputToUtcIso(newDates[id]);
      }
      await api.post(`/entries/${id}/resolve`, payload);
      setItems((prev) => prev.filter((x) => x.id !== id));
      setActions((prev) => {
        const c = { ...prev };
        delete c[id];
        return c;
      });
      setNewDates((prev) => {
        const c = { ...prev };
        delete c[id];
        return c;
      });
      onChange?.();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Karar uygulanamadı.');
    } finally {
      setBusyId(null);
    }
  }

  const remaining = items.length;
  const allChosen = useMemo(
    () =>
      items.length > 0 &&
      items.every((it) => {
        const a = actions[it.id];
        if (!a) return false;
        if (a === 'reschedule' && !newDates[it.id]) return false;
        return true;
      }),
    [items, actions, newDates],
  );

  async function applyAll() {
    setErr(null);
    for (const it of items) {
      const a = actions[it.id];
      if (!a) continue;
      if (a === 'reschedule' && !newDates[it.id]) continue;
      // Sırayla uygula; bir hata olursa dur ve kullanıcıya göster.
      setBusyId(it.id);
      try {
        const payload: any = { action: a };
        if (a === 'reschedule') {
          payload.new_occurs_at = localInputToUtcIso(newDates[it.id]);
        }
        await api.post(`/entries/${it.id}/resolve`, payload);
      } catch (e: any) {
        setErr(
          `Giriş #${it.id} için karar uygulanamadı: ` +
            (e?.response?.data?.detail || 'bilinmeyen hata'),
        );
        setBusyId(null);
        // Mevcut durumu tazele ki başarılı olanlar listede görünmesin.
        await load();
        return;
      }
    }
    setBusyId(null);
    setActions({});
    setNewDates({});
    await load();
    onChange?.();
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-start justify-center z-50 p-4 overflow-y-auto">
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow-xl w-full max-w-3xl my-8">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-slate-700">
          <div>
            <h2 className="font-semibold text-gray-900 dark:text-slate-100">
              Bekleyen Kararlar
            </h2>
            <p className="text-xs text-gray-500 dark:text-slate-400 mt-0.5">
              Bir önceki vardiyadan kalan <b>DDoS Taşıma</b> (zamanı geçmiş planlamalar)
              ve <b>Bilgi</b> girişleri için karar verin. Diğer tipler için ek karar
              gerekmez.
            </p>
          </div>
          <button
            type="button"
            className="text-gray-500 dark:text-slate-400"
            onClick={onClose}
            aria-label="Kapat"
          >
            ✕
          </button>
        </div>

        <div className="p-5 space-y-4">
          {loading ? (
            <div className="text-sm text-gray-500 dark:text-slate-400">
              Yükleniyor…
            </div>
          ) : items.length === 0 ? (
            <div className="text-sm text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800/40 rounded p-3">
              Bekleyen karar yok. Yeni vardiya raporunu hazırlamaya devam edebilirsiniz.
            </div>
          ) : (
            <>
              <div className="text-xs text-gray-500 dark:text-slate-400">
                {remaining} bekleyen karar
              </div>

              <ul className="space-y-3">
                {items.map((e) => {
                  const action = actions[e.id];
                  const newDate = newDates[e.id] || '';
                  const isBusy = busyId === e.id;
                  return (
                    <li
                      key={e.id}
                      className="border border-gray-200 dark:border-slate-700 rounded-md p-3 space-y-3 bg-white dark:bg-slate-800"
                    >
                      <div className="flex items-start justify-between gap-3 flex-wrap">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-xs font-semibold uppercase text-gray-500 dark:text-slate-400">
                              {ENTRY_TYPE_LABEL[e.entry_type]}
                            </span>
                            {e.occurs_at && (
                              <span className="text-xs font-semibold text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-0.5 dark:text-amber-200 dark:bg-amber-900/30 dark:border-amber-800/40">
                                Geçmiş plan: {fmtLocal(e.occurs_at)}
                              </span>
                            )}
                          </div>
                          <div className="text-sm text-gray-800 dark:text-slate-100 mt-1 whitespace-pre-wrap">
                            {entryDisplay(e)}
                          </div>
                          <div className="text-xs text-gray-400 dark:text-slate-500 mt-1">
                            {e.author_name || `#${e.author_id}`} · oluşturuldu{' '}
                            {new Date(e.created_at).toLocaleString('tr-TR')}
                          </div>
                        </div>
                      </div>

                      <fieldset className="space-y-1.5 text-sm text-gray-700 dark:text-slate-200">
                        {e.entry_type === 'info' ? (
                          // --- BİLGİ: 2 seçenek (sona erdi / kalmaya devam) ---
                          // "Hayır, kalmaya devam edecek" seçilirse entry silinmez,
                          // bir sonraki vardiya raporu oluşturulurken aynı soru
                          // tekrar sorulur (entry'nin shift_id'si değişmez ve aktif
                          // olmayan vardiyaya ait olduğu için pending-resolution'a
                          // yine düşer).
                          <>
                            <div className="text-sm text-gray-700 dark:text-slate-200">
                              Bu bilgi durumu sona erdi mi?
                            </div>
                            <label className="flex items-start gap-2">
                              <input
                                type="radio"
                                name={`act-${e.id}`}
                                className="mt-0.5"
                                checked={action === 'completed'}
                                onChange={() =>
                                  setActions((p) => ({ ...p, [e.id]: 'completed' }))
                                }
                              />
                              <span>
                                <b>Evet, durum sona erdi</b>{' '}
                                <span className="text-xs text-gray-500 dark:text-slate-400">
                                  — giriş silinsin, sonraki vardiya raporlarına
                                  dahil edilmesin.
                                </span>
                              </span>
                            </label>
                            <label className="flex items-start gap-2">
                              <input
                                type="radio"
                                name={`act-${e.id}`}
                                className="mt-0.5"
                                checked={action === 'keep'}
                                onChange={() =>
                                  setActions((p) => ({ ...p, [e.id]: 'keep' }))
                                }
                              />
                              <span>
                                <b>Hayır, bu bilgi kalmaya devam edecek</b>{' '}
                                <span className="text-xs text-gray-500 dark:text-slate-400">
                                  — sonraki vardiya raporu oluşturulurken aynı
                                  soru tekrar sorulacak; her vardiyada karar
                                  yeniden verilir.
                                </span>
                              </span>
                            </label>
                          </>
                        ) : (
                          // --- DDoS TAŞIMA: 3 seçenek (tamamlandı / yeniden planla / tarih belli değil) ---
                          <>
                            <label className="flex items-start gap-2">
                              <input
                                type="radio"
                                name={`act-${e.id}`}
                                className="mt-0.5"
                                checked={action === 'completed'}
                                onChange={() =>
                                  setActions((p) => ({ ...p, [e.id]: 'completed' }))
                                }
                              />
                              <span>
                                <b>Evet, taşıma tamamlandı</b>{' '}
                                <span className="text-xs text-gray-500 dark:text-slate-400">
                                  — giriş silinsin, yeni rapora dahil edilmesin.
                                </span>
                              </span>
                            </label>

                            <label className="flex items-start gap-2">
                              <input
                                type="radio"
                                name={`act-${e.id}`}
                                className="mt-0.5"
                                checked={action === 'reschedule'}
                                onChange={() =>
                                  setActions((p) => ({ ...p, [e.id]: 'reschedule' }))
                                }
                              />
                              <span className="flex-1">
                                <b>Hayır, taşıma tamamlanmadı — yeni tarih:</b>
                                <input
                                  type="datetime-local"
                                  className="input mt-1 max-w-xs"
                                  disabled={action !== 'reschedule'}
                                  value={newDate}
                                  onChange={(ev) =>
                                    setNewDates((p) => ({
                                      ...p,
                                      [e.id]: ev.target.value,
                                    }))
                                  }
                                />
                                <div className="text-xs text-gray-500 dark:text-slate-400 mt-1">
                                  Europe/Istanbul cinsinden seçin. Hatırlatma yeniden gönderilir.
                                </div>
                              </span>
                            </label>

                            <label className="flex items-start gap-2">
                              <input
                                type="radio"
                                name={`act-${e.id}`}
                                className="mt-0.5"
                                checked={action === 'keep_unscheduled'}
                                onChange={() =>
                                  setActions((p) => ({
                                    ...p,
                                    [e.id]: 'keep_unscheduled',
                                  }))
                                }
                              />
                              <span>
                                <b>Tarih belli değil</b>{' '}
                                <span className="text-xs text-gray-500 dark:text-slate-400">
                                  — giriş açık iş olarak listede kalsın; ileride
                                  manuel olarak tarih atanabilir.
                                </span>
                              </span>
                            </label>
                          </>
                        )}
                      </fieldset>

                      <div className="flex justify-end">
                        <button
                          type="button"
                          className="btn-primary text-sm"
                          disabled={
                            isBusy ||
                            !action ||
                            (action === 'reschedule' && !newDate)
                          }
                          onClick={() => applyOne(e.id)}
                        >
                          {isBusy ? 'Uygulanıyor…' : 'Kararı Uygula'}
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </>
          )}

          {err && (
            <div className="text-sm text-red-600 dark:text-red-400">{err}</div>
          )}
        </div>

        <div className="flex items-center justify-between gap-2 px-5 py-3 border-t border-gray-200 dark:border-slate-700 bg-gray-50 dark:bg-slate-900/40 rounded-b-lg">
          <button type="button" className="btn-ghost" onClick={onClose}>
            {items.length === 0 ? 'Kapat' : 'Sonra karar veririm'}
          </button>
          {items.length > 1 && (
            <button
              type="button"
              className="btn-primary text-sm"
              disabled={!allChosen || busyId !== null}
              onClick={applyAll}
              title={
                allChosen
                  ? 'Tüm seçili kararları sırayla uygula'
                  : 'Her giriş için aksiyon seçtikten sonra aktifleşir'
              }
            >
              Tümünü Uygula ({remaining})
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
