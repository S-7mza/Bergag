from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://hamza:rootpassword@localhost:5433/marchespublics",
        alias="DATABASE_URL"
    )
    postgres_db: str = Field(default="marchespublics", alias="POSTGRES_DB")
    postgres_user: str = Field(default="hamza", alias="POSTGRES_USER")
    postgres_password: str = Field(default="rootpassword", alias="POSTGRES_PASSWORD")

    # Application Base URL (for deep-linking Fiche 60s from alerts)
    app_url: str = Field(default="http://localhost:8000", alias="APP_URL")

    # Scraper
    scraper_rate_limit_seconds: float = Field(default=1.0, alias="SCRAPER_RATE_LIMIT_SECONDS")
    scraper_page_size: int = Field(default=50, alias="SCRAPER_PAGE_SIZE")
    proxy_url: str | None = Field(default=None, alias="PROXY_URL")

    # AI & LLM
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")

    # Gmail SMTP Alert Settings
    smtp_host: str = Field(default="smtp.gmail.com", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str | None = Field(default=None, alias="SMTP_USER")
    smtp_password: str | None = Field(default=None, alias="SMTP_PASSWORD") # Gmail App Password
    alert_recipient_email: str | None = Field(default=None, alias="ALERT_RECIPIENT_EMAIL")

    # Enterprise Alerting & Webhooks
    webhook_url: str | None = Field(default=None, alias="WEBHOOK_URL")
    alert_min_score: float = Field(default=80.0, alias="ALERT_MIN_SCORE")
    alert_enable_email: bool = Field(default=True, alias="ALERT_ENABLE_EMAIL")
    alert_enable_webhook: bool = Field(default=True, alias="ALERT_ENABLE_WEBHOOK")

    # Security & RBAC
    jwt_secret_key: str = Field(
        default="bergag-procurement-secret-key-morocco-2026",
        alias="JWT_SECRET_KEY"
    )
    token_validity_seconds: int = Field(default=86400 * 7, alias="TOKEN_VALIDITY_SECONDS")
    allow_anonymous_dev_admin: bool = Field(default=True, alias="ALLOW_ANONYMOUS_DEV_ADMIN")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
