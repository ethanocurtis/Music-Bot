# All-in-One Music Bot — yt-dlp Edition

This build uses `discord.py`, `yt-dlp`, and FFmpeg directly. Lavalink and its YouTube plugin are no longer required.

## Features

- `/play` accepts a search, track URL, or playlist URL
- Queue, pause, resume, skip, stop, shuffle, volume, now-playing, and disconnect commands
- Persistent player buttons
- SQLite server settings
- Docker deployment

## Install / upgrade

1. Keep your existing `.env`. The old `LAVALINK_*` values may be removed; they are ignored.
2. Replace the project files with this package.
3. Rebuild from scratch so FFmpeg, PyNaCl, the current Discord voice dependencies, and yt-dlp are installed:

```bash
docker compose down --remove-orphans
docker compose build --no-cache
docker compose up -d
docker compose logs -f bot
```

The former Lavalink container is removed by `--remove-orphans`.

## Environment

Copy `.env.example` to `.env` and set at least:

```env
DISCORD_TOKEN=your_bot_token
TEST_GUILD_ID=your_test_server_id
```

`TEST_GUILD_ID` is optional, but makes slash-command updates appear immediately in one server.

## Notes

The bot intentionally joins self-deafened. That only prevents it from receiving user audio and does not block playback.

YouTube changes frequently. Rebuilding the image updates `yt-dlp` to the version allowed by `requirements.txt`.
