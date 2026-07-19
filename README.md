# MSSP Handover — v0.8.15

> Eski adı: *Vardiya Devir Sistemi* (v0.7.3 ve öncesi). v0.8.0 itibarıyla
> uygulama markası `MSSP Handover` olarak güncellendi.

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
| Dağıtıcı Listesi           | Aylık dağıtıcı + öğlen nöbetçileri çizelgesi; aynı yükleme akışı (.xlsx / .pdf), aynı RBAC. Nöbetçi Listesi'nden ayrı bir menü altında |
| Bekleyen kararlar          | Yeni vardiya raporundan önce, geçmiş planlamalı **DDoS Taşıma** ve **Bilgi** girişleri için pop-up: tamamlandı (sil) / yeni tarih (yeniden planla) / tarih belli değil (açık iş olarak listede tut) |
| Rapor başlığı              | Varsayılan: "MSSP Vardiya Raporu — X Vardiyası (tarih)" — UI'dan override edilir |
| Düzenleme & silme          | Girişler, raporlar (gönderilmeden), olaylar, nöbet kayıtları, kullanıcılar ve mail listeleri için satır içi **Düzenle / Sil** + onay diyaloğu. Tüm operatörler birbirinin girişini düzenleyebilir/silebilir (her aksiyon audit log'a yazılır) |
| Tema                       | Aydınlık / karanlık mod toggle'ı; tercih `localStorage`'da saklanır, sistem temasını fallback olarak kullanır |
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
* v0.4 → v0.5: **Şema değişikliği yok.** Yalnızca yeni `PATCH` / `DELETE`
  uç noktaları (raporlar, mail listeleri, nöbet kayıtları) ve UI'da
  satır içi düzenle/sil butonları + modallar eklendi. Mevcut volume ile
  sorunsuz yükseltilebilir; sadece `docker compose build && docker compose up -d`
  yeterlidir.
* v0.5.0 → v0.5.1: **Şema değişikliği yok.** `entries` PATCH/DELETE artık
  `require_operator` ile koruyor — tüm operatörler birbirinin girişini
  düzenleyebilir/silebilir (sorumluluk audit log üzerinden izlenir). Aydınlık /
  karanlık tema toggle'ı eklendi (Tailwind `class` stratejisi, header'da
  ay/güneş ikonu, `localStorage` ile kalıcı). Yine sadece `docker compose
  build && docker compose up -d` yeterlidir.
* v0.5.1 → v0.5.2: **Şema değişikliği yok.** `GET /entries` artık
  `hide_past_scheduled` query parametresini destekliyor; Panel sayfasındaki
  "Aktif girişler" listesi bu parametreyi kullanarak `occurs_at` zamanı
  geçmiş planlamaları gizler. Yalnızca zamanı henüz gelmemiş veya zaman
  bilgisi girilmemiş girişler görünür. Analitik ve CSV export ham veriyi
  kullanmaya devam eder, dolayısıyla tür bazlı sayım/raporlamalar
  etkilenmez. Yine sadece `docker compose build && docker compose up -d`
  yeterlidir.
* v0.5.2 → v0.5.3: **PostgreSQL kullanıcıları için enum migration gerekir
  — SQLite'da otomatik.** `RosterTeam` enum'ına iki yeni değer eklendi:
  `distributor` (Aylık Dağıtıcı) ve `lunch` (Öğlen Nöbetçileri). Aynı
  `oncall_roster` tablosu paylaşılır; sadece `team` alanı ayrışır. Yeni
  "Dağıtıcı Listesi" sayfası (`/distributors`) Nöbetçi Listesi'nin
  yanında menüde yer alır. Ayrıca yeni "Bekleyen Kararlar" akışı:
  `GET /entries/pending-resolution` ve `POST /entries/{id}/resolve`
  endpoint'leri eklendi; UI tarafında Panel'de banner, Reports sayfasında
  "Oluştur/Planla/Oluştur & Gönder" butonlarına intercept eklendi.
  PostgreSQL'de yükseltme:

  ```sql
  ALTER TYPE rosterteam ADD VALUE IF NOT EXISTS 'distributor';
  ALTER TYPE rosterteam ADD VALUE IF NOT EXISTS 'lunch';
  ```

  Volume sıfırlamak istemeyenler bu iki SQL'i bir kez çalıştırır;
  ardından `docker compose build && docker compose up -d`.
* v0.5.3 → v0.5.4: **Sadece UI değişikliği — migration gerekmez.** Üst
  menüdeki "Dağıtıcı Listesi" düz linki kaldırıldı; bunun yerine
  "Nöbetçi Listesi" başlığı bir dropdown'a dönüştü. Dropdown altında
  iki alt kalem var: *Nöbetçi Listesi* (L2 + MSSP) ve *Dağıtıcı Listesi*
  (Aylık Dağıtıcı + Öğlen Nöbetçileri). Backend, route'lar ve sayfa
  içerikleri değişmedi; sadece `docker compose build && docker compose up -d`.
* v0.5.4 → v0.6.0: **Şema değişikliği yok — migration gerekmez.** Üç
  iyileştirme: (1) "Yeni Giriş" formunda *Planlanan Zaman* alanı artık
  yalnızca **DDoS Taşıma** türü için gösterilir; diğer türlerde gizli ve
  her zaman `null` yazılır (mevcut kayıtların stale `occurs_at` değerleri
  bir sonraki düzenlemede otomatik temizlenir). (2) Rapor maili artık
  yalnızca **inline HTML tablo** olarak gönderilir (Outlook/Gmail uyumlu,
  müşterinin paylaştığı şablona sadık); PDF eki **hiçbir gönderimde**
  eklenmez. PDF manuel indirme için `/api/reports/{id}/export.pdf`
  üzerinden hâlâ erişilebilir. (3) "Bekleyen Kararlar" akışı **Bilgi**
  türünü 2 seçenekli soruya alır ("Evet, raporda kalmaya devam etsin" /
  "Hayır, silinsin"); DDoS Taşıma'nın 3 seçenekli akışı dokunulmadan
  korunur. Yeni endpoint davranışı: `GET /entries/pending-resolution`
  artık Bilgi girişlerini aktif vardiya dışındaki tüm vardiyalardan
  toplar; `POST /entries/{id}/resolve` yeni `action=keep` değerini kabul
  eder (state değiştirmez, sadece audit yazar). Yine sadece
  `docker compose build && docker compose up -d`.
* v0.6.0 → v0.6.1: **Yeni tablolar — migration gerekir.** Müşteri İrtibat
  Listesi (Customer Orgs + Contacts) eklendi. Üç şey değişti: (1) `entries`
  tablosuna 3 yeni opsiyonel kolon: `caller_org_name`, `caller_contact_name`,
  `caller_contact_phone` (snapshot — irtibat ileride değişse/silinse bile
  tarihsel rapor bozulmaz). (2) Yeni tablolar `customer_orgs` ve
  `customer_contacts` (1-N ilişki). (3) `/api/customers/orgs` + alt
  endpoint'ler (CRUD). "Arayanlar" giriş formu artık 3 ayrı alan
  gösteriyor (kurum, kişi, numara) ve datalist autocomplete; yeni
  kurum/kişi otomatik olarak listeye eklenir. Analytics'e "Telefon
  Çağrıları — Kullanıcı Dağılımı" widget'ı eklendi (son 30 gün, hangi
  operatör kaç çağrı aldı). Rapor mail body'sinde "Telefon Çağrıları"
  satırı bullet listede kurum + kişi + numara olarak basılır.
  **Reports sayfasında** "Oluştur/Planla/Oluştur & Gönder" butonları
  artık bekleyen karar varsa önce ResolveScheduledModal'ı tetikler.

  PostgreSQL şema oluşturma (`Base.metadata.create_all` ilk açılışta
  hallediyor); manuel migration için:

  ```sql
  ALTER TABLE entries ADD COLUMN IF NOT EXISTS caller_org_name VARCHAR(255);
  ALTER TABLE entries ADD COLUMN IF NOT EXISTS caller_contact_name VARCHAR(255);
  ALTER TABLE entries ADD COLUMN IF NOT EXISTS caller_contact_phone VARCHAR(64);

  CREATE TABLE IF NOT EXISTS customer_orgs (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
  );

  CREATE TABLE IF NOT EXISTS customer_contacts (
    id SERIAL PRIMARY KEY,
    org_id INTEGER REFERENCES customer_orgs(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    phone VARCHAR(64),
    notes VARCHAR(512),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
  );

  CREATE INDEX IF NOT EXISTS ix_customer_contact_org_name
    ON customer_contacts (org_id, name);
  ```

  SQLite'da otomatik. Yine sadece `docker compose build && docker compose up -d`.
* v0.6.1 → v0.6.2: **Rol sistemi yeniden tasarımı (otomatik migration).**
  Üç rol (`operator/supervisor/admin`) tek hamlede ikiye düştü:
  - **Standart Kullanıcı** (`standard`) — Tüm sistem üzerinde tam yetki:
    kullanıcı oluşturma/düzenleme, mail listesi yönetimi, rapor oluşturma,
    giriş ekleme/düzenleme/silme, müşteri irtibat listesi CRUD, vb.
    Vardiya Listesi'ni **yalnızca okuyabilir** (düzenleme/silme/yükleme
    butonları görünmez).
  - **Super Admin** (`super_admin`) — Standart yetkilerinin tümü + Vardiya
    Listesi (Nöbetçi + Dağıtıcı) **çizelgelerine manuel müdahale** +
    başka bir kullanıcıyı **Super Admin rolüne yükseltme/indirme** yetkisi.

  **Migration otomatik** çalışır (`backend/app/seed.py:_migrate_roles`):
  açılışta tüm `operator/supervisor/admin` rolündeki kullanıcılar
  `standard`'a çevrilir; ardından en az bir `super_admin` yoksa
  `SEED_ADMIN_EMAIL` ile eşleşen kullanıcı `super_admin`'e yükseltilir.
  Sistem tek aktif super_admin'in pasifleştirilmesini ve rolünü
  düşürmesini engeller (orphaned-system koruması).

  PostgreSQL enum'ına yeni değerleri eklemek için manuel SQL gerekirse:

  ```sql
  ALTER TYPE role ADD VALUE IF NOT EXISTS 'standard';
  ALTER TYPE role ADD VALUE IF NOT EXISTS 'super_admin';
  -- Sonra startup'ta migration otomatik çalışır.
  ```

  SQLite'da bu adım gerekmez. `docker compose build && docker compose up -d`.
* v0.6.2 → v0.6.3: **Sadece UI değişikliği — migration gerekmez.** Üst
  menüdeki dropdown başlığı `Vardiya Listesi` olarak yeniden adlandırıldı
  (eski: `Nöbetçi Listesi`). Dropdown altı üç kalem:
  - *Nöbetçi Listesi* (L2 + MSSP) — herkes okur, Super Admin düzenler
  - *Dağıtıcı Listesi* (Aylık Dağıtıcı + Öğlen Nöbetçileri) — aynı yetki
  - *Aylık Vardiya Listesi* (`/aylik-vardiya`) — **yalnızca Super Admin** —
    v0.7.0'da otomatik vardiya jeneratörüne bağlanacak placeholder sayfa.

  Standart kullanıcılar yalnızca ilk iki kalemi görür; Aylık Vardiya
  Listesi menü ve route düzeyinde gizlidir (`ProtectedRoute requireRole`).
  Yine sadece `docker compose build && docker compose up -d`.
* v0.6.3 → v0.7.0: **Aylık vardiya otomatik jeneratörü (backend) +
  yeni tablolar — migration gerekir.**

  Yeni 2 tablo + 3 enum tipi:
  - `personnel` — personel master (lokasyon İstanbul/Ankara, grup
    siyah/mavi/kırmızı, on-call mı, sabit A mı)
  - `monthly_shift_assignment` — personel × gün × slot atamaları
  - Enum'lar: `personnellocation`, `personnelgroup`, `monthlyshiftslot`

  Yeni endpoint'ler:
  - `GET /api/personnel` — herkes okur; `POST/PATCH/DELETE` super_admin
  - `GET /api/monthly-shifts?year=Y&month=M` — herkes okur
  - `POST /api/monthly-shifts/generate` — super_admin (jeneratör çalıştırır)
  - `POST/PATCH/DELETE /api/monthly-shifts[/{id}]` — super_admin manuel müdahale

  Startup'ta `_seed_personnel()` çağrısı idempotent: bilinen 17 personeli
  (Rıdvan, Fatih, Mehmet, Beyza, Kübra, Enes, Duygu, İrfan, Yağız, Sabri,
  Doğukan, Burak, Talha, Hasan, Furkan, Ülkü, Zehra) seed eder. Aynı isimle
  kayıt varsa atlanır; super admin sonradan düzenleyebilir.

  Jeneratör rotasyon kuralları (Excel analizinden):
  - Sabit kadro (Rıdvan, Fatih): her hafta içi sabit A vardiyası
  - On-call rotasyonu (4 haftalık döngü): Zehra → Yağız → Ülkü → Sabri
  - Hafta içi B: Duygu + Furkan sabit + 1 rotating
  - Hafta içi C: 1 rotating
  - Hafta sonu (Cmt-Paz): A/B/C için 3 farklı rotating kişi
  - Manuel müdahale (modified_by_user_id) jeneratör tarafından korunur

  PostgreSQL'de manuel migration (opsiyonel — startup zaten oluşturur):

  ```sql
  -- create_all yeni tabloları oluşturur. Yeni enum'lar otomatik gelir.
  -- Sadece volume'u silmeden devam edenler için tablo seeding:
  --   docker compose restart backend  →  log: "Personnel seeded ..."
  ```

  **Frontend UI** bu sürümde sadece placeholder (`/aylik-vardiya` super_admin'e
  görünür). Tam takvim arayüzü ve manuel düzenleme UI'ı **v0.7.1**'de gelecek.
  Backend hazır olduğu için Swagger (`/api/docs`) üzerinden generate'i test
  edebilirsiniz.
* v0.7.0 → v0.7.1: **Sadece frontend — migration gerekmez.** Aylık Vardiya
  Listesi sayfası artık placeholder değil; gerçek takvim arayüzüyle geliyor:
  - **Üst bar:** Yıl + Ay seçici, "Otomatik Üret", "Sıfırla & Üret" (manuel
    kayıtlar dahil her şeyi siler), "Personel Yönet" modal, "CSV İndir"
  - **Grid:** satırlar personel, sütunlar ayın günleri (hafta sonu mavi).
    Hücreler slot kısaltmasıyla renk kodlu (A, B, C, OC, İZ, Off, A*).
    Manuel müdahale yapılmış hücrenin sağ üstünde kırmızı `●` işareti.
  - **Hücre tıklama → Düzenleme Modal** (yalnızca Super Admin): slot
    seç + not yaz, kaydı manuel-lock'la. Bir sonraki "Otomatik Üret"
    çağrısı bu hücreyi korur (`modified_by_user_id` IS NOT NULL).
  - **Personel Yönet Modal:** yeni personel ekle (ad, lokasyon, grup,
    on-call only / sabit A bayrakları), mevcut personeli aktif/pasif et.
    Atama varsa silme yerine soft delete (is_active=False).
  - **CSV indirme** her kullanıcı için açık; raporu Excel'de aç, filtrele,
    yazdır. UTF-8 BOM ile Türkçe karakterler bozulmaz.
  - **Renk legend'i** sayfanın altında — yeni kullanıcıya kısayolları öğretir.

  Sayfa yine sadece Super Admin'e açık (`ProtectedRoute requireRole`).
  Backend endpoint'leri değişmedi; sadece UI eklendi. Yine sadece
  `docker compose build && docker compose up -d`.
* v0.7.1 → v0.7.2: **Sadece UI değişikliği — migration gerekmez.**
  Aylık Vardiya Listesi artık **her giriş yapan kullanıcıya görünür**
  (read-only). Düzenleme yetkisi yine yalnızca Super Admin'de:
  - Standart kullanıcı: takvimi okuyabilir, CSV indirebilir, ay/yıl
    değiştirebilir. "Otomatik Üret", "Sıfırla & Üret", "Personel Yönet"
    butonları gizli; hücreye tıklayıp düzenleyemez.
  - Super Admin: tüm yetkiler eskisi gibi.

  Menü filtresinden `superAdminOnly` flag'i kalktı; route'tan
  `ProtectedRoute requireRole={['super_admin']}` gardı çıktı. Backend
  endpoint'leri zaten doğru korumalıydı (`GET` için
  `require_authenticated`, yazma için `require_super_admin`); değişiklik
  yok. Sadece `docker compose build frontend && docker compose up -d frontend`.
* v0.7.2 → v0.7.3: **Sadece backend — jeneratör algoritması revize edildi.**
  Kullanıcı tarif ettiği iş kurallarına göre `monthly_shift_generator.py`
  baştan yazıldı:

  - **Hafta içi B/C 1. personel rotasyonu** (9 kişilik döngü):
    Talha → Doğukan → İrfan → Burak → Enes → Kübra → Hasan → Mehmet → Beyza.
    Sıra her hafta 1 ileri kayar; bir kişi 1 hafta B-1st, sonraki hafta
    C-1st olarak çalışır. Sıraya geri dönüş ~9 haftada bir.
  - **B vardiyası 2. personel**: Furkan ve Duygu. Biri Pzt-Sa (2 gün
    ardışık), diğeri Çr-Cu (3 gün ardışık); haftalık parite ile
    "kim 2g, kim 3g" alternate. B'ye girmediği günlerde A vardiyasında.
  - **C vardiyası**: Bu hafta C-1st = geçen haftanın B-1st'i (otomatik).
  - **On-call** (4 haftalık döngü, Ank↔İst alternate):
    Zehra → Yağız → Ülkü → Sabri.
  - **Sabit A kadrosu** (Rıdvan, Fatih): her hafta içi a_fixed, hafta sonu yok.
  - **Hafta sonu (Cmt-Paz)**: A/B/C için 3 farklı kişi her gün; B/C-1st
    ve Furkan/Duygu hafta sonu off (çünkü hafta içi 5 günleri dolu).
  - **Max 5 gün/hafta** garantili tüm rollerde:
    - B/C-1st: 5 hafta içi → hafta sonu off
    - Furkan/Duygu: 5 gün (B + A karması) → hafta sonu off
    - Normal worker: 4 hafta içi A + 1 hafta sonu
  - **%20 hafta sonu off**: her 5 haftada 1 worker hafta sonu izinli sayılır
    (hafta sonu rotasyon havuzundan o hafta atlanır).
  - **Manuel müdahale koruması**: `modified_by_user_id IS NOT NULL` olan
    her atama, jeneratörden korunur (önceki davranışla aynı).

  Eksik personel uyarıları artık `warnings` array'inde döner — örn.
  Rıdvan/Fatih yoksa, "Personnel master'da bulunamayan rotasyon isimleri"
  uyarısı verilir. Mevcut Personnel master eskiden seed'lendi; yine de
  Personel Yönet'ten elle ekleme/aktivasyon yapılabilir.

  Sadece `docker compose build backend && docker compose up -d backend`.
* v0.7.3 → v0.8.0: **Marka değişikliği + kalibrasyon + UI iyileştirme.**
  Migration gerekmez.
  - **App adı yeniden adlandırıldı**: *Vardiya Devir Sistemi* → **MSSP Handover**
    (`config.app_name`, Layout header, Login, README, footer hepsinde).
  - **Jeneratör kalibrasyonu**: rotasyon anchor sabit tarihe taşındı —
    `ROTATION_ANCHOR_MONDAY = 2026-06-01` (Talha B-1st). Önceki yıllar
    negatif modulo ile doğru hesaplanır. Bu sayede her ay/yıl için
    deterministic + öngörülebilir çizelge.
  - **Furkan/Duygu B-2nd split düzeltildi**: Pzt-Çr (3 gün ardışık) +
    Pe-Cu (2 gün ardışık). Önceden Pzt-Sa(2)+Çr-Cu(3) yanlıştı.
    Haftalık parite ile alternate.
  - **'OC' → 'ON'** kısaltma (`SLOT_SHORT.oncall = 'ON'`).
  - **İzinli (`leave`) hücreleri** belirgin kırmızı arka plan + kalın
    border (`border-2 border-red-600`) + bold font. Hızlı göze çarpsın.
  - **Aylık Vardiya tablosu**: `text-xs` → `text-sm`, padding `py-1`→`py-2`,
    `px-1`→`px-2`, header'lar `font-bold`, gün numarası `text-base`,
    min-width `34px`→`44px` (hücreler daha okunaklı).
  - **Nöbetçi/Dağıtıcı Listesi tablosu**: `text-sm` → `text-base`,
    header'lar `text-sm uppercase font-bold` + gri arka plan.

  Sadece `docker compose build && docker compose up -d`.
* v0.8.0 → v0.8.1: **Dağıtıcı Listesi otomasyonu + Nöbetçi Listesi sade.**
  Yeni tablo eklendi (`daily_duty`) → `create_all` otomatik oluşturur.

  **Dağıtıcı Listesi (`/distributors`)** tamamen yenilendi:
  - Eski mantık (XLSX/PDF yükleme + manuel satır + iki tab) kaldırıldı
  - Yeni mantık: Aylık Vardiya'dan veri çekerek otomatik üretim
  - Her hafta içi gün için 1 Aylık Dağıtıcı + 1 Öğlen Nöbetçi
  - Eligible: o gün A vardiyasında olan kişiler (Rıdvan/Fatih hariç,
    on-call only ve sabit A hariç)
  - Greedy fair distribution: her aktif personele ayda **≥2 dağıtıcı +
    ≥2 öğlen** hedefli
  - <2 hedefe ulaşamamış kişiler kırmızı vurguyla "Kişi Bazlı Atama
    Özeti" panelinde gösterilir
  - Manuel müdahale koruması (`modified_by_user_id IS NOT NULL`)
  - Standart kullanıcı: read-only + CSV indir; Super Admin: Otomatik
    Üret + Sıfırla & Üret + hücreye tıklayarak manuel düzenleme

  **Nöbetçi Listesi (`/roster`)** sadeleşti:
  - Yalnızca **L2 ekibi** kaldı (MSSP, distributor, lunch tab'ları bu
    sayfadan kalktı; MSSP artık Aylık Vardiya'da otomasyonlu)
  - Backend `RosterTeam` enum'ı korundu — eski veriler bozulmaz; sadece
    UI filtrelemesi değişti

  **Yeni endpoint'ler:**
  - `GET /api/daily-duty?year=Y&month=M` — herkes okur
  - `POST /api/daily-duty/generate` — super_admin (jeneratör)
  - `POST /api/daily-duty` — super_admin (manuel ekle)
  - `PATCH/DELETE /api/daily-duty/{id}` — super_admin

  Sadece `docker compose build && docker compose up -d`.
* v0.8.1 → v0.8.2: **Dağıtıcı/öğlen havuzu genişletildi.** Migration gerekmez.
  On-call only kişiler (Sabri, Yağız, Ülkü, Zehra) artık dağıtıcı + öğlen
  nöbet havuzuna dahil. v0.8.1'de hatayla `is_oncall_only=True` ve
  `is_fixed_a=True` olanlar SQL filter'da hariç tutuluyordu — bu mantık
  yanlıştı.

  Yeni eligibility kuralı (`daily_duty_generator.py`):
  - Personnel havuzu = aktif + Rıdvan/Fatih hariç (sadece bu 2 isim)
  - Günlük blocking: kişi o gün **B/C/on-call/leave/off** slot'larından
    birinde ise eligible değil. A vardiyalı veya Aylık Vardiya'da hiç
    kaydı olmayan (örn. on-call kişinin diğer haftalarındaki günü)
    kişiler eligible.

  Sonuç: on-call kişiler kendi on-call haftası dışındaki tüm hafta içi
  günlerinde dağıtıcı/öğlen alabilir. Greedy round-robin sayesinde adil
  dağıtım otomatik. Sadece `docker compose build backend && docker compose up -d backend`.
* v0.8.2 → v0.8.3: **2 kişi/slot + öğlen aynı lokasyon kuralı.** PG için
  otomatik index migration var (startup'ta).

  Eskiden gün başına **1 dağıtıcı + 1 öğlen** atanıyordu. Şimdi:
  - **2 dağıtıcı** (lokasyon kısıtsız, karışık olabilir)
  - **2 öğlen nöbetçi** (her ikisi de aynı lokasyondan: Ank-Ank veya İst-İst)
  - Toplam 4 farklı kişi/gün (aynı kişi aynı günde iki rol almaz)

  Schema değişikliği:
  - `daily_duty` tablosunda eski `(day, duty_type)` unique index'i kaldırıldı
  - Yeni index: `(day, duty_type, personnel_id)` unique (duplicate kişi engellenir)
  - PG için `_migrate_daily_duty_index()` startup'ta eski index'i DROP eder

  Jeneratör (`daily_duty_generator.py`) yeniden yazıldı:
  - **Dağıtıcı**: greedy round-robin ile 2 farklı kişi (counts düşük olanlar)
  - **Öğlen**: önce 1. kişiyi pick et, sonra **aynı lokasyondan** 2. kişiyi pick et.
    Aynı lokasyonda 2. kişi yoksa, diğer lokasyondan iki kişiyle dene.
    Olmazsa tek kişi atanır + uyarı.
  - Aynı kişi aynı günde hem dağıtıcı hem öğlen alamaz (assigned_today set'i).
  - Manuel müdahale korunur; 1 manuel + 1 otomatik karması destekli.

  Frontend (`Distributors.tsx`):
  - Hücreler 2 kişiyi alt alta gösterir
  - 1 kişi atanmışsa "— 2. kişi atanmadı —" uyarısı
  - Edit modal **2 seat dropdown'ı** + her birine ayrı not alanı
  - Lokasyon uyarısı (öğlen için): farklı lokasyon seçildiyse amber uyarı
  - CSV: "Dağıtıcı 1, Dağıtıcı 2, Öğlen 1, Öğlen 2" 4 sütun
  - Aynı kişi 2 seat'e atama denemesi engellenir (frontend + backend)

  Yeni POST validation:
  - Aynı (day, duty_type) için max 2 atama (409 dönüyor 3.'de)
  - Aynı kişi aynı (day, duty_type) için tek kez atanır (409 duplicate'te)

  Sadece `docker compose build && docker compose up -d`.
* v0.8.3 → v0.8.4: **Cuma öğlen kuralı eklendi.** Migration gerekmez.
  - Pzt-Per: önceki gibi 2 dağıtıcı + 2 öğlen (öğlen aynı lokasyon)
  - **Cuma**: 2 dağıtıcı + yalnızca **1 öğlen nöbetçi**
  - Cuma öğleninde kişi mutlaka **Yağız / Sabri / Ülkü / Zehra** havuzundan
    seçilir (`FRIDAY_LUNCH_POOL` sabiti). Bu kişiler aynı zamanda diğer
    günlerin öğlen ve dağıtıcı havuzuna da dahil olmaya devam eder.
  - Frontend: Cuma öğlen hücresinde "2. kişi atanmadı" uyarısı çıkmaz.
    Edit modal'da Cuma öğlen seçildiğinde sadece 1 seat görünür + bilgi notu.

  Sadece `docker compose build && docker compose up -d`.
* v0.8.4 → v0.8.5: **Rapor mail body düzeni — her giriş türü kendi
  başlığı altında.** Migration gerekmez (sadece backend template).

  Eskiden Bilgi (info) girişleri "L2'ye eskale edilen önemli olay/konu"
  satırının altında kırmızı+kalın olarak gösteriliyordu. Bu yapı bozuldu;
  yeni mantık:
  - **Bilgi** ve **L2'ye Eskale Edilen Konu** ayrı satırlar
  - **Tüm tür satırları conditional** — ilgili giriş yoksa o satır
    rapora hiç eklenmez (boş başlık çıkmaz)
  - **MSSP Talepler** satırı (İYS/DHS/SM) her zaman görünür (rapor şablon
    standardı; rakamlar 0/boş olabilir)

  Yeni satır sırası (giriş varsa):
  1. MSSP Talepler (her zaman)
  2. Telefon ile gelen Müşteri Çağrıları (callers varsa)
  3. Yapılan Önemli İşler/Olaylar (important_work varsa)
  4. DDoS Taşıma (ddos_transfer varsa)
  5. **Bilgi** (info varsa) — kırmızı + kalın
  6. **L2'ye Eskale Edilen Konu** (l2_escalation varsa)
  7. Yaklaşan Planlı İşler (upcoming varsa)

  Sadece `docker compose build backend && docker compose up -d backend`.
* v0.8.5 → v0.8.6: **B rotasyon sırası + WFH slot + empty state.**
  PG için enum migration otomatik (startup).

  - **B vardiyası 1. personel rotasyonu güncellendi**:
    eski: Talha → Doğukan → İrfan → Burak → Enes → Kübra → Hasan → Mehmet → Beyza
    yeni: **Talha → İrfan → Doğukan → Enes → Burak → Kübra → Hasan → Mehmet → Beyza**
    (pozisyon 2-3 ve 4-5 yer değiştirdi). Anchor 1 Haz 2026 = Talha.
  - **Yeni slot türü: `wfh` (EV — Evden Çalışma)**
    - Sembol kılavuzunda mor/lila ile italic gösterilir
    - Edit modal'da seçilebilir 9 slot içinde
    - Jeneratör otomatik üretmez (sadece super admin manuel atayabilir)
  - **Empty state**: Aylık Vardiya'da henüz çizelge oluşturulmadıysa
    tablo yerine bilgi mesajı: "*Otomatik Üret butonuna basın*".
  - PG enum migration: startup'ta `ALTER TYPE monthlyshiftslot ADD VALUE
    IF NOT EXISTS 'wfh'`.

  Sadece `docker compose build && docker compose up -d`.

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
| PATCH  | `/api/entries/{id}`                     | operator+ (kendi) / supervisor+ | Giriş düzenle (`occurs_at` değişirse hatırlatma resetlenir) |
| DELETE | `/api/entries/{id}`                     | supervisor+  | Giriş sil                                        |
| GET    | `/api/entries/export.csv`               | operator+    | CSV indirme                                      |
| POST   | `/api/reports/generate`                 | supervisor+  | `{shift_id, to_recipients, cc_recipients, scheduled_at?, dispatch?}` |
| PATCH  | `/api/reports/{id}`                     | supervisor+  | Başlık / gövde / alıcı / planlama düzenle (gönderilmiş raporlar hariç) |
| DELETE | `/api/reports/{id}`                     | supervisor+  | Taslak / planlı / başarısız raporu sil (gönderilmiş silinemez) |
| POST   | `/api/reports/{id}/dispatch`            | supervisor+  | Mevcut taslağı gönder                           |
| POST   | `/api/reports/{id}/cancel-schedule`     | supervisor+  | Planlamayı iptal et                             |
| GET    | `/api/reports/{id}/export.pdf`          | operator+    | PDF                                              |
| GET    | `/api/analytics/overview`               | operator+    | 14 günlük trend + 30 günlük tür toplamları + `upcoming_count` |
| GET    | `/api/entries/upcoming`                 | operator+    | `occurs_at > now` olan girişler (yaklaşan planlı işler) |
| GET    | `/api/roster?team=l2\|mssp`             | operator+    | Nöbetçi listesi okuma                           |
| POST   | `/api/roster/upload` (multipart)        | supervisor+  | XLSX / PDF yükle → otomatik parse → toplu ekle  |
| POST   | `/api/roster` + `DELETE /api/roster/{id}` | supervisor+ | Manuel satır ekleme / silme                     |
| PATCH  | `/api/roster/{id}`                      | supervisor+  | Tek nöbet kaydını düzenle                       |
| DELETE | `/api/roster/batch/{upload_batch}`      | supervisor+  | Bir yükleme grubunu toplu sil                   |
| PATCH  | `/api/incidents/{id}` + `DELETE`        | operator+ / supervisor+ | Olay düzenle / sil                     |
| PATCH  | `/api/mailing-lists/{id}`               | admin        | Mail listesini düzenle (varsayılanı tek tıkla devret) |
| `*`    | `/api/users`, `/api/mailing-lists`      | admin        | Yönetim (deactivate / reactivate dahil)         |

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
