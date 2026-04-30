"""Configuración centralizada de la aplicación usando pydantic-settings."""

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    db_host:     str = "localhost"
    db_port:     int = 5432
    db_name:     str = "trl_db"
    db_user:     str = "trl_user"
    db_password: str = "trl_password"

    # App
    app_name:        str = "TRL Rugby API"
    app_version:     str = "1.0.0"
    debug:           bool = False
    current_season:  int = 2024
    semifinal_spots: int = 4

    # Simulation
    monte_carlo_iterations: int = 10_000
    default_predictor:      str = "elo"     # "elo" | "logistic" | "xgboost"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001"]

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def async_database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
