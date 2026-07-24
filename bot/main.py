from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from .config import Settings
from .db.session import Database
from .services.settings import GuildSettingsService
from .views import PlayerControls

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("musicbot")


class MusicBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.voice_states = True
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.settings = settings
        self.database = Database(settings.database_url)
        self.guild_settings = GuildSettingsService(self.database, settings.default_volume)

    async def setup_hook(self) -> None:
        await self.database.initialize()
        await self.load_extension("bot.cogs.music")
        await self.load_extension("bot.cogs.admin")
        self.add_view(PlayerControls())
        if self.settings.test_guild_id:
            guild = discord.Object(id=self.settings.test_guild_id)

            # Keep development commands guild-only. Copy the registered global
            # definitions to the test guild, then remove any old global command
            # registrations so Discord does not display every command twice.
            self.tree.copy_global_to(guild=guild)
            self.tree.clear_commands(guild=None)
            await self.tree.sync()

            synced = await self.tree.sync(guild=guild)
            log.info("Synced %s guild-only commands to test guild %s", len(synced), guild.id)
        else:
            synced = await self.tree.sync()
            log.info("Synced %s global commands", len(synced))

    async def close(self) -> None:
        cog = self.get_cog("Music")
        if cog and hasattr(cog, "shutdown"):
            await cog.shutdown()
        await self.database.close()
        await super().close()

    async def on_ready(self) -> None:
        log.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "unknown")


async def main() -> None:
    settings = Settings.from_env()
    bot = MusicBot(settings)
    async with bot:
        await bot.start(settings.discord_token)


def run() -> None:
    asyncio.run(main())
