# All-in-One Music Bot — Phase 1

A Dockerized Discord music bot starter built with discord.py, Wavelink, Lavalink v4, the official Lavalink YouTube source plugin, and SQLite.

## Included

- `/play` with YouTube Music search and supported URLs
- `/pause`, `/resume`, `/skip`, `/stop`, `/disconnect`
- `/queue`, `/nowplaying`, `/volume`, `/shuffle`
- Persistent player buttons
- Per-server default volume stored in SQLite
- Lavalink health check and Docker restart policies
- SoundCloud, Bandcamp, Twitch, Vimeo, HTTP streams, and YouTube source support

## Setup

1. Create a Discord application and bot in the Discord Developer Portal.
2. Enable the bot's `bot` and `applications.commands` OAuth scopes.
3. Invite it with Connect, Speak, View Channels, Send Messages, Embed Links, and Use Application Commands permissions.
4. Copy the environment template:

   ```bash
   cp .env.example .env
   ```

5. Set `DISCORD_TOKEN` and replace `LAVALINK_PASSWORD` with a strong value.
6. For instant command syncing during development, put your server ID in `TEST_GUILD_ID`. Leave it blank for global commands.
7. Start the stack:

   ```bash
   docker compose up -d --build
   ```

8. Watch startup logs:

   ```bash
   docker compose logs -f bot lavalink
   ```

## Updating

```bash
docker compose pull
docker compose up -d --build
```

## Architecture note

Lavalink's current dedicated YouTube source plugin is used instead of yt-dlp. The bot's command layer only asks Wavelink/Lavalink to resolve tracks, which keeps playback sources replaceable.

## Current Phase 1 limits

This is a runnable foundation rather than the complete long-term feature set. Search-result pickers, vote skip, DJ roles, loop modes, saved queues, favorites, playlists, autoplay, lyrics, filters UI, and the dashboard are planned next.

## Troubleshooting

- Commands missing: set `TEST_GUILD_ID`, rebuild, and check bot logs.
- Lavalink authentication failure: ensure the same `LAVALINK_PASSWORD` is used by both services.
- YouTube failure: update the configured YouTube plugin version in `lavalink/application.yml` and recreate the Lavalink container.
- No audio: verify the bot has Connect and Speak permissions and that the host can reach Discord voice services.
