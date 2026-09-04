from decimal import Decimal
from enum import StrEnum
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppMode(StrEnum):
    REPLAY = "replay"
    PAPER = "paper"
    LIVE = "live"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: str = "development"
    app_mode: AppMode = AppMode.REPLAY
    live_trading_enabled: bool = False
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/sentinelflow"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    max_position_usdt: Decimal = Field(default=Decimal(20), gt=0)
    max_daily_loss_usdt: Decimal = Field(default=Decimal(5), gt=0)
    min_accumulation_score: int = Field(default=75, ge=0, le=100)
    max_spread_percent: Decimal = Field(default=Decimal("0.20"), gt=0)
    signal_expiry_seconds: int = Field(default=60, ge=10, le=3600)
    max_live_signal_age_seconds: int = Field(default=120, ge=5, le=300)
    binance_mcp_endpoint: str = "https://agent.binance.com/mcp/agentic"

    @model_validator(mode="after")
    def protect_live_mode(self) -> "Settings":
        if self.app_mode == AppMode.LIVE and not self.live_trading_enabled:
            raise ValueError("APP_MODE=live requires LIVE_TRADING_ENABLED=true")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
