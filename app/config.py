from functools import cached_property

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    app_env: str = 'development'
    telegram_bot_token: str = ''
    telegram_allowed_user_ids: str = ''
    indodax_api_key: str = ''
    indodax_secret_key: str = ''
    indodax_base_url: str = 'https://indodax.com'
    indodax_recv_window: int = 5000
    trading_enabled: bool = False
    live_trading_confirmation_required: bool = True
    dry_run: bool = True
    max_order_idr: int = 1_000_000
    max_daily_loss_idr: int = 100_000
    max_open_orders: int = 5
    max_position_idr: int = 2_000_000
    min_confidence: float = 0.65
    openai_api_key: str = ''
    openai_model: str = 'gpt-4.1-mini'
    database_url: str = 'postgresql+asyncpg://trader:change-me@postgres:5432/trading'
    redis_url: str = 'redis://redis:6379/0'
    order_monitor_interval_seconds: int = 10
    pair_whitelist: str = 'btc_idr'

    @cached_property
    def allowed_ids(self) -> set[int]:
        return {int(x.strip()) for x in self.telegram_allowed_user_ids.split(',') if x.strip()}

    @cached_property
    def pairs(self) -> set[str]:
        return {x.strip().lower() for x in self.pair_whitelist.split(',') if x.strip()}

    @property
    def live(self) -> bool:
        return self.trading_enabled and not self.dry_run and self.live_trading_confirmation_required


settings = Settings()
