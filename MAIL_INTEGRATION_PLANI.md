# Mail Entegrasyon Planı (On-Prem / Lokal)

> **Önemli:** Bu sistem **kesinlikle hiçbir cloud servisi (SendGrid, AWS SES, Mailgun, vb.) kullanmaz.**
> Tüm posta trafiği şirket içi (on-prem) altyapı üzerinden gerçekleşir.
> Veriler ve kimlik bilgileri yalnızca lokal ortamda (Postgres + sunucu disk) tutulur.

---

## 1. Mimari Özeti

```
┌────────────────────┐        ┌─────────────────────┐        ┌──────────────────────┐
│  Vardiya Devir     │  SMTP  │  On-Prem SMTP Relay │   ───► │  Microsoft Exchange  │
│  Sistemi (FastAPI) │ ─────► │  (Postfix / IIS /   │        │   veya kurum içi     │
│  - aiosmtplib      │  STARTTLS │  Exchange Hub)   │        │   posta sunucusu     │
└────────────────────┘        └─────────────────────┘        └──────────────────────┘
        │                                                                 │
        ▼                                                                 ▼
   PostgreSQL                                                  Alıcı kullanıcı
   (Reports / AuditLog)                                        gelen kutusu
```

Backend, `aiosmtplib` ile **doğrudan SMTP** konuşur. Hiçbir noktada üçüncü
parti bir HTTP API kullanılmaz. Posta zarfının (envelope), gövdenin ve
alıcı listesinin tamamı sunucunun kendi belleğinde oluşturulur ve TLS
üzerinden SMTP sunucusuna iletilir.

---

## 2. Desteklenen Senaryolar

### 2.1. Senaryo A — Kurumsal SMTP Relay (önerilen)

Şirket içinde zaten bir SMTP relay (Postfix, sendmail, IIS SMTP, Exchange
Edge Transport, vb.) varsa en sade yol budur.

```env
SMTP_HOST=smtp.intra.sirket.local
SMTP_PORT=25            # ya da 587
SMTP_USE_TLS=false      # 587 kullanıyorsanız true (STARTTLS)
SMTP_USE_SSL=false
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM="Vardiya Devir Sistemi <vardiya-devir@sirket.local>"
```

- Relay genelde sunucu IP'si üzerinden whitelist'lendiği için kullanıcı
  adı/parola gerekmez. Yetersizse servis hesabı tanımlanır.
- Relay kendisi üzerinden Exchange'e (veya Internet'e) iletim yapar;
  uygulamanın doğrudan Exchange'e bağlanmasına gerek kalmaz.

### 2.2. Senaryo B — Doğrudan Microsoft Exchange (on-prem)

Exchange 2016 / 2019 / Subscription Edition kurulumları **SMTP client
submission**'u doğrudan kabul eder.

```env
SMTP_HOST=mail.sirket.local
SMTP_PORT=587
SMTP_USE_TLS=true       # STARTTLS zorunlu
SMTP_USE_SSL=false
SMTP_USERNAME=DOMAIN\vardiya-devir       # ya da UPN: vardiya-devir@sirket.local
SMTP_PASSWORD=*****
SMTP_FROM="Vardiya Devir Sistemi <vardiya-devir@sirket.com>"
```

- Exchange tarafında "Client Frontend" Receive Connector'ünün
  uygulamanın IP'sine **anonymous** ya da **TLS-authenticated relay**
  izni verilmiş olmalıdır.
- Servis hesabının "Send As" yetkisi (`Set-ADUser` veya Exchange
  EAC üzerinden) olmalıdır.
- Receive connector'da `RequireTLS = true` ve `AuthMechanisms = Tls,
  BasicAuth` kullanılması önerilir.

### 2.3. Senaryo C — Microsoft 365 Exchange Online (yalnızca on-prem
hibrit kurulumlarda)

Kullanıcı isteği gereği cloud bağımlılığı yok; bu senaryo
**önerilmez**. Yine de hibrit kurulumlarda dahili relay üzerinden
çıkış zorunlu olursa **internal relay** SMTP konektörü oluşturulup
yalnızca Senaryo A'daki gibi şirket içi adres kullanılmalıdır.

### 2.4. Senaryo D — Postfix nullclient (tamamen yerel)

Internet bağlantısı olmayan tesislerde (örn. NOC odası) tek başına
çalışan bir Postfix kurulumu kullanılabilir.

```bash
# /etc/postfix/main.cf
relayhost = [smtp.intra.sirket.local]:25
inet_interfaces = loopback-only
mynetworks = 127.0.0.0/8
```

Backend'in `SMTP_HOST=127.0.0.1`, `SMTP_PORT=25` ile çalışması
yeterlidir. Postfix tüm gönderimi sırada tutar, yeniden dener ve
şirket relay'ine teslim eder.

---

## 3. TLS / Sertifika Yönetimi

- Üretim ortamında SMTP bağlantısı **mutlaka TLS** üzerinden olmalı
  (`SMTP_USE_TLS=true` STARTTLS, ya da `SMTP_USE_SSL=true` saf TLS).
- Sunucunun root sertifikası şirket CA'sı tarafından imzalanmışsa,
  `backend` konteynerine `/usr/local/share/ca-certificates/` altına
  CA `.crt` dosyaları kopyalanıp `update-ca-certificates` ile sisteme
  eklenmelidir. (Dockerfile'a `RUN apt-get install -y ca-certificates
  && update-ca-certificates` satırları eklenir.)
- `aiosmtplib` Python `ssl` modülünün kök sertifika havuzunu kullanır;
  bu yüzden sistemin trust store'una eklemek yeterlidir.

---

## 4. Kimlik Bilgileri ve Sırların Yönetimi

- Tüm SMTP bilgileri **`backend/.env`** dosyasında tutulur ve repository'e
  commit edilmez (`.gitignore` zaten içerir).
- Üretimde dosya izinleri `chmod 600 backend/.env` olarak kısıtlanmalıdır.
- Docker Compose, `.env` dosyasını yalnızca `backend` servisine
  enjekte eder; konteyner dışında ifşa olmaz.
- Kurumda HashiCorp Vault / Windows DPAPI / Ansible Vault kullanılıyorsa,
  konteyner başlatılmadan önce `.env` dinamik olarak buradan üretilebilir.

---

## 5. Alıcı Listesi (Mailing List) Yönetimi

Sistem iki seviyeli alıcı yönetimi sunar:

1. **Yönetim Paneli → Mail Listeleri**
   Burada `İsim`, `TO` (virgülle ayrılmış), `CC` (opsiyonel), `Varsayılan`
   alanlarıyla listeler tanımlanır. Vardiya bittiğinde rapor otomatik
   olarak varsayılan listeye gönderilir.

2. **Rapor Üretiminde Override**
   Raporlar sayfasında "TO" ve "CC" alanları doldurulursa o anki gönderim
   için varsayılanın yerine bu adresler kullanılır. Persist edilmek
   istenirse Mail Listeleri sekmesinden eklenmelidir.

3. **Vardiya Tipine Özel Listeler**
   Veri modelinde `MailingList.shift_type` alanı mevcuttur (`day`,
   `evening`, `night`). Bu sayede gece vardiyası raporu yalnızca gece
   ekibine gidebilir.

---

## 6. Zamanlanmış Gönderim (Europe/Istanbul)

- `APScheduler` her 30 saniyede bir çalışır ve `Report` tablosundaki
  `status='scheduled' AND scheduled_at <= now()` kayıtları yakalar.
- Frontend'deki `datetime-local` girdisi naive bir zaman olarak
  backend'e gider. Backend `Europe/Istanbul` (`scheduler_timezone`)
  zamanı olarak yorumlar, UTC'ye çevirip `scheduled_at` kolonuna yazar.
- Türkiye DST kullanmadığından sapma riski yoktur (Europe/Istanbul = UTC+3 sabit).
- Zamanlanmış raporlar Raporlar sekmesinde **mavi `planlandı`** etiketiyle
  görünür. "Planlamayı İptal" butonu raporu `taslak` durumuna düşürür.

---

## 7. Hata Yönetimi & Yeniden Deneme

- Gönderim başarısız olursa `Report.status = failed`, hata mesajı
  `Report.error_message` alanına yazılır ve audit loga düşer
  (`report.dispatch_failed`).
- Kullanıcı, Raporlar sayfasında "Gönder" butonuyla manuel olarak
  yeniden tetikleyebilir.
- SMTP relay'den gelen geçici hatalar (4xx) için Postfix tarzı bir
  arka plan kuyruğu eklenmedi; relay'in kendi yeniden deneme
  mekanizmasını kullanması beklenir (Senaryo A/D).

---

## 8. Güvenlik Notları

- SMTP `EHLO` / banner bilgileri loglanmaz; sadece "ok" / hata
  durumu audit'e yazılır.
- Bilgi sızıntısını önlemek için rapor gövdesi (PDF + HTML) asla
  konsola loglanmaz; yalnızca `Report` tablosunda saklanır.
- Web UI üzerinden mail tetikleyebilen roller: **supervisor**, **admin**.
  `operator` raporu yalnızca okuyabilir / PDF indirebilir.
- Tüm gönderimler `audit_log` tablosuna `report.dispatched` /
  `report.dispatch_failed` event'leriyle yazılır (kim, ne zaman, kime).

---

## 9. Test Adımları (Pilot)

1. `backend/.env` dosyasında SMTP ayarlarını yukarıdaki senaryolardan
   birine göre doldurun.
2. `docker compose restart backend` ile servisi yeniden başlatın.
3. Web arayüzünde Yönetim → Mail Listeleri'nden bir test listesi
   ekleyin (kendinizi TO, BT yöneticisini CC olarak).
4. Yeni Giriş ile birkaç kayıt açın, "Aktif Vardiya"da görünür olduğunu
   doğrulayın.
5. Raporlar → Vardiya seçin → "Oluştur & Gönder". Mail kutunuza ulaşıp
   ulaşmadığını kontrol edin.
6. Aynı raporu bu sefer 5 dakika sonrasına planlayın; 30 saniye
   içerisinde otomatik gönderilmesi beklenir.
7. PDF indirmeyi test edin (`PDF` butonu).

---

## 10. Hiçbir Şekilde Kullanılmayan Servisler

Aşağıdaki servisler bilinçli olarak entegre edilmemiştir ve
edilmeyecektir:

- ❌ AWS SES, Mailgun, SendGrid, Postmark, SparkPost
- ❌ Microsoft Graph API (Exchange Online HTTP)
- ❌ Slack / Teams / Discord webhook'ları
- ❌ OpenAI / Anthropic / Azure OpenAI / Google Vertex
- ❌ Sentry, Datadog, New Relic gibi cloud telemetri servisleri
- ❌ Cloud secret manager'ları (AWS Secrets Manager, Azure Key Vault)

Tüm servis bağımlılıkları `docker-compose.yml`, `backend/requirements.txt`
ve `frontend/package.json` dosyaları üzerinden denetlenebilir; harici
hiçbir HTTP istemcisi (`httpx`, `requests`, `openai`, `anthropic`)
bulunmaz.
