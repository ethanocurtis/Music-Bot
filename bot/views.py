from __future__ import annotations

import discord
import wavelink


class PlayerControls(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    async def _player(self, interaction: discord.Interaction) -> wavelink.Player | None:
        if not interaction.guild or not interaction.guild.voice_client:
            await interaction.response.send_message("Nothing is currently playing.", ephemeral=True)
            return None
        return interaction.guild.voice_client  # type: ignore[return-value]

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.primary, custom_id="music:pause")
    async def pause(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        player = await self._player(interaction)
        if not player:
            return
        await player.pause(not player.paused)
        await interaction.response.send_message("Playback toggled.", ephemeral=True)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="music:skip")
    async def skip(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        player = await self._player(interaction)
        if not player:
            return
        await player.skip(force=True)
        await interaction.response.send_message("Skipped.", ephemeral=True)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, custom_id="music:stop")
    async def stop(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        player = await self._player(interaction)
        if not player:
            return
        player.queue.clear()
        await player.stop(force=True)
        await interaction.response.send_message("Stopped and cleared the queue.", ephemeral=True)
