# MeTube Manager

A **Home Assistant** custom integration that watches RSS feeds and sends new videos to your [MeTube](https://github.com/alexta69/metube) instance for download.

## Features

- **MeTube connection**: Configure your MeTube base URL and download quality (e.g. `best`).
- **YouTube channels**: Enter a channel URL or **@handle** (e.g. `@MrBeast`); the integration resolves the channel and lets you pick the feed type: **All**, **Videos**, **Shorts**, or **Live** (same idea as [YouTube RSS Feed Generator](https://www.newskeeper.io/tools/youtube-rss)). No need to look up RSS URLs yourself.
- **Manual RSS**: You can still paste a direct RSS URL (e.g. `Name | https://...videos.xml?channel_id=... | optional Backlog`).
- **Optional backlog**: Add a YouTube playlist URL to fetch all existing videos once via yt-dlp and send them to MeTube (one-time per feed).
- **Hourly check**: Every hour the integration fetches all RSS feeds, finds new video links, and sends them to MeTube via its `/add` API.
- **Seen tracking**: Already-seen video URLs are stored so each video is only sent to MeTube once.

## Installation

### Via HACS (recommended)

1. In HACS go to **Integrations** → **⋮** (top right) → **Custom repositories**.
2. Add repository URL: `https://github.com/YOUR_USERNAME/MeTubeManager` (use your actual GitHub repo URL).
3. Choose category **Integration** and add.
4. Search for **MeTube Manager** in HACS, install it, then restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration** and search for **MeTube Manager** to configure.

### Manual

1. Copy the `custom_components/metube_manager` folder into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and search for **MeTube Manager**.
4. Enter your MeTube base URL (e.g. `http://metube.local:8081` or `https://metube.example.com`) and quality (default `best`).
5. On the next step, add RSS feed URLs (one per line). You can leave this empty and add feeds later via the integration’s **Configure**.
6. Finish the setup.

## Configuration

- **MeTube base URL**: Full URL to your MeTube instance (no trailing slash). Must be reachable from Home Assistant.
- **Download quality**: Value sent to MeTube as `quality` (e.g. `best`, `worst`, `bestvideo`).
- **Feeds** (one per line). Two formats:
  - **YouTube**: `channel or @handle | All | optional Backlog URL` — use **All**, **Videos**, **Shorts**, or **Live** as the feed type. Examples:
    - `@MrBeast | Videos`
    - `https://youtube.com/@Channel | Shorts | https://youtube.com/playlist?list=PLxxx`
  - **Manual RSS**: `Name | RSS URL | optional Backlog URL` — paste any RSS feed URL. Channel name is fetched automatically if you leave the name empty.
  - **Backlog playlist URL** (optional): all videos in that playlist are fetched once via yt-dlp and sent to MeTube (one-time per feed).

After setup you can change the URL, quality, and list of feeds via the integration’s **Configure** (options).

## How it works

1. For any feed with an optional **backlog playlist URL** that hasn’t been processed yet: the integration uses **yt-dlp** (flat playlist, no download) to get all video URLs in that playlist, sends each to MeTube, then marks that feed’s backlog as done.
2. Every **hour** the integration fetches each configured RSS feed.
3. It parses the feed and collects every item `link` (video URL).
4. URLs that have not been seen before are sent to MeTube with `POST /add` and `{"url": "<link>", "quality": "<your quality>", "format": "mp4"}`.
5. Seen URLs are stored locally so each video is only sent once.

## Requirements

- Home Assistant (tested on recent versions).
- MeTube instance (e.g. [alexta69/metube](https://github.com/alexta69/metube)) with its HTTP API reachable from Home Assistant.
- Dependencies (installed automatically): `feedparser`, `aiohttp`, `yt-dlp` (for optional backlog playlists).

## License

MIT
