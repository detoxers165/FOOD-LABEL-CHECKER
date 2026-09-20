from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "development"
    app_name: str = "Label Analysis API"
    debug: bool = False

    mongodb_uri: str
    mongodb_database: str

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    otp_hmac_secret: str
    otp_expiry_seconds: int = 300
    otp_max_attempts: int = 5
    otp_resend_cooldown_seconds: int = 60
    otp_max_sends_per_hour: int = 5

    smtp_host: str
    smtp_port: int = 587
    smtp_username: str
    smtp_password: str
    smtp_from_email: str

    cors_origins: list[str] = Field(default_factory=list)

    max_images_per_scan: int = 4
    max_upload_size_mb: int = 10
    max_request_size_mb: int = 50

    upload_directory: str = "uploads"

    ai_engine: str = "mock"
    ai_reader_path: str | None = None
    ai_reader_version: str = "unknown"
    ai_max_concurrency: int = 1
    ai_timeout_seconds: int = 120

    log_level: str = "INFO"
    log_file: str = "logs/app.log"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        if value is None:
            return []

        if isinstance(value, str):
            return [
                item.strip()
                for item in value.split(",")
                if item.strip()
            ]

        return value

    @field_validator("ai_engine")
    @classmethod
    def validate_ai_engine(cls, value: str) -> str:
        value = value.lower().strip()

        if value not in {"mock", "real"}:
            raise ValueError("AI_ENGINE must be either 'mock' or 'real'")

        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
