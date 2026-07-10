from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///data/alpha_digest.db"
    rss_feeds: str = ""
    llm_provider: str = "fallback"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o-mini"
    codex_model: str | None = None
    codex_command: str = "codex"
    codex_timeout_seconds: int = 180
    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None
    telegram_session_name: str = "data/alpha_digest_telegram"
    telegram_source_channels: str = ""
    telegram_ingest_lookback_hours: int = 24
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    discord_webhook_url: str | None = None
    signal_pairing_max_distance: int = 120

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def rss_feed_urls(self) -> list[str]:
        return [url.strip() for url in self.rss_feeds.split(",") if url.strip()]

    @property
    def telegram_source_channel_list(self) -> list[str]:
        return [channel.strip() for channel in self.telegram_source_channels.split(",") if channel.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
