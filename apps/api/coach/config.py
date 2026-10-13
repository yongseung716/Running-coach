from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    mode: str = "development"
    database_url: str = "sqlite:///./data/coach.db"
    data_dir: Path = Path("data")
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    dev_jwt_secret: str = ""
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    storage_bucket: str = "gpx-private"
    max_upload_bytes: int = 10 * 1024 * 1024

    def validate_runtime(self):
        if self.mode not in {"development", "production", "test"}:
            raise RuntimeError("Unknown MODE")
        if self.mode == "production":
            if not all([self.supabase_url.startswith("https://"), self.supabase_anon_key,
                        self.supabase_service_role_key, self.database_url.startswith("postgresql")]):
                raise RuntimeError("Production requires Supabase HTTPS, keys and PostgreSQL")
            if any(not x.startswith("https://") for x in self.allowed_origins.split(",")):
                raise RuntimeError("Production origins must be HTTPS")
        elif self.database_url.startswith("postgresql"):
            raise RuntimeError("Use production mode for PostgreSQL RLS")

    @property
    def origins(self):
        return self.allowed_origins.split(",")


@lru_cache
def settings():
    cfg = Settings()
    cfg.validate_runtime()
    return cfg
