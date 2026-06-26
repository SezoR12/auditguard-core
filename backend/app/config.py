from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase Postgres
    SUPABASE_DB_HOST: str
    SUPABASE_DB_PORT: int = 6543
    SUPABASE_DB_NAME: str = "postgres"
    SUPABASE_DB_USER: str
    SUPABASE_DB_PASSWORD: str

    # Crypto
    SECRET_KEY: str
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    REDIS_URL: str = "redis://redis:6379/0"

    # File storage / encryption (Phase 2)
    # Root directory where encrypted uploads are persisted (Docker volume).
    STORAGE_ROOT: str = "/data"
    # Master key used to derive per-file AES-256-GCM keys. MUST be set in prod.
    ENCRYPTION_MASTER_KEY: str = "dev-insecure-master-key-change-me"
    # Max upload size in bytes (50 MB).
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024

    @property
    def async_database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.SUPABASE_DB_USER}:{self.SUPABASE_DB_PASSWORD}"
            f"@{self.SUPABASE_DB_HOST}:{self.SUPABASE_DB_PORT}/{self.SUPABASE_DB_NAME}"
        )

    @property
    def sync_database_url(self) -> str:
        # Alembic uses sync driver
        return (
            f"postgresql+psycopg2://{self.SUPABASE_DB_USER}:{self.SUPABASE_DB_PASSWORD}"
            f"@{self.SUPABASE_DB_HOST}:{self.SUPABASE_DB_PORT}/{self.SUPABASE_DB_NAME}"
        )


settings = Settings()
