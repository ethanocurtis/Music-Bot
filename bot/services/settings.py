from __future__ import annotations

from sqlalchemy import select

from bot.db.models import GuildSettings
from bot.db.session import Database


class GuildSettingsService:
    def __init__(self, database: Database, fallback_volume: int) -> None:
        self.database = database
        self.fallback_volume = fallback_volume

    async def get(self, guild_id: int) -> GuildSettings:
        async with self.database.sessions() as session:
            settings = await session.scalar(select(GuildSettings).where(GuildSettings.guild_id == guild_id))
            if settings is None:
                settings = GuildSettings(guild_id=guild_id, default_volume=self.fallback_volume)
                session.add(settings)
                await session.commit()
            return settings

    async def set_volume(self, guild_id: int, volume: int) -> GuildSettings:
        async with self.database.sessions() as session:
            settings = await session.get(GuildSettings, guild_id)
            if settings is None:
                settings = GuildSettings(guild_id=guild_id, default_volume=volume)
                session.add(settings)
            else:
                settings.default_volume = volume
            await session.commit()
            await session.refresh(settings)
            return settings
