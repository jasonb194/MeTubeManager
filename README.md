# MeTube Manager

A **Home Assistant** custom integration that subscribes to **YouTube channels** and sends new videos to your [MeTube](https://github.com/alexta69/metube) instance for download.

## Features

- **One integration = one channel**: Add MeTube Manager once per YouTube channel. Each integration has its own MeTube URL, quality, channel name, and optional backlog.
- **Default URL/quality**: When adding another channel, the form pre-fills MeTube URL and quality from your first existing MeTube Manager (if any).
- **Hourly check**: Every hour the integration fetches each channel’s feed, finds new video links, and sends them to MeTube via its `/add` API.
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
5. You can leave feeds empty and add YouTube channels later via the integration’s **Configure**.
6. Finish the setup.

## Finding the integration

- **Add Integration**: Go to **Settings → Devices & services → Add integration** and search for **MeTube Manager** (with a space). If it doesn’t appear, the custom component may not be loaded: check that `custom_components/metube_manager` is in your config folder and restart Home Assistant.
- **After setup**: The integration appears as a card under **Settings → Devices & services**. Open the **Integrations** tab, then search or scroll for **MeTube Manager**. Click the card to see **Configure** and the **Status** sensor (and any feed sensors).

## Where is the UI?

- **Add a channel**: **Settings → Devices & services → Add integration** → **MeTube Manager**. Enter URL, quality, one channel name, and optionally **Fetch backlog**. Each card in the integration list is one channel.
- **Edit a channel**: Click that channel's **MeTube Manager** card (the one named after the channel), then **Configure**. Change URL, quality, channel name, or backlog.
- **MeTube Manager dashboard**: The integration automatically creates a **Lovelace dashboard** named **MeTube Manager** that shows your Status sensor and all feed sensors (videos sent, last fetched, etc.) in one place. Open it from the **sidebar** (MeTube Manager) or go to `/metube-manager`. If it doesn't appear right away, refresh the page or restart Home Assistant.
- **Feeds and status**: Open the integration card to see **Configure** and the **entity list**. You get one **Status** sensor (number of feeds) plus **one device per feed, each with its own sensor (metube_url, quality, rss_feed, backlog_feed in attributes)** (e.g. “MrBeast”) showing **videos sent** and attributes **last_fetched** and feed URL. Add or remove feeds in Configure (add a line to add, delete a line to remove); after you save, the integration reloads and the sensor list updates.

## Configuration

- **MeTube base URL**: Full URL to your MeTube instance (no trailing slash). Must be reachable from Home Assistant.
- **Download quality**: Value sent to MeTube as `quality` (e.g. `best`, `worst`, `bestvideo`).
- **Channels**: Enter **YouTube channel names only**, one per line (e.g. MrBeast or @MrBeast). The addon resolves each channel and uses the **Videos** feed; add **`| backlog`** to also fetch existing videos once. Do not enter RSS or website URLs. Examples: `MrBeast`, `MrBeast | backlog`. Device name = channel name; device shows channel_id, videos_downloaded, last_downloaded, backlog_enabled.

After setup you can change the URL, quality, and list of feeds via the integration’s **Configure** (options).

## How it works

1. For any channel with **Fetch backlog** checked: the backlog playlist URL is built from the channel. All backlog items are sent to MeTube once via yt-dlp.
2. Every **hour** the integration fetches each channel’s feed.
3. It parses the feed and collects every item `link` (video URL).
4. URLs that have not been seen before are sent to MeTube with `POST /add` and `{"url": "<link>", "quality": "<your quality>", "format": "mp4"}`.
5. Seen URLs are stored locally so each video is only sent once.

## Requirements

- Home Assistant (tested on recent versions).
- MeTube instance (e.g. [alexta69/metube](https://github.com/alexta69/metube)) with its HTTP API reachable from Home Assistant.
- Dependencies (installed automatically): `feedparser`, `aiohttp`, `yt-dlp` (for optional backlog playlists).

## License

MIT
