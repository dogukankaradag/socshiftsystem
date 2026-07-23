# MSSP Handover — v0.9.5

NOC / operasyon ekipleri için yapılandırılmış vardiya devir ve raporlama
platformu. Serbest format e-posta devir alışkanlığını; aranabilir,
denetlenebilir ve zamanlanmış otomatik raporlamaya taşır.

> **Stack:** Python 3.12 / FastAPI / SQLAlchemy 2 / PostgreSQL 16 / React 18 +
> TypeScript / Vite / Tailwind / Recharts. Tamamen on-prem (lokal) çalışacak
> şekilde Docker Compose ile paketlenmiştir.
>
> **Cloud bağımlılığı yok.** Hiçbir veri şirket dışına çıkmaz, harici API'lara
> bağlanılmaz.

---

## Kutunun içindekiler

| Konu                       | Nasıl çözüldü                                                     |
|----------------------------|-------------------------------------------------------------------|
| Web UI                     | React SPA, nginx arkasında                                        |
| Kimlik doğrulama           | JWT (OAuth2 password) + bcrypt, route bazlı RBAC                  |
| Roller                     | `standard`, `super_admin` (v0.6.2+)                               |
| Vardiya giriş türleri      | DDoS Taşıma, Bilgi, Yapılan Önemli İşler, L2'ye Eskale, Arayanlar, DHS, İYS |
| Sayısal giriş              | DHS ve İYS case sayıları ayrı kolonda                             |
| Planlı işler               | `occurs_at` alanı; gelecekteki DDoS Taşımalar tarih gelene kadar tüm vardiya raporlarında **"Yaklaşan Planlı İşler"** olarak hatırlatılır |
| Otomatik hatırlatma        | `occurs_at` zamanına 30 dk kala vardiyanın TO alıcılarına e-posta |
| MPLS ekibi hatırlatması    | DDoS Taşıma girişinde seçilen MPLS ekibine 30 dk önce mail        |
| IMAP entegrasyonu          | DHS / İYS maillerinden otomatik giriş (on-prem IMAP / Exchange)   |
| Nöbetçi Listesi            | L2 + MSSP aylık vardiya çizelgesi; XLSX / PDF yükle + parse       |
| Dağıtıcı Listesi           | Aylık dağıtıcı + öğlen nöbetçileri; aynı yükleme akışı            |
| Aylık Vardiya Listesi      | Otomatik jeneratör + manuel-lock desteği + FORCED_OVERRIDES       |
| Rapor başlığı              | Varsayılan: "MSSP Vardiya Raporu — X Vardiyası (tarih)"; UI'dan override |
| Düzenleme & silme          | Girişler, raporlar (gönderilmeden), olaylar için satır içi Düzenle / Sil |
| Tema                       | Aydınlık / karanlık mod toggle                                    |
| Rapor özeti                | Yerel heuristik özetleyici — harici LLM yok                       |
| Zamanlanmış gönderim       | APScheduler, Europe/Istanbul; per-rapor datetime                  |
| Alıcılar                   | TO + CC alanları, varsayılan mail listesi + per-rapor override    |
| Çıktılar                   | PDF (reportlab) ve CSV                                            |
| Analitik                   | 14 günlük trend, öncelik dağılımı, 30 günlük tür bazlı toplamlar  |
| Denetim günlüğü            | Append-only `audit_logs` tablosu                                  |
| API-first                  | `/api/*` altında + `/api/docs` (Swagger)                          |

---

## Personel yapılandırması

Personel kadrosu, rotasyon sıraları, on-call havuzu, Cuma öğlen havuzu ve
sabit override'lar bir JSON dosyasından okunur:

```
config/personnel_config.json            ← gerçek kadro (v0.9.2 itibariyle git ile takip edilir)
config/personnel_config.example.json    ← placeholder örneği
```

Kadro değişikliği yapmak için `config/personnel_config.json`'ı düzenleyip
`git commit` + `git push` yapın; sunucu `git pull` sonrası `docker compose
restart backend` ile yeni config'i yükler.

Docker Compose bu dizini backend container'ının `/app/config`'ine read-only
mount eder. Startup'ta config okunur ve `_seed_personnel()` DB'ye idempotent
yazar. Config'ten çıkarılan personel otomatik `is_active=False` yapılır.

**Yapılandırma alanları** (detay için `config/personnel_config.example.json`
içindeki `_schema_notes`):

| Alan                       | Açıklama                                                    |
|----------------------------|-------------------------------------------------------------|
| `personnel`                | Personel master listesi                                     |
| `excluded_from_daily_duty` | Dağıtıcı/öğlen atamalarından tamamen dışlanan isimler       |
| `weekday_rotation`         | B/C 1. personel haftalık rotasyon sırası                    |
| `b_secondary`              | B vardiyasında 2. personel (2 kişi ardışık gün paylaşımı)   |
| `oncall_rotation`          | On-call haftalık dönüşüm listesi                            |
| `friday_lunch_pool`        | Cuma öğlen özel havuzu                                      |
| `rotation_anchor_monday`   | Rotasyon indeksinin başladığı Pazartesi (ISO tarih)         |
| `forced_overrides`         | Sabit atamalar (her Otomatik Üret'te uygulanır)             |

---

## Hızlı başlangıç (Docker Compose)

```bash
# 1. .env dosyasını hazırlayın
cp .env.example .env
# JWT_SECRET değerini uzun, rastgele bir stringle değiştirin.

# 2. Personel config dosyasını hazırlayın
cp config/personnel_config.example.json config/personnel_config.json
$EDITOR config/personnel_config.json

# 3. Servisleri başlatın
docker compose up -d --build

# 4. Açın
#   Web arayüz:  http://localhost:8080
#   Swagger:     http://localhost:8000/api/docs
```

**Varsayılan giriş:** `admin@example.com` / `admin123` — ilk girişten
sonra hemen değiştirin.

---

## Rol modeli

- **Standard** (`standard`) — Vardiya devir işleyişinin tamamını kullanabilir.
  Vardiya listelerini yalnızca okuyabilir.
- **Super Admin** (`super_admin`) — Standart yetkileri + Vardiya çizelgelerine
  manuel müdahale + kullanıcı rol yönetimi.

Sistem tek aktif super_admin'in pasifleştirilmesini engeller (orphaned-system
koruması).

---

## Aylık Vardiya jeneratörü — İş kuralları

Config'te tanımlanan rotasyonlar üzerinden çalışır:

- **Hafta içi B/C 1. personel:** `weekday_rotation` listesinden `week_index % len`
  seçilir. 1 hafta B-1st, sonraki hafta C-1st (2 hafta vardiya, sonra rotasyonda
  bekleme).
- **Hafta içi B 2. personel:** `b_secondary` listesinden 2 kişi. Baş kişi
  Pzt-başlangıç, son kişi Cu-sonuç. Çift hafta 3-2, tek hafta 2-3.
- **Hafta içi C:** Bu hafta C-1st = önceki haftanın B-1st'i.
- **On-call:** `oncall_rotation` haftalık dönüşüm (Pzt-Paz aynı kişi).
- **On-call only kişiler:** on-call olmadıkları hafta kendi lokasyonlarının
  A vardiyasında.
- **Hafta sonu:** A/B/C için 3 farklı kişi. B/C 1st ve B-2nd bu hafta hafta sonu
  off (max 5/hafta).
- **Pazar C → Pazartesi off (v0.9.1):** Pazar günü C vardiyasında olan kişi
  bir sonraki Pazartesi hiçbir slotta olamaz — otomatik `off` atanır. Ay
  sınırını da geçer (önceki ayın son Pazar'ı DB'den okunur).
- **FORCED_OVERRIDES:** her Otomatik Üret / Sıfırla & Üret'te garantili
  uygulanır. On-call slot'lu override o hafta için normal rotasyonu skipler.

## Dağıtıcı + Öğlen jeneratörü — İş kuralları

- Sadece hafta içi (Pzt-Cu).
- **Dağıtıcı:** günde 1 İstanbul + 1 Ankara personeli. Haftada max 1/kişi.
- **Öğlen (Pzt-Per):** günde 2 kişi, aynı lokasyondan (haftalık 3 Ank / 2 İst
  desenine göre). Ankara + on-call-only iki kişi aynı gün öğlen olamaz.
- **Öğlen (Cuma):** 2 kişi, `friday_lunch_pool` havuzundan (lokasyon bağımsız).
  Pair kısıtı (Ankara + on-call-only ikilisi) uygulanır.
- **Havuz:** o gün B/C/leave/off olmayan tüm personel (on-call PASİF durum;
  aynı gün dist/öğlen alabilir). `excluded_from_daily_duty` listesi hariç.
- **Hedef:** kişi başı ay içinde ≥2 dağıtıcı + ≥2 öğlen.
- Manuel müdahale (`modified_by_user_id` NOT NULL) korunur — Aylık Vardiya
  çakışması hariç: bir kişi o gün `leave`/`off`/`B`/`C` alıyorsa mevcut
  dist/lunch kaydı (manuel dahil) otomatik silinip boşluk yeniden doldurulur
  (v0.9.3).

---

## Bakım & migration

Startup'ta otomatik çalışan migration'lar (`backend/app/seed.py`):

- Rol enum'una `standard` + `super_admin` değerleri
- Eski rol adlarını (`operator/supervisor/admin`) `standard`'a çevir
- `monthlyshiftslot` enum'una `wfh` ekle
- `entries` tablosuna `mpls_team_id`, `mpls_reminder_enabled`, `reported_at`
  kolonları
- Config'ten okunan personeli seed et; kadrodan çıkarılanları `is_active=False`
  yap

Manuel PostgreSQL migration gerekmez — hepsi idempotent.

---

## Güncelleme akışı

```bash
cd /path/to/mailsys
git pull origin main
docker compose build --pull=false
docker compose up -d --force-recreate
docker compose logs backend --tail=20
```

Config dosyasını değiştirdiyseniz backend'i restart edin (`docker compose
restart backend`).
