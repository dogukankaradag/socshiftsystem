# Kurulum ve Güncelleme Rehberi — v0.5.4

Bu doküman iki şeyi adım adım anlatır:

1. **Bölüm A** — Şirketin intranet ağındaki bir Linux sunucuya sıfırdan
   kurulum + canlıya alma.
2. **Bölüm B** — Sen kodu GitHub'a push ettikten sonra mevcut
   müşterilerin/şirketlerin bu güncellemeyi nasıl çekeceği (versiyon
   tipine göre).

---

## Bölüm A — Şirket Linux sunucusuna sıfırdan kurulum

### A0. Ön koşullar (sunucu tarafı)

| Gereksinim | Notlar |
|------------|--------|
| Linux sunucu | Ubuntu 22.04+ / Debian 12+ / RHEL 9+ önerilir. 2 vCPU, 4 GB RAM, 20 GB disk yeterli. |
| Statik IP veya DNS | Şirket içi DNS'te bir A kaydı (`vardiya.sirket.local` gibi) idealdir. |
| İnternet | Sadece **ilk kurulumda** Docker imajlarını çekmek için. Çalışırken offline olabilir. |
| Şirket SMTP relay | Mail göndermek için (Exchange, Postfix, vb.) |
| (Opsiyonel) IMAP/Exchange mailbox | DHS/İYS otomatik girişi için |
| (Opsiyonel) TLS sertifikası | Şirket içi CA'dan, intranet domain'i için |

### A1. Docker ve Docker Compose kurulumu

Ubuntu/Debian için:

```bash
# Eski paketleri temizle
sudo apt remove -y docker docker-engine docker.io containerd runc 2>/dev/null

# Resmi Docker repo'sunu ekle
sudo apt update
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io \
                    docker-buildx-plugin docker-compose-plugin

# Servis hesabı (deployment için): docker grubuna ekle
sudo usermod -aG docker $USER
# Yeni grubun aktif olması için oturumu yenile
newgrp docker

# Doğrula
docker version
docker compose version
```

> Şirket internet kısıtlaması varsa: bu adımları DMZ'deki bir build
> sunucusunda yapıp imajları `docker save` / `docker load` ile transfer
> etmeyi düşün.

### A2. Repo'yu sunucuya çekme

İki seçenek var. Şirket içi git erişimi varsa **clone**, yoksa
**tarball** ile transfer.

#### Seçenek 1 — Doğrudan clone (önerilen, güncellemeleri kolaylaştırır)

```bash
sudo mkdir -p /opt/mailsys
sudo chown $USER:$USER /opt/mailsys
cd /opt
git clone https://github.com/<KULLANICI>/MailSys.git mailsys
cd mailsys
git checkout v0.5.4   # belirli sürüm tag'ine sabitle (önerilir)
```

Eğer repo private ise PAT (Personal Access Token) ile clone:

```bash
git clone https://<KULLANICI>:<TOKEN>@github.com/<KULLANICI>/MailSys.git mailsys
```

#### Seçenek 2 — Hava boşluğu (air-gap) için tarball

Lokal makinende:

```bash
git archive --format=tar.gz --prefix=mailsys/ v0.5.4 > mailsys-v0.5.4.tar.gz
scp mailsys-v0.5.4.tar.gz user@vardiya.sirket.local:/tmp/
```

Sunucuda:

```bash
sudo mkdir -p /opt && cd /opt
sudo tar xzf /tmp/mailsys-v0.5.4.tar.gz
sudo chown -R $USER:$USER /opt/mailsys
cd /opt/mailsys
```

### A3. `.env` dosyasını hazırlama

```bash
cd /opt/mailsys
cp .env.example .env
nano .env   # ya da: vim .env
```

Mutlaka değiştirilmesi gerekenler:

```ini
# --- Güvenlik ---
JWT_SECRET=<openssl rand -hex 32 ile üret>      # Ör: 9d8a7f...
SEED_ADMIN_EMAIL=admin@sirket.local
SEED_ADMIN_PASSWORD=<güçlü-geçici-parola>       # ilk girişten sonra değiştir
SEED_ADMIN_NAME=Sistem Yöneticisi

# --- Veritabanı (compose içinde db servisi) ---
POSTGRES_USER=shift
POSTGRES_PASSWORD=<güçlü-rastgele>
POSTGRES_DB=shift

# --- CORS (frontend'in göründüğü domain/IP) ---
CORS_ORIGINS=http://vardiya.sirket.local,http://10.0.20.15

# --- SMTP (mail gönderimi) ---
SMTP_HOST=smtp.sirket.local
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USE_SSL=false
SMTP_USERNAME=svc-vardiya
SMTP_PASSWORD=<servis-hesabı-parolası>
SMTP_FROM=vardiya-bot@sirket.local
DEFAULT_MAILING_LIST=noc-team@sirket.local

# --- (Opsiyonel) IMAP — DHS/İYS otomatik girişi ---
IMAP_HOST=mail.sirket.local
IMAP_PORT=993
IMAP_USE_SSL=true
IMAP_USERNAME=svc-vardiya-ingest
IMAP_PASSWORD=<servis-hesabı-parolası>
IMAP_FOLDER=INBOX
IMAP_POLL_SECONDS=600

# --- Zaman dilimi ---
SCHEDULER_TIMEZONE=Europe/Istanbul
ENVIRONMENT=production
```

`JWT_SECRET` üretmek için:

```bash
openssl rand -hex 32
```

> SMTP boş bırakılırsa sistem **dry-run** modunda çalışır — mailler diske
> loglanır, gönderim olmaz. Test için kullanışlıdır ama production'da
> mutlaka doldurulmalı.

### A4. İlk başlatma

```bash
cd /opt/mailsys
docker compose up -d --build
```

Bu komut:

1. PostgreSQL imajını çeker, `db_data` volume'unu oluşturur
2. Backend imajını build eder (Python deps install)
3. Frontend imajını build eder (npm install + Vite build + nginx)
4. Üç container'ı başlatır (`db`, `backend`, `frontend`)
5. Backend başlangıçta tabloları oluşturur ve seed admin'i ekler

İlerleyişi izle:

```bash
docker compose logs -f
# Ctrl+C ile çıkış (container'lar çalışmaya devam eder)

# Sadece backend logları
docker compose logs -f backend

# Container durumları
docker compose ps
```

Beklenen çıktı:

```
NAME                    STATUS              PORTS
mailsys-db-1            Up (healthy)
mailsys-backend-1       Up                  0.0.0.0:8000->8000/tcp
mailsys-frontend-1      Up                  0.0.0.0:8080->80/tcp
```

### A5. Sağlık kontrolü

Sunucu üzerinde:

```bash
# Backend ayakta mı
curl -fsS http://localhost:8000/api/docs >/dev/null && echo "backend OK"

# Frontend serving yapıyor mu
curl -fsSI http://localhost:8080 | head -1     # HTTP/1.1 200 OK beklenir
```

Şirket içindeki bir bilgisayardan:

```
http://<sunucu-ip>:8080      → Web arayüz (login ekranı)
http://<sunucu-ip>:8000/api/docs   → Swagger
```

İlk login: `.env`'deki `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD`.
**İlk girişten sonra Yönetim → Kullanıcılar'dan parolayı değiştirin.**

### A6. İntranette canlıya alma — DNS + ters proxy + TLS

Tek başına `8080` portunu açmak yerine, **kurum domain adı + 443 (HTTPS)**
kullanmak çok daha temiz. İki yol var:

#### A6.1. Kurumsal load balancer / WAF arkasında

Kurumda zaten F5 / NetScaler / nginx LB varsa: bunları
`vardiya.sirket.local:443 → <sunucu-ip>:8080` şeklinde yönlendirip TLS
terminasyonunu LB'de yap. Sonra `.env`'deki `CORS_ORIGINS`'i
`https://vardiya.sirket.local` yap, restart:

```bash
docker compose up -d
```

#### A6.2. Sunucunun kendisinde Caddy ile (en kolay)

Kurum CA'dan veya internal step-ca'dan sertifika al, Caddy ile sun:

```bash
# Caddy kur
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

`/etc/caddy/Caddyfile`:

```caddy
vardiya.sirket.local {
    tls /etc/ssl/sirket/vardiya.crt /etc/ssl/sirket/vardiya.key
    encode gzip

    # API trafiğini backend'e
    handle /api/* {
        reverse_proxy 127.0.0.1:8000
    }

    # Geri kalan her şey frontend'e (SPA)
    handle {
        reverse_proxy 127.0.0.1:8080
    }
}
```

```bash
sudo systemctl reload caddy
sudo systemctl enable caddy
```

Sonra `.env`:

```ini
CORS_ORIGINS=https://vardiya.sirket.local
```

`docker compose up -d` ile backend'i restart et.

> Caddy yerine nginx tercih edersen aynı reverse-proxy kurgusunu nginx
> ile de yapabilirsin; örnek konfigürasyon Caddyfile'a denk düşer.

#### A6.3. Şirket içi DNS kaydı

Network ekibinden `vardiya.sirket.local` için sunucu IP'sine A kaydı
açtır. (Veya `/etc/hosts` ile pilot kullanıcılarda test et.)

### A7. Servisi sistemd ile garanti altına almak

Docker zaten `restart: unless-stopped` ile yeniden başlatılır, ama
sunucu reboot'unda Docker daemon'unun da otomatik kalkması için:

```bash
sudo systemctl enable docker
```

Compose stack'inin reboot sonrası otomatik kalkması zaten sağlanmış olur.

İsteğe bağlı olarak bir systemd unit ekleyebilirsin:

```bash
sudo tee /etc/systemd/system/mailsys.service >/dev/null <<'EOF'
[Unit]
Description=Vardiya Devir Sistemi (Docker Compose)
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/mailsys
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now mailsys.service
```

### A8. Yedekleme (kritik — production'da atlama)

Veritabanı `db_data` adlı bir Docker volume'unda. Günlük dump alın:

```bash
sudo tee /opt/mailsys/backup.sh >/dev/null <<'EOF'
#!/bin/bash
set -euo pipefail
TS=$(date +%F-%H%M)
DEST=/var/backups/mailsys
mkdir -p "$DEST"
cd /opt/mailsys
docker compose exec -T db pg_dump -U shift shift | gzip > "$DEST/db-$TS.sql.gz"
# 30 günden eskileri sil
find "$DEST" -name "db-*.sql.gz" -mtime +30 -delete
EOF
sudo chmod +x /opt/mailsys/backup.sh

# Cron: her gün 02:30
( sudo crontab -l 2>/dev/null; echo "30 2 * * * /opt/mailsys/backup.sh" ) | sudo crontab -
```

Geri yükleme (felaket senaryosu):

```bash
cd /opt/mailsys
gunzip < /var/backups/mailsys/db-2026-04-30-0230.sql.gz \
  | docker compose exec -T db psql -U shift shift
```

### A9. Sonraki kontrol listesi

- [ ] Admin parolası değiştirildi
- [ ] Üretim kullanıcıları (operator/supervisor/admin) Yönetim'den eklendi
- [ ] Mail listesi doğru: TO + CC alıcıları gerçek
- [ ] Test maili gitti (Reports'tan dummy bir taslak gönderip doğrula)
- [ ] Nöbetçi Listesi + Dağıtıcı Listesi yüklendi
- [ ] DNS + TLS çalışıyor (tarayıcı kilit ikonu)
- [ ] Yedek scripti cron'a eklendi
- [ ] (Opsiyonel) IMAP poller log'da hata vermiyor:
      `docker compose logs backend | grep -i imap`

---

## Bölüm B — GitHub'a push edilen güncellemeleri çekme akışı

Sen lokal makinende kod değişikliği yapıp push ettin (örn. `v0.5.3 → v0.5.4`).
Müşterinin sunucusunda bu güncellemeyi nasıl alacaksın? Üç senaryo var:

### B0. Önce: hangi tip güncelleme?

README'deki migration notlarından öğrenildiği gibi, üç farklı durum var:

| Tip | Örnek | Aksiyon |
|-----|-------|---------|
| **UI / kod değişikliği** | v0.5.3 → v0.5.4 | Sadece pull + rebuild — veri korunur |
| **Şema-uyumlu backend değişikliği** | v0.4 → v0.5 | Sadece pull + rebuild — veri korunur |
| **Enum / şema değişikliği** | v0.5.2 → v0.5.3 | Önce SQL migration, sonra pull + rebuild — veri korunur |
| **Büyük şema kırılması** | v0.1 → v0.2 | Volume sıfırlama (eski veri kaybedilir) ya da Alembic migration |

Her sürümün CHANGELOG/migration notu README'nin "Veritabanı sıfırlama"
bölümünde tutulur. Push'tan **önce** o bölüme yeni satır eklemek
müşterinin elini rahatlatır.

### B1. Standart güncelleme akışı (her seferinde aynı 4 adım)

Müşteri sunucusunda:

```bash
cd /opt/mailsys

# 1. Yedek (kritik — özellikle migration varsa)
./backup.sh

# 2. Yeni sürüm tag'ini çek
git fetch --tags origin
git checkout v0.5.4              # ya da: git pull origin main

# 3. (Migration varsa) — README'deki SQL'i çalıştır
#    Ör. v0.5.2 → v0.5.3:
docker compose exec -T db psql -U shift shift <<'SQL'
ALTER TYPE rosterteam ADD VALUE IF NOT EXISTS 'distributor';
ALTER TYPE rosterteam ADD VALUE IF NOT EXISTS 'lunch';
SQL

# 4. Rebuild + restart
docker compose build
docker compose up -d
```

Build cache sayesinde sadece değişen katmanlar yeniden derlenir;
genelde 30–90 saniye sürer.

### B2. Tek satırlık güncelleme scripti (kolay tutmak için)

`/opt/mailsys/update.sh` olarak kaydet:

```bash
#!/bin/bash
# update.sh — bir sürüm tag'ine güvenli geçiş
set -euo pipefail

if [ -z "${1:-}" ]; then
  echo "Kullanım: ./update.sh v0.5.4"
  exit 1
fi
TAG="$1"

cd "$(dirname "$0")"

echo "==> Yedek alınıyor..."
./backup.sh

echo "==> Tag'ler çekiliyor..."
git fetch --tags origin

echo "==> $TAG sürümüne geçiliyor..."
git checkout "$TAG"

echo "==> Migration kontrolü için README'yi okuyun:"
echo "    grep -A 10 \"$TAG\" README.md"
read -p "Migration SQL'i çalıştırdınız mı (veya gerek yok mu)? [y/N] " ok
if [[ ! "$ok" =~ ^[Yy]$ ]]; then
  echo "İptal edildi. Önce migration'ı tamamlayın."
  exit 1
fi

echo "==> Rebuild..."
docker compose build

echo "==> Restart..."
docker compose up -d

echo "==> Logları izle: docker compose logs -f backend"
```

Çalıştır:

```bash
chmod +x /opt/mailsys/update.sh
./update.sh v0.5.4
```

### B3. Senaryo bazlı örnekler

#### B3.1. Sadece UI değişikliği (v0.5.3 → v0.5.4 gibi)

```bash
cd /opt/mailsys
git fetch --tags origin
git checkout v0.5.4
docker compose build frontend
docker compose up -d frontend
```

Backend ve DB hiç yeniden başlamaz; kullanıcılar oturumda kalır.
30 saniye sürer.

#### B3.2. Backend kod değişikliği (şema değişmeden)

```bash
cd /opt/mailsys
./backup.sh
git fetch --tags origin
git checkout vX.Y.Z
docker compose build backend frontend
docker compose up -d
```

Backend container ~5 saniye downtime ile yeniden başlar.

#### B3.3. Enum / şema değişikliği (v0.5.2 → v0.5.3 gibi)

```bash
cd /opt/mailsys
./backup.sh

# Önce DB migration — uygulama eski kodla çalışırken bile güvenli
docker compose exec -T db psql -U shift shift <<'SQL'
ALTER TYPE rosterteam ADD VALUE IF NOT EXISTS 'distributor';
ALTER TYPE rosterteam ADD VALUE IF NOT EXISTS 'lunch';
SQL

# Şimdi yeni kodu deploy et
git fetch --tags origin
git checkout v0.5.3
docker compose build
docker compose up -d
```

> **Sıralama önemli**: önce SQL, sonra rebuild. Aksi halde yeni kod
> eski enum'a yazmaya çalışıp hata verir.

#### B3.4. Geri alma (rollback)

Bir güncelleme bozulursa:

```bash
cd /opt/mailsys

# Önceki sürüm tag'ine dön
git checkout v0.5.3
docker compose build
docker compose up -d

# DB hasar görmüşse, yedekten geri yükle
gunzip < /var/backups/mailsys/db-2026-04-30-0230.sql.gz \
  | docker compose exec -T db psql -U shift shift
```

> Şema değişikliği içeren bir sürümden geri dönerken yeni eklenen enum
> değerlerinin DB'de kalması bir sorun değil — eski kod onları görmez.
> Ama yeni eklenen tablo/kolon kullanılıyorsa veri kaybı riski vardır.
> Bu nedenle yedek şarttır.

### B4. Air-gapped (internet yok) müşteri için akış

GitHub'a doğrudan erişimi olmayan müşteri için:

**Sen (lokal):**

```bash
cd C:\Users\<user>\Desktop\MailSys
git checkout v0.5.4
git archive --format=tar.gz --prefix=mailsys/ v0.5.4 > mailsys-v0.5.4.tar.gz
# Bu dosyayı USB / S/FTP / kurum dosya sunucusuyla teslim et
```

**Müşteri sunucusunda:**

```bash
cd /opt/mailsys
./backup.sh

# Mevcut çalışan sürümün yedeği
sudo cp -r /opt/mailsys /opt/mailsys.bak.$(date +%F)

# Yeni dosyaları yerleştir (.env ve docker-compose.override.yml dokunulmaz)
tar xzf /tmp/mailsys-v0.5.4.tar.gz -C /tmp
rsync -a --exclude='.env' --exclude='docker-compose.override.yml' \
       --exclude='backup.sh' --exclude='update.sh' \
       /tmp/mailsys/ /opt/mailsys/

# Migration varsa burada
# docker compose exec -T db psql -U shift shift < migration.sql

docker compose build
docker compose up -d
```

### B5. Müşteri tarafına bilgilendirme şablonu (release notu)

Her tag push'undan sonra müşteriye yollayacağın kısa not:

```
Konu: Vardiya Devir Sistemi v0.5.4 yayında

Değişiklik özeti:
- "Dağıtıcı Listesi" üst menüden kaldırıldı; "Nöbetçi Listesi"
  başlığı dropdown'a dönüştü ve iki alt kalem altında toplandı.
- Backend / DB değişikliği yok — migration gerekmez.

Yükseltme komutu (sunucuda):
    cd /opt/mailsys
    ./update.sh v0.5.4

Beklenen downtime: ~30 saniye (sadece frontend container restart).

Sorun olursa:
    git checkout v0.5.3 && docker compose up -d
```

---

## Ek: Sürekli kullanılan komutların özeti

```bash
# Durum / loglar
docker compose ps
docker compose logs -f backend
docker compose logs --tail=200 frontend

# Restart
docker compose restart backend
docker compose up -d                  # değişiklik varsa fark eder

# Tek seferlik komut
docker compose exec backend python -c "from app.database import engine; print(engine.url)"
docker compose exec db psql -U shift shift     # interaktif psql

# Tam temizlik (DİKKAT — verileri siler)
docker compose down -v

# Disk kullanımı
docker system df
docker system prune -f                # kullanılmayan imajları temizle
```

---

## Ek: Sık karşılaşılan sorunlar

| Belirti | Sebep | Çözüm |
|--------|------|-------|
| Login ekranı geliyor ama login olmuyor, console'da CORS hatası | `CORS_ORIGINS` değeri frontend domain'ini içermiyor | `.env`'de `CORS_ORIGINS=https://vardiya.sirket.local` olmalı, sonra `docker compose up -d` |
| `invalid input value for enum rosterteam` | Volume eski, enum migration yapılmadı | B3.3'teki SQL'i çalıştır |
| Mail gitmiyor, log'da SMTP hatası yok | `SMTP_HOST` boş, dry-run'dasın | `.env`'i doldur, restart |
| Frontend `502 Bad Gateway` | Backend başlamadı | `docker compose logs backend` — genelde DB bağlantı hatası |
| `port is already allocated` | 8000 veya 8080 başka bir servis tarafından kullanılıyor | `docker compose.yml`'de port mapping'i değiştir (ör. `8001:8000`) |
| Build sırasında `npm` 403 / timeout | Şirket proxy'si | `.npmrc`'de proxy ayarla veya offline build'le devret |
| Saat dilimi yanlış | Sunucu UTC, planlamalar Europe/Istanbul bekliyor | `SCHEDULER_TIMEZONE=Europe/Istanbul` (zaten varsayılan) + container TZ=Europe/Istanbul (v0.9.4'te docker-compose'a eklendi) |
