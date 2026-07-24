from __future__ import annotations

import discord


class PlayerControls(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    async def _music(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Music")
        if cog is None:
            await interaction.response.send_message("The music system is unavailable.", ephemeral=True)
        return cog

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.primary, custom_id="music:pause")
    async def pause(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        cog = await self._music(interaction)
        if cog:
            await cog.toggle_pause(interaction)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="music:skip")
    async def skip(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        cog = await self._music(interaction)
        if cog:
            await cog.skip_playback(interaction)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, custom_id="music:stop")
    async def stop(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        cog = await self._music(interaction)
        if cog:
            await cog.stop_playback(interaction)
