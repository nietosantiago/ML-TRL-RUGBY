"""Configuración centralizada de la aplicación usando pydantic-settings."""

from functools import lru_cache
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",          # ignorar vars del .env que no estén definidas aquí
    )

    # Database
    database_url_env:       Optional[str] = Field(None, alias="DATABASE_URL")
    async_database_url_env: Optional[str] = Field(None, alias="ASYNC_DATABASE_URL")

    db_host:     str = "localhost"
    db_port:     int = 5432
    db_name:     str = "trl_db"
    db_user:     str = "trl_user"
    db_password: str = "trl_password"

    # App
    app_name:        str = "TRL Rugby API"
    app_version:     str = "1.0.0"
    debug:           bool = False
    current_season:  int = 2026
    semifinal_spots: int = 4

    # Simulation
    monte_carlo_iterations: int = 10_000
    default_predictor:      str = "elo"

    # CORS — separados por coma
    cors_origins_str: str = "http://localhost:3000,http://localhost:3001"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins_str.split(",") if o.strip()]

    @property
    def database_url(self) -> str:
        if self.database_url_env:
            return self.database_url_env
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def async_database_url(self) -> str:
        if self.async_database_url_env:
            url = self.async_database_url_env
        else:
            url = self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        # Supabase transaction pooler: el dialecto asyncpg de SQLAlchemy no debe
        # cachear prepared statements (el pooler reasigna la conexión del server
        # entre transacciones y el statement cacheado deja de existir).
        if "prepared_statement_cache_size" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}prepared_statement_cache_size=0"
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
