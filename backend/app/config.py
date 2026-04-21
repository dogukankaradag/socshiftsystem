"""Application configuration loaded from environment variables.

ON-PREM ONLY: This system never contacts third-party / cloud services at runtime.
- Mail dispatch goes through an on-premise SMTP relay or Exchange (no SaaS).
- Summarization is fully deterministic (heuristic) and runs locally.
- No telemetry. No outbound HTTP at runtime.
"""
from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    app_name: str = "Vardiya Devir Sistemi"
    environment: str = "development"
    api_prefix: str = "/api"
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://localhost,http://localhost:8080"

    # Database (on-prem PostgreSQL)
    database_url: str = "postgresql+psycopg2://shift:shift@db:5432/shift"

    # Auth
    jwt_secret: str = "CHANGE_ME_IN_PRODUCTION_USE_A_LONG_RANDOM_STRING"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12  # 12h

    # Admin seed
    seed_admin_email: str = "admin@example.com"
    seed_admin_password: str = "admin123"
    seed_admin_name: str = "Sistem Yöneticisi"

    # Scheduler / reports
    # Default daily auto-dispatch crons (Europe/Istanbul). 07:00, 15:00, 23:00 = shift handovers.
    report_dispatch_cron: str = "0 7,15,23 * * *"
    # Timezone all schedules are evaluated in. GMT+3 — no DST.
    scheduler_timezone: str = "Europe/Istanbul"
    default_mailing_list: str = "ops-team@example.com"

    # Email (on-prem SMTP / Exchange relay).
    # If smtp_host is empty, emails are written to the log instead of sent (dry-run mode).
    smtp_host: str = ""
    smtp_port: int = 25
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "shift-bot@example.com"
    smtp_use_tls: bool = False  # set True for STARTTLS (typically port 587)
    smtp_use_ssl: bool = False  # set True for implicit TLS (typically port 465)

    # Reminder (planlı girişler için 30 dk önce e-posta)
    reminder_lead_minutes: int = 30  # kaç dakika önce hatırlat
    reminder_tick_seconds: int = 60   # hatırlatma jobunun aralığı

    # IMAP poller (DHS / İYS otomatik girişi — on-prem IMAP / Exchange)
    # imap_host boşsa poller devre dışıdır.
    imap_host: str = ""
    imap_port: int = 993
    imap_username: str = ""
    imap_password: str = ""
    imap_folder: str = "INBOX"
    imap_use_ssl: bool = True
    imap_poll_seconds: int = 600   # 10 dk
    # Konu satırı regex'leri. Eşleşen mailler DHS veya İYS girişi olarak kaydedilir.
    # Sayı ilk number grubundan alınır; grup yoksa body içinden ilk tam sayı bulunur.
    imap_subject_dhs_regex: str = r"(?i)DHS.*?(\d{1,6})"
    imap_subject_iys_regex: str = r"(?i).Y.*?case.*?(\d{1,6})"

    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
