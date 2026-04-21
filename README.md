# Vardiya Devir Sistemi — v0.4.0

NOC / operasyon ekipleri için yapılandırılmış vardiya devir ve raporlama
platformu. Serbest format e-posta devir alışkanlığını; aranabilir,
denetlenebilir ve zamanlanmış otomatik raporlamaya taşır.

> **Stack:** Python 3.12 / FastAPI / SQLAlchemy 2 / PostgreSQL 16 / React 18 +
> TypeScript / Vite / Tailwind / Recharts. Tamamen on-prem (lokal) çalışacak
> şekilde Docker Compose ile paketlenmiştir.
>
> **Cloud bağımlılığı yok.** Hiçbir veri şirket dışına çıkmaz, harici API'lara
> bağlanılmaz. Bkz. [`MAIL_INTEGRATION_PLANI.md`](MAIL_INTEGRATION_PLANI.md).

---

## Kutunun içindekiler

| Konu                       | Nasıl çözüldü                                                     |
|----------------------------|-------------------------------------------------------------------|
| Web UI                     | React SPA, nginx arkasında (otomatik yenilenen panel)             |
| Kimlik doğrulama           | JWT (OAuth2 password) + bcrypt, route bazlı RBAC                  |
| Roller                     | `operator`, `supervisor`, `admin`                                 |
| Vardiya giriş türleri      | DDoS Taşıma, Bilgi, Yapılan Önemli İşler, L2'ye Eskale, Arayanlar, DHS, İYS |
| Sayısal giriş              | DHS ve İYS case sayıları (ör. 11, 33) ayrı kolonda                |
| Planlı işler               | Her girişin `occurs_at` alanı var; gelecekteki girişler tarih gelene kadar tüm vardiya raporlarında **"Yaklaşan Planlı İşler"** olarak hatırlatılır |
| Otomatik hatırlatma        | `occurs_at` zamanına 30 dk kala vardiyanın TO alıcılarına kısa hatırlatma e-postası |
| IMAP entegrasyonu          | DHS / İYS maillerinden otomatik giriş (on-prem IMAP / Exchange) — manuel giriş yine mümkün |
| Nöbetçi Listesi            | L2 + MSSP aylık vardiya çizelgesi; XLSX / PDF yükle + otomatik parse |
| Rapor başlığı              | Varsayılan: "MSSP Vardiya Raporu — X Vardiyası (tarih)" — UI'dan override edilir |
| Olay yönetimi              | açık → devam ediyor → çözüldü → kapalı                            |
| Rapor özeti                | Yerel (heuristik) özetleyici — harici LLM yok                     |
| Mükerrer tespiti           | Vardiya bazlı SequenceMatcher tabanlı benzerlik                   |
| Zamanlanmış gönderim       | APScheduler, GMT+3 (Europe/Istanbul); per-rapor datetime seçilir  |
| Alıcılar                   | TO + CC alanları, varsayılan mail listesi + per-rapor override    |
| Çıktılar                   | PDF (reportlab) ve CSV                                            |
| Analitik                   | 14 günlük trend, öncelik dağılımı, **30 günlük tür bazlı toplamlar** (toplam İYS, toplam DHS, vb.) |
| Denetim günlüğü            | Append-only `audit_logs` tablosu                                  |
| API-first                  | Tüm özellikler `/api/*` altında + `/api/docs` (Swagger)          |

---

## Hızlı başlangıç (Docker Compose)

```bash
# 1. Proje kökünde .env hazırlayın
cp .env.example .env
# JWT_SECRET değerini uzun, rastgele bir stringle değiştirin.
# SMTP ayarlarını MAIL_INTEGRATION_PLANI.md'ye göre doldurun.

# 2. Servisleri başlatın
docker compose up -d --build

# 3. Açın
#   Web arayüz:  http://localhost:8080
#   Swagger:     http://localhost:8000/api/docs
```

**Varsayılan giriş:** `admin@example.com` / `admin123` — ilk girişten
sonra hemen değiştirin.

İlk boot'ta backend, tabloları oluşturur ve varsayılan admin + mail
listesini seed eder. Veritabanı `db_data` volume'unda tutulur ve
`docker compose down` sonrası kalır.

### ⚠️ Veritabanı sıfırlama (enum değişiklikleri için zorunlu)

Aşağıdaki enum değişikliklerinden **her biri** PostgreSQL enum tipini değiştirir
ve mevcut veritabanı volume'u ile uyumsuz hale getirir; eski volume ile
başlatırsanız `invalid input value for enum ...` hatası alırsınız.

* v0.1 → v0.2: `EntryType` (`task/incident/alert/note` →
  `ddos_transfer/info/important_work/l2_escalation/callers/dhs/iys`),
  raporlara `scheduled_at` ve `cc_recipients` kolonları eklendi.
* v0.2 → v0.3: `ShiftType` (`day/evening/night` → `a/b/c`,
  Europe/Istanbul GMT+3 ile `A: 07:30–15:30`, `B: 15:30–23:30`,
  `C: 23:30–07:30` saatlerine bağlandı).
* v0.3 → v0.4: **Entry modeli yeniden şekillendirildi** — `priority` kolonu
  kaldırıldı; `occurs_at` (planlı gerçekleşme zamanı), `reminder_sent_at`
  ve `source` kolonları eklendi. Yeni `oncall_roster` tablosu (L2 / MSSP
  nöbetçi çizelgeleri) ve `RosterTeam` enum'ı eklendi. IMAP poller ve 30 dk
  hatırlatma scheduler job'ları eklendi. Rapor mail konusu varsayılan olarak
  "MSSP Vardiya Raporu — X Vardiyası (tarih)" formatına alındı.

Bu yüzden eski volume'u temizlemek gerekir:

```bash
docker compose down -v            # volume'ları da siler, verileri kaybedersiniz
docker compose up -d --build
```

Üretimde migration gerektiğinde Alembic'e geçilmelidir.

### Docker'sız (yerel geliştirme)

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload

# Frontend (ayrı terminalde)
cd frontend
npm install
npm run dev
```

---

## Mimari

```
┌──────────────┐   HTTPS   ┌──────────────────────┐   HTTP   ┌──────────────┐
│  React SPA   │──────────▶│  nginx (frontend)    │─────────▶│  FastAPI     │
└──────────────┘           │  /api/* reverse-proxy│          │  (uvicorn)   │
                           └──────────────────────┘          └──────┬───────┘
                                                                   │
                                                   SQLAlchemy      │
                                                                   ▼
                                                           ┌──────────────┐
                                                           │ PostgreSQL   │
                                                           └──────────────┘
                                                                   │
                                                  SMTP (on-prem)   ▼
                                               ┌──────────────────────┐
                                               │  Kurum SMTP Relay    │
                                               │  (Exchange/Postfix)  │
                                               └──────────────────────┘
```

### Tasarım notları

- **Servis katmanı (`app/services.py`)** hem HTTP hem zamanlanmış iş için
  tek kod yolu — manuel ve otomatik gönderim arasında sapma olmaz.
- **Özetleyici deterministiktir.** Harici LLM çağrısı yapılmaz; şirket
  içi veri hiçbir noktada dışarı çıkmaz.
- **SMTP boşsa dry-run.** `SMTP_HOST` boş bırakılırsa mailler disk'e
  loglanır, sistem yine de çalışmaya devam eder.
- **Zamanlayıcı in-process** (APScheduler AsyncIO). Europe/Istanbul
  (sabit GMT+3) tabanlıdır.
- **Alembic'e hazır.** Modeller Alembic ile tek komutta migration
  üretebilir; MVP için `create_all` yeterli.

---

## Vardiya Giriş Türleri

| Tür                | Giriş şekli   | Açıklama                                       |
|--------------------|---------------|------------------------------------------------|
| DDoS Taşıma        | metin         | Yapılan DDoS taşıma işleminin detayı           |
| Bilgi              | metin         | Sonraki vardiyaya aktarılacak serbest not       |
| Yapılan Önemli İşler | metin       | Önemli operasyonel aksiyonlar                   |
| L2'ye Eskale Edilen Konu | metin    | L2'ye eskale edilen konuların listesi           |
| Arayanlar          | metin         | Önemli arayan / geri aranacak kişi notları      |
| DHS                | **sayı**      | Vardiya boyu işlenen DHS case sayısı (ör. 11)   |
| İYS                | **sayı**      | Vardiya boyu işlenen İYS case sayısı (ör. 33)   |

Analitik sayfasında DHS ve İYS toplamları **son 30 günün toplam case
sayısını** gösterir (örn. "toplam İYS: 870"). Diğer türler için toplam,
kayıt sayısıdır.

### Planlı işler (`occurs_at`)

Her girişe opsiyonel bir "planlanan zaman" (GMT+3 tarih + saat)
atayabilirsiniz. Bu alan doldurulursa:

1. Giriş, **tarih gelene kadar** oluşturulan tüm vardiya raporlarına
   "Yaklaşan Planlı İşler" bölümünde otomatik olarak taşınır. Böylece 3 gün
   sonrası için yazılmış bir plan, araya giren her vardiyayı da uyarır.
2. `occurs_at` zamanına **30 dakika kala**, ilgili vardiyanın mail listesinin
   TO alıcılarına kısa bir Türkçe hatırlatma e-postası gönderilir (bu süre
   `REMINDER_LEAD_MINUTES` ile ayarlanabilir). Her giriş için yalnızca bir
   hatırlatma gönderilir (`reminder_sent_at` stamp'i ile garanti edilir).

### DHS / İYS Mail Entegrasyonu

Kurumsal Exchange / on-prem IMAP sunucusundan case sayıları otomatik
çekilebilir. `IMAP_HOST` doldurulduğunda `imap_poller.py`, her
`IMAP_POLL_SECONDS` saniyede bir `IMAP_FOLDER` içindeki **okunmamış**
mailleri tarar; konu / gövde üzerinde DHS / İYS regex'leri eşleşirse
açık vardiya altına `source='imap'` etiketli bir giriş oluşturur ve
maili SEEN olarak işaretler. Manuel giriş yine kullanılabilir durumdadır.

Exchange tarafındaki öneri: izole bir "vardiya-ingest" mailbox'ı açıp
yalnızca DHS / İYS raporlarının oraya yönlendirilmesi, servis hesabı için
IMAPS (port 993) + read/mark-seen izni.

### Nöbetçi Listesi (L2 + MSSP)

`Nöbetçi Listesi` menüsü iki sekme içerir:

* **L2 Ekibi** — ad soyad + tarih aralığı
* **MSSP Vardiyaları** — ad soyad + tarih aralığı + A/B/C etiketi

Supervisor/admin rolündeki kullanıcılar XLSX veya PDF dosyası yükleyebilir;
`openpyxl` (XLSX başlık-sezgili parser) ve `pdfplumber` (satır bazlı regex)
ile çizelge, normalize edilmiş satırlara çevrilir. **Orijinal dosya
saklanmaz** — yalnızca parse edilmiş satırlar DB'ye yazılır. Her yükleme bir
`upload_batch` UUID'si ile işaretlenir ve tek tıkla toplu silinebilir.

### Rapor Mail Konusu

Varsayılan konu: `MSSP Vardiya Raporu — {A/B/C Vardiyası} ({tarih})`.
Reports sayfasında "Mail Konusu (opsiyonel)" alanı doldurulursa bu değer
ezilir; sabit şablon değiştirmek istenmediği sürece boş bırakılır.

---

## API özeti

| Yöntem | Endpoint                                | Rol          | Açıklama                                        |
|--------|-----------------------------------------|--------------|--------------------------------------------------|
| POST   | `/api/auth/login-json`                  | public       | SPA için JSON login                             |
| GET    | `/api/shifts/current`                   | operator+    | Açık vardiya yoksa otomatik açar                |
| POST   | `/api/entries`                          | operator+    | Aktif vardiyaya giriş ekler                     |
| GET    | `/api/entries/export.csv`               | operator+    | CSV indirme                                      |
| POST   | `/api/reports/generate`                 | supervisor+  | `{shift_id, to_recipients, cc_recipients, scheduled_at?, dispatch?}` |
| POST   | `/api/reports/{id}/dispatch`            | supervisor+  | Mevcut taslağı gönder                           |
| POST   | `/api/reports/{id}/cancel-schedule`     | supervisor+  | Planlamayı iptal et                             |
| GET    | `/api/reports/{id}/export.pdf`          | operator+    | PDF                                              |
| GET    | `/api/analytics/overview`               | operator+    | 14 günlük trend + 30 günlük tür toplamları + `upcoming_count` |
| GET    | `/api/entries/upcoming`                 | operator+    | `occurs_at > now` olan girişler (yaklaşan planlı işler) |
| GET    | `/api/roster?team=l2\|mssp`             | operator+    | Nöbetçi listesi okuma                           |
| POST   | `/api/roster/upload` (multipart)        | supervisor+  | XLSX / PDF yükle → otomatik parse → toplu ekle  |
| POST   | `/api/roster` + `DELETE /api/roster/{id}` | supervisor+ | Manuel satır ekleme / silme                     |
| DELETE | `/api/roster/batch/{upload_batch}`      | supervisor+  | Bir yükleme grubunu toplu sil                   |
| `*`    | `/api/users`, `/api/mailing-lists`      | admin        | Yönetim                                          |

Tüm endpoint'ler `/api/docs` altında Swagger ile gezilebilir.

---

## Ortam değişkenleri (özet)

| Ad                        | Açıklama                                     |
|---------------------------|----------------------------------------------|
| `JWT_SECRET`              | 32+ karakter rastgele string                 |
| `DATABASE_URL`            | `postgresql://...`                          |
| `SCHEDULER_TIMEZONE`      | `Europe/Istanbul` (sabit GMT+3)             |
| `SMTP_HOST`, `SMTP_PORT`  | Kurum SMTP relay'i                          |
| `SMTP_USE_TLS`, `SMTP_USE_SSL` | STARTTLS / SMTPS seçimi                 |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Servis hesabı (gerekirse)           |
| `SMTP_FROM_ADDRESS`, `SMTP_FROM_NAME` | Gönderici kimliği                 |
| `REMINDER_LEAD_MINUTES`   | Planlı iş hatırlatması için dakika (varsayılan 30) |
| `REMINDER_TICK_SECONDS`   | Hatırlatma tarayıcısının aralığı (varsayılan 60)   |
| `IMAP_HOST` / `IMAP_PORT` | DHS/İYS IMAP sunucusu (boşsa poller devre dışı)    |
| `IMAP_USERNAME`, `IMAP_PASSWORD`, `IMAP_FOLDER` | IMAP kimlik & klasör     |
| `IMAP_USE_SSL`            | Exchange/IMAPS için `true` (port 993)              |
| `IMAP_POLL_SECONDS`       | IMAP tarama sıklığı (varsayılan 600 sn)            |
| `IMAP_SUBJECT_DHS_REGEX` / `IMAP_SUBJECT_IYS_REGEX` | Konu/body parse regex'leri |
| `CORS_ORIGINS`            | Frontend domain(leri)                        |
| `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` | İlk boot için seed admin      |

Detaylı e-posta konfigürasyon senaryoları için
[`MAIL_INTEGRATION_PLANI.md`](MAIL_INTEGRATION_PLANI.md).

---

## Güvenlik notları (üretim öncesi)

1. `JWT_SECRET`'i 32+ karakter rastgele bir değere çevirin.
2. İlk girişten sonra admin parolasını değiştirin.
3. nginx önünde TLS terminasyonu (Traefik / Caddy / kurum LB).
4. `DATABASE_URL`'i yedekli bir Postgres'e bağlayın.
5. `CORS_ORIGINS`'i sadece şirket domain'ine kısıtlayın.
6. `SMTP_USE_TLS=true` kullanın, least-privilege servis hesabı.
7. `audit_logs` tablosu hesap verebilirlik için tek doğruluk kaynağıdır.

---

## Repo yapısı

```
MailSys/
├── docker-compose.yml
├── .env.example
├── README.md
├── MAIL_INTEGRATION_PLANI.md
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── database.py
│       ├── models.py
│       ├── schemas.py
│       ├── auth.py
│       ├── ai.py                  # yerel heuristik özetleyici (harici API yok)
│       ├── email_service.py       # aiosmtplib, TO + CC, dry-run
│       ├── export.py              # PDF + CSV (Türkçe)
│       ├── report_builder.py      # Markdown + HTML şablonlar (Türkçe) — MSSP başlık varsayılanı
│       ├── services.py
│       ├── scheduler.py           # scheduled dispatch + 30dk hatırlatma + IMAP poll
│       ├── imap_poller.py         # on-prem IMAP/Exchange DHS-İYS otomatik girişi
│       ├── seed.py
│       └── routers/
│           ├── auth.py
│           ├── users.py
│           ├── shifts.py
│           ├── entries.py         # /upcoming endpoint'i eklendi, priority kaldırıldı
│           ├── incidents.py
│           ├── reports.py         # /generate destekler scheduled_at + TO/CC + subject_override
│           ├── analytics.py       # 30 günlük totals_30d + upcoming_count
│           ├── roster.py          # L2 / MSSP Nöbetçi Listesi CRUD + XLSX/PDF yükleme
│           └── mailing.py
└── frontend/
    ├── Dockerfile
    ├── nginx.conf
    ├── package.json
    └── src/
        ├── api/client.ts          # yeni EntryType birliği + Türkçe etiketler
        ├── auth/AuthContext.tsx
        ├── components/{Layout,PriorityBadge,ProtectedRoute}.tsx
        └── pages/
            ├── Login.tsx
            ├── Dashboard.tsx      # yaklaşan planlı işler listesi eklendi
            ├── NewEntry.tsx       # tür bazlı form (sayısal vs metin) + planlanan zaman
            ├── Incidents.tsx
            ├── Reports.tsx        # TO/CC + GMT+3 datetime + konu override
            ├── ReportDetail.tsx
            ├── Roster.tsx         # L2 / MSSP Nöbetçi Listesi + XLSX/PDF yükleme
            ├── Analytics.tsx      # 30 günlük tür toplamları widget'ı
            └── Admin.tsx          # Mail listelerinde CC kolonu
```

---

## Lisans

Organizasyonunuzun ihtiyaçlarına göre özgürce uyarlayabilirsiniz.
