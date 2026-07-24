from __future__ import annotations

import math

import discord
from discord import app_commands
from discord.ext import commands
import wavelink

from bot.services.settings import GuildSettingsService
from bot.views import PlayerControls


def format_ms(value: int) -> str:
    seconds = max(0, value // 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot, settings: GuildSettingsService) -> None:
        self.bot = bot
        self.settings = settings

    async def ensure_player(self, interaction: discord.Interaction) -> wavelink.Player | None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return None
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("Join a voice channel first.", ephemeral=True)
            return None
        existing = interaction.guild.voice_client
        if existing:
            player: wavelink.Player = existing  # type: ignore[assignment]
            if player.channel != interaction.user.voice.channel:
                await interaction.response.send_message("You must be in my voice channel.", ephemeral=True)
                return None
            return player
        player = await interaction.user.voice.channel.connect(cls=wavelink.Player, self_deaf=True)
        guild_settings = await self.settings.get(interaction.guild.id)
        await player.set_volume(guild_settings.default_volume)
        return player

    @app_commands.command(description="Play a song, playlist, URL, or search query.")
    @app_commands.describe(query="Song name or supported URL")
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer(thinking=True)
        player = await self.ensure_player_deferred(interaction)
        if not player:
            return
        search_query = query if query.startswith(("http://", "https://")) else f"ytmsearch:{query}"
        try:
            results = await wavelink.Playable.search(search_query)
        except Exception as exc:
            await interaction.followup.send(f"Search failed: `{type(exc).__name__}`", ephemeral=True)
            return
        if not results:
            await interaction.followup.send("No matching tracks were found.", ephemeral=True)
            return
        tracks = list(results.tracks) if isinstance(results, wavelink.Playlist) else list(results)
        if not tracks:
            await interaction.followup.send("That playlist did not contain playable tracks.", ephemeral=True)
            return
        for track in tracks:
            track.extras = {"requester_id": interaction.user.id, "requester_name": interaction.user.display_name}
        added = await player.queue.put_wait(tracks)
        if not player.playing:
            await player.play(player.queue.get())
        first = tracks[0]
        text = f"Queued **{first.title}**" if len(tracks) == 1 else f"Queued **{len(tracks)} tracks** from **{getattr(results, 'name', first.title)}**"
        await interaction.followup.send(text, view=PlayerControls())

    async def ensure_player_deferred(self, interaction: discord.Interaction) -> wavelink.Player | None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
            return None
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("Join a voice channel first.", ephemeral=True)
            return None
        if interaction.guild.voice_client:
            player: wavelink.Player = interaction.guild.voice_client  # type: ignore[assignment]
            if player.channel != interaction.user.voice.channel:
                await interaction.followup.send("You must be in my voice channel.", ephemeral=True)
                return None
            return player
        player = await interaction.user.voice.channel.connect(cls=wavelink.Player, self_deaf=True)
        guild_settings = await self.settings.get(interaction.guild.id)
        await player.set_volume(guild_settings.default_volume)
        return player

    @app_commands.command(description="Pause playback.")
    async def pause(self, interaction: discord.Interaction) -> None:
        player = interaction.guild.voice_client if interaction.guild else None
        if not isinstance(player, wavelink.Player) or not player.playing:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        await player.pause(True)
        await interaction.response.send_message("Paused.")

    @app_commands.command(description="Resume playback.")
    async def resume(self, interaction: discord.Interaction) -> None:
        player = interaction.guild.voice_client if interaction.guild else None
        if not isinstance(player, wavelink.Player) or not player.paused:
            await interaction.response.send_message("Playback is not paused.", ephemeral=True)
            return
        await player.pause(False)
        await interaction.response.send_message("Resumed.")

    @app_commands.command(description="Skip the current track.")
    async def skip(self, interaction: discord.Interaction) -> None:
        player = interaction.guild.voice_client if interaction.guild else None
        if not isinstance(player, wavelink.Player) or not player.current:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        await player.skip(force=True)
        await interaction.response.send_message("Skipped.")

    @app_commands.command(description="Stop playback and clear the queue.")
    async def stop(self, interaction: discord.Interaction) -> None:
        player = interaction.guild.voice_client if interaction.guild else None
        if not isinstance(player, wavelink.Player):
            await interaction.response.send_message("I am not connected.", ephemeral=True)
            return
        player.queue.clear()
        await player.stop(force=True)
        await interaction.response.send_message("Stopped and cleared the queue.")

    @app_commands.command(description="Show the current queue.")
    async def queue(self, interaction: discord.Interaction) -> None:
        player = interaction.guild.voice_client if interaction.guild else None
        if not isinstance(player, wavelink.Player):
            await interaction.response.send_message("The queue is empty.", ephemeral=True)
            return
        lines: list[str] = []
        if player.current:
            lines.append(f"**Now:** {player.current.title} — `{format_ms(player.position)}/{format_ms(player.current.length)}`")
        queued = list(player.queue)
        for index, track in enumerate(queued[:10], start=1):
            lines.append(f"`{index}.` {track.title} — `{format_ms(track.length)}`")
        if len(queued) > 10:
            lines.append(f"…and {len(queued) - 10} more")
        await interaction.response.send_message("\n".join(lines) if lines else "The queue is empty.", view=PlayerControls())

    @app_commands.command(description="Show the currently playing track.")
    async def nowplaying(self, interaction: discord.Interaction) -> None:
        player = interaction.guild.voice_client if interaction.guild else None
        if not isinstance(player, wavelink.Player) or not player.current:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        track = player.current
        ratio = 0 if track.length <= 0 else min(1, player.position / track.length)
        filled = math.floor(ratio * 16)
        progress = "━" * filled + "●" + "─" * (16 - filled)
        embed = discord.Embed(title=track.title, url=track.uri, description=f"`{format_ms(player.position)}` {progress} `{format_ms(track.length)}`")
        embed.add_field(name="Author", value=track.author or "Unknown")
        embed.add_field(name="Volume", value=f"{player.volume}%")
        if track.artwork:
            embed.set_thumbnail(url=track.artwork)
        await interaction.response.send_message(embed=embed, view=PlayerControls())

    @app_commands.command(description="Set playback volume from 0 to 150.")
    @app_commands.describe(level="Volume percentage")
    async def volume(self, interaction: discord.Interaction, level: app_commands.Range[int, 0, 150]) -> None:
        player = interaction.guild.voice_client if interaction.guild else None
        if not isinstance(player, wavelink.Player):
            await interaction.response.send_message("I am not connected.", ephemeral=True)
            return
        await player.set_volume(level)
        await interaction.response.send_message(f"Volume set to **{level}%**.")

    @app_commands.command(description="Shuffle the queue.")
    async def shuffle(self, interaction: discord.Interaction) -> None:
        player = interaction.guild.voice_client if interaction.guild else None
        if not isinstance(player, wavelink.Player) or len(player.queue) < 2:
            await interaction.response.send_message("There are not enough queued tracks to shuffle.", ephemeral=True)
            return
        player.queue.shuffle()
        await interaction.response.send_message("Queue shuffled.")

    @app_commands.command(description="Disconnect the bot and clear the queue.")
    async def disconnect(self, interaction: discord.Interaction) -> None:
        player = interaction.guild.voice_client if interaction.guild else None
        if not isinstance(player, wavelink.Player):
            await interaction.response.send_message("I am not connected.", ephemeral=True)
            return
        player.queue.clear()
        await player.disconnect()
        await interaction.response.send_message("Disconnected.")

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload) -> None:
        player = payload.player
        if player and not player.queue.is_empty:
            await player.play(player.queue.get())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot, bot.guild_settings))  # type: ignore[attr-defined]
