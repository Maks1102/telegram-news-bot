"""Конфигурация бота через .env (pydantic-settings)."""
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    bot_token: str
    chat_id: int

    # RSS-источники (через запятую)
    rss_feeds: str

    # Расписание еженедельной рассылки
    schedule_day: str = "mon"          # mon..sun или 0..6
    schedule_time: str = "09:00"       # HH:MM
    timezone: str = "Europe/Moscow"

    # Хранилище и дайджест
    database_path: str = "data/news.db"
    digest_size: int = 10
    retention_days: int = 90           # сколько дней хранить хэши статей

    # HTTP-запросы к RSS
    request_timeout: int = 15

    log_level: str = "INFO"

    @field_validator("rss_feeds")
    @classmethod
    def validate_feeds(cls, v: str) -> str:
        feeds = cls._split_feeds(v)
        if not feeds:
            raise ValueError("RSS_FEEDS не содержит ни одного валидного URL")
        for url in feeds:
            if not url.lower().startswith(("http://", "https://")):
                raise ValueError(f"Некорректный URL в RSS_FEEDS: {url!r}")
        return ",".join(feeds)

    @staticmethod
    def _split_feeds(v: str) -> list[str]:
        return [s.strip() for s in v.split(",") if s.strip()]

    @property
    def feed_list(self) -> list[str]:
        return self._split_feeds(self.rss_feeds)

    @field_validator("schedule_time")
    @classmethod
    def validate_time(cls, v: str) -> str:
        try:
            hour_s, minute_s = v.strip().split(":")
            hour, minute = int(hour_s), int(minute_s)
            assert 0 <= hour <= 23 and 0 <= minute <= 59
        except (ValueError, AssertionError):
            raise ValueError(f"SCHEDULE_TIME должен быть в формате HH:MM, получено: {v!r}")
        return f"{hour:02d}:{minute:02d}"

    @property
    def schedule_hour(self) -> int:
        return int(self.schedule_time.split(":")[0])

    @property
    def schedule_minute(self) -> int:
        return int(self.schedule_time.split(":")[1])

    @field_validator("schedule_day")
    @classmethod
    def validate_day(cls, v: str) -> str:
        allowed = {"mon", "tue", "wed", "thu", "fri", "sat", "sun",
                   "0", "1", "2", "3", "4", "5", "6"}
        day = v.strip().lower()
        if day not in allowed:
            raise ValueError(f"SCHEDULE_DAY должен быть одним из {sorted(allowed)}, получено: {v!r}")
        return day

    @field_validator("timezone")
    @classmethod
    def validate_tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError:
            raise ValueError(f"Неизвестная таймзона TIMEZONE: {v!r}")
        return v

    @field_validator("digest_size")
    @classmethod
    def validate_digest_size(cls, v: int) -> int:
        if not 1 <= v <= 30:
            raise ValueError("DIGEST_SIZE должен быть от 1 до 30")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
