from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase Postgres
    SUPABASE_DB_HOST: str
    SUPABASE_DB_PORT: int = 6543
    SUPABASE_DB_NAME: str = "postgres"
    SUPABASE_DB_USER: str
    SUPABASE_DB_PASSWORD: str

    # Supabase Auth (project that issues the JWTs the backend trusts)
    SUPABASE_URL: str = ""
    SUPABASE_JWT_SECRET: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_JWT_ALGORITHM: str = "HS256"
    SUPABASE_JWT_AUDIENCE: str = "authenticated"

    # Legacy / app crypto (still used for internal signing if needed)
    SECRET_KEY: str = "dev-insecure-secret-change-me"

    REDIS_URL: str = "redis://redis:6379/0"

    # File storage / encryption (Phase 2)
    STORAGE_ROOT: str = "/data"
    ENCRYPTION_MASTER_KEY: str = "dev-insecure-master-key-change-me"
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024

    @property
    def async_database_url(self) -> str:
        user = quote(self.SUPABASE_DB_USER, safe="")
        pwd = quote(self.SUPABASE_DB_PASSWORD, safe="")
        return (
            f"postgresql+asyncpg://{user}:{pwd}"
            f"@{self.SUPABASE_DB_HOST}:{self.SUPABASE_DB_PORT}/{self.SUPABASE_DB_NAME}"
        )

    @property
    def sync_database_url(self) -> str:
        user = quote(self.SUPABASE_DB_USER, safe="")
        pwd = quote(self.SUPABASE_DB_PASSWORD, safe="")
        return (
            f"postgresql+psycopg2://{user}:{pwd}"
            f"@{self.SUPABASE_DB_HOST}:{self.SUPABASE_DB_PORT}/{self.SUPABASE_DB_NAME}"
        )


settings = Settings()
