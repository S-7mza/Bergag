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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
