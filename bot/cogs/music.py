from __future__ import annotations

import asyncio
import logging
import math
import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp

from bot.services.settings import GuildSettingsService
from bot.views import PlayerControls

log = logging.getLogger("musicbot.music")

YTDLP_OPTIONS: dict[str, Any] = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": False,
    "extract_flat": "in_playlist",
    "default_search": "ytsearch1",
    "skip_download": True,
    "source_address": "0.0.0.0",
}
STREAM_OPTIONS: dict[str, Any] = {
    **YTDLP_OPTIONS,
    "noplaylist": True,
    "extract_flat": False,
}
FFMPEG_BEFORE = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
FFMPEG_OPTIONS = "-vn"


def format_seconds(value: int | float | None) -> str:
    seconds = max(0, int(value or 0))
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"


@dataclass(slots=True)
class Track:
    title: str
    webpage_url: str
    duration: int = 0
    uploader: str = "Unknown"
    thumbnail: str | None = None
    requester_id: int | None = None
    requester_name: str | None = None


@dataclass
class GuildPlayer:
    queue: deque[Track] = field(default_factory=deque)
    current: Track | None = None
    volume: int = 75
    started_at: float | None = None
    paused_at: float | None = None
    paused_total: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def position(self) -> int:
        if self.started_at is None:
            return 0
        end = self.paused_at if self.paused_at is not None else time.monotonic()
        return max(0, int(end - self.started_at - self.paused_total))


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot, settings: GuildSettingsService) -> None:
        self.bot = bot
        self.settings = settings
        self.players: dict[int, GuildPlayer] = {}

    def state(self, guild_id: int) -> GuildPlayer:
        return self.players.setdefault(guild_id, GuildPlayer())

    async def extract_tracks(self, query: str, requester: discord.Member | discord.User) -> tuple[list[Track], str | None]:
        loop = asyncio.get_running_loop()

        def extract() -> dict[str, Any]:
            with yt_dlp.YoutubeDL(YTDLP_OPTIONS) as ydl:
                return ydl.extract_info(query, download=False)

        info = await loop.run_in_executor(None, extract)
        entries = info.get("entries") if info else None
        playlist_name: str | None = None
        raw_items: list[dict[str, Any]]
        if entries is not None:
            raw_items = [entry for entry in entries if entry]
            if info.get("_type") == "playlist" and len(raw_items) > 1:
                playlist_name = info.get("title")
            else:
                raw_items = raw_items[:1]
        else:
            raw_items = [info]

        tracks: list[Track] = []
        for item in raw_items:
            url = item.get("webpage_url") or item.get("original_url") or item.get("url")
            if not url:
                continue
            if item.get("ie_key") == "Youtube" and not str(url).startswith("http"):
                url = f"https://www.youtube.com/watch?v={url}"
            tracks.append(
                Track(
                    title=item.get("title") or "Unknown title",
                    webpage_url=str(url),
                    duration=int(item.get("duration") or 0),
                    uploader=item.get("uploader") or item.get("channel") or "Unknown",
                    thumbnail=item.get("thumbnail"),
                    requester_id=requester.id,
                    requester_name=requester.display_name,
                )
            )
        return tracks, playlist_name

    async def resolve_stream(self, track: Track) -> tuple[str, dict[str, str]]:
        loop = asyncio.get_running_loop()

        def extract() -> dict[str, Any]:
            with yt_dlp.YoutubeDL(STREAM_OPTIONS) as ydl:
                return ydl.extract_info(track.webpage_url, download=False)

        info = await loop.run_in_executor(None, extract)
        stream_url = info.get("url")
        if not stream_url:
            raise RuntimeError("yt-dlp did not return an audio stream URL")
        headers = {str(k): str(v) for k, v in (info.get("http_headers") or {}).items()}
        track.title = info.get("title") or track.title
        track.duration = int(info.get("duration") or track.duration)
        track.uploader = info.get("uploader") or info.get("channel") or track.uploader
        track.thumbnail = info.get("thumbnail") or track.thumbnail
        track.webpage_url = info.get("webpage_url") or track.webpage_url
        return str(stream_url), headers

    async def ensure_voice(self, interaction: discord.Interaction, deferred: bool = False) -> discord.VoiceClient | None:
        send = interaction.followup.send if deferred else interaction.response.send_message
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await send("This command can only be used in a server.", ephemeral=True)
            return None
        channel = interaction.user.voice.channel if interaction.user.voice else None
        if channel is None:
            await send("Join a voice channel first.", ephemeral=True)
            return None
        voice = interaction.guild.voice_client
        if voice:
            if voice.channel != channel:
                await send("You must be in my voice channel.", ephemeral=True)
                return None
            return voice
        try:
            voice = await channel.connect(self_deaf=True)
        except Exception:
            log.exception("Failed to connect to voice in guild %s", interaction.guild.id)
            await send("I could not connect to that voice channel. Check my Connect and Speak permissions.", ephemeral=True)
            return None
        guild_settings = await self.settings.get(interaction.guild.id)
        self.state(interaction.guild.id).volume = guild_settings.default_volume
        return voice

    async def play_next(self, guild: discord.Guild) -> None:
        state = self.state(guild.id)
        async with state.lock:
            voice = guild.voice_client
            if not isinstance(voice, discord.VoiceClient) or not voice.is_connected() or voice.is_playing() or voice.is_paused():
                return
            if not state.queue:
                state.current = None
                state.started_at = None
                return
            track = state.queue.popleft()
            state.current = track
            state.started_at = time.monotonic()
            state.paused_at = None
            state.paused_total = 0.0
            try:
                stream_url, headers = await self.resolve_stream(track)
                header_args = "".join(f"{k}: {v}\\r\\n" for k, v in headers.items())
                before = FFMPEG_BEFORE + (f' -headers "{header_args}"' if header_args else "")
                source = discord.FFmpegPCMAudio(stream_url, before_options=before, options=FFMPEG_OPTIONS)
                audio = discord.PCMVolumeTransformer(source, volume=state.volume / 100)

                def after(error: Exception | None) -> None:
                    if error:
                        log.error("FFmpeg playback error in guild %s: %s", guild.id, error)
                    future = asyncio.run_coroutine_threadsafe(self._after_track(guild, error), self.bot.loop)
                    try:
                        future.result()
                    except Exception:
                        log.exception("Failed to advance queue in guild %s", guild.id)

                voice.play(audio, after=after)
                log.info("Started track %r in guild %s", track.title, guild.id)
            except Exception:
                log.exception("Failed to resolve or start %r in guild %s", track.title, guild.id)
                state.current = None
                state.started_at = None
                asyncio.create_task(self.play_next(guild))

    async def _after_track(self, guild: discord.Guild, error: Exception | None) -> None:
        state = self.state(guild.id)
        state.current = None
        state.started_at = None
        state.paused_at = None
        state.paused_total = 0.0
        await self.play_next(guild)

    @app_commands.command(description="Play a song, playlist, URL, or search query.")
    @app_commands.describe(query="Song name or supported URL")
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer(thinking=True)
        voice = await self.ensure_voice(interaction, deferred=True)
        if not voice or not interaction.guild:
            return
        try:
            tracks, playlist_name = await self.extract_tracks(query, interaction.user)
        except Exception as exc:
            log.exception("yt-dlp search failed for %r", query)
            await interaction.followup.send(f"Search failed: `{type(exc).__name__}`. Check the bot logs for details.", ephemeral=True)
            return
        if not tracks:
            await interaction.followup.send("No matching tracks were found.", ephemeral=True)
            return
        state = self.state(interaction.guild.id)
        state.queue.extend(tracks)
        if not voice.is_playing() and not voice.is_paused() and state.current is None:
            await self.play_next(interaction.guild)
        first = tracks[0]
        text = f"Queued **{first.title}**" if playlist_name is None else f"Queued **{len(tracks)} tracks** from **{playlist_name}**"
        await interaction.followup.send(text, view=PlayerControls())

    async def toggle_pause(self, interaction: discord.Interaction) -> None:
        voice = interaction.guild.voice_client if interaction.guild else None
        state = self.state(interaction.guild.id) if interaction.guild else None
        if not isinstance(voice, discord.VoiceClient) or state is None:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        if voice.is_paused():
            voice.resume()
            if state.paused_at is not None:
                state.paused_total += time.monotonic() - state.paused_at
                state.paused_at = None
            await interaction.response.send_message("Resumed.", ephemeral=True)
        elif voice.is_playing():
            voice.pause()
            state.paused_at = time.monotonic()
            await interaction.response.send_message("Paused.", ephemeral=True)
        else:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)

    @app_commands.command(description="Pause playback.")
    async def pause(self, interaction: discord.Interaction) -> None:
        voice = interaction.guild.voice_client if interaction.guild else None
        state = self.state(interaction.guild.id) if interaction.guild else None
        if not isinstance(voice, discord.VoiceClient) or not voice.is_playing() or state is None:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        voice.pause()
        state.paused_at = time.monotonic()
        await interaction.response.send_message("Paused.")

    @app_commands.command(description="Resume playback.")
    async def resume(self, interaction: discord.Interaction) -> None:
        voice = interaction.guild.voice_client if interaction.guild else None
        state = self.state(interaction.guild.id) if interaction.guild else None
        if not isinstance(voice, discord.VoiceClient) or not voice.is_paused() or state is None:
            await interaction.response.send_message("Playback is not paused.", ephemeral=True)
            return
        voice.resume()
        if state.paused_at is not None:
            state.paused_total += time.monotonic() - state.paused_at
            state.paused_at = None
        await interaction.response.send_message("Resumed.")

    async def skip_playback(self, interaction: discord.Interaction) -> None:
        voice = interaction.guild.voice_client if interaction.guild else None
        if not isinstance(voice, discord.VoiceClient) or not (voice.is_playing() or voice.is_paused()):
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        voice.stop()
        await interaction.response.send_message("Skipped.", ephemeral=True)

    @app_commands.command(description="Skip the current track.")
    async def skip(self, interaction: discord.Interaction) -> None:
        await self.skip_playback(interaction)

    async def stop_playback(self, interaction: discord.Interaction) -> None:
        voice = interaction.guild.voice_client if interaction.guild else None
        if not interaction.guild or not isinstance(voice, discord.VoiceClient):
            await interaction.response.send_message("I am not connected.", ephemeral=True)
            return
        state = self.state(interaction.guild.id)
        state.queue.clear()
        state.current = None
        if voice.is_playing() or voice.is_paused():
            voice.stop()
        await interaction.response.send_message("Stopped and cleared the queue.", ephemeral=True)

    @app_commands.command(description="Stop playback and clear the queue.")
    async def stop(self, interaction: discord.Interaction) -> None:
        await self.stop_playback(interaction)

    @app_commands.command(description="Show the current queue.")
    async def queue(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("The queue is empty.", ephemeral=True)
            return
        state = self.state(interaction.guild.id)
        lines: list[str] = []
        if state.current:
            lines.append(f"**Now:** {state.current.title} — `{format_seconds(state.position())}/{format_seconds(state.current.duration)}`")
        for index, track in enumerate(list(state.queue)[:10], start=1):
            lines.append(f"`{index}.` {track.title} — `{format_seconds(track.duration)}`")
        if len(state.queue) > 10:
            lines.append(f"…and {len(state.queue) - 10} more")
        await interaction.response.send_message("\n".join(lines) if lines else "The queue is empty.", view=PlayerControls())

    @app_commands.command(description="Show the currently playing track.")
    async def nowplaying(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        state = self.state(interaction.guild.id)
        track = state.current
        if not track:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        position = state.position()
        ratio = 0 if track.duration <= 0 else min(1, position / track.duration)
        filled = math.floor(ratio * 16)
        progress = "━" * filled + "●" + "─" * (16 - filled)
        embed = discord.Embed(title=track.title, url=track.webpage_url, description=f"`{format_seconds(position)}` {progress} `{format_seconds(track.duration)}`")
        embed.add_field(name="Author", value=track.uploader)
        embed.add_field(name="Volume", value=f"{state.volume}%")
        if track.requester_name:
            embed.add_field(name="Requested by", value=track.requester_name)
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
        await interaction.response.send_message(embed=embed, view=PlayerControls())

    @app_commands.command(description="Set playback volume from 0 to 150.")
    async def volume(self, interaction: discord.Interaction, level: app_commands.Range[int, 0, 150]) -> None:
        if not interaction.guild:
            await interaction.response.send_message("I am not connected.", ephemeral=True)
            return
        state = self.state(interaction.guild.id)
        state.volume = level
        voice = interaction.guild.voice_client
        if isinstance(voice, discord.VoiceClient) and isinstance(voice.source, discord.PCMVolumeTransformer):
            voice.source.volume = level / 100
        await interaction.response.send_message(f"Volume set to **{level}%**.")

    @app_commands.command(description="Shuffle the queue.")
    async def shuffle(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("There are not enough queued tracks to shuffle.", ephemeral=True)
            return
        state = self.state(interaction.guild.id)
        if len(state.queue) < 2:
            await interaction.response.send_message("There are not enough queued tracks to shuffle.", ephemeral=True)
            return
        items = list(state.queue)
        random.shuffle(items)
        state.queue = deque(items)
        await interaction.response.send_message("Queue shuffled.")

    @app_commands.command(description="Disconnect the bot and clear the queue.")
    async def disconnect(self, interaction: discord.Interaction) -> None:
        voice = interaction.guild.voice_client if interaction.guild else None
        if not interaction.guild or not isinstance(voice, discord.VoiceClient):
            await interaction.response.send_message("I am not connected.", ephemeral=True)
            return
        state = self.state(interaction.guild.id)
        state.queue.clear()
        state.current = None
        await voice.disconnect(force=True)
        await interaction.response.send_message("Disconnected.")

    async def shutdown(self) -> None:
        for voice in list(self.bot.voice_clients):
            try:
                await voice.disconnect(force=True)
            except Exception:
                log.exception("Failed to disconnect voice client during shutdown")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot, bot.guild_settings))  # type: ignore[attr-defined]
