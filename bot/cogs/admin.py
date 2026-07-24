from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(description="Configure this server's default music volume.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setupmusic(self, interaction: discord.Interaction, default_volume: app_commands.Range[int, 0, 150] = 75) -> None:
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        await self.bot.guild_settings.set_volume(interaction.guild.id, default_volume)  # type: ignore[attr-defined]
        await interaction.response.send_message(f"Default server volume set to **{default_volume}%**.", ephemeral=True)

    @setupmusic.error
    async def setupmusic_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("You need **Manage Server** to use this command.", ephemeral=True)
            return
        raise error


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Admin(bot))
