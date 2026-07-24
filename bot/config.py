from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int | None = None) -> int | None:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    return int(value)


@dataclass(frozen=True, slots=True)
class Settings:
    discord_token: str
    database_url: str
    default_volume: int
    inactivity_timeout_seconds: int
    test_guild_id: int | None

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token or token == "replace_me":
            raise RuntimeError("DISCORD_TOKEN is missing from .env")
        return cls(
            discord_token=token,
            database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:////app/data/musicbot.db"),
            default_volume=max(0, min(150, int(os.getenv("DEFAULT_VOLUME", "75")))),
            inactivity_timeout_seconds=max(60, int(os.getenv("INACTIVITY_TIMEOUT_SECONDS", "300"))),
            test_guild_id=_int("TEST_GUILD_ID"),
        )
