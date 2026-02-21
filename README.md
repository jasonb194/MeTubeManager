# MeTube Manager

A **Home Assistant** custom integration that subscribes to **YouTube channels** and sends new videos to your [MeTube](https://github.com/alexta69/metube) instance for download.

## Features

- **One integration = one channel**: Add MeTube Manager once per YouTube channel. Each integration has its own MeTube URL, quality, channel name, and optional backlog.
- **Default URL/quality**: When adding another channel, the form pre-fills MeTube URL and quality from your first existing MeTube Manager (if any).
- **Hourly check**: Every hour the integration fetches each channel's feed, finds new video links, and sends them to MeTube via its `/add` API.
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
4. Enter **MeTube base URL** (e.g. `http://metube.local:8081`), **quality** (e.g. `best`), **one YouTube channel name** (e.g. `MrBeast` or `@MrBeast`), and optionally check **Fetch backlog**. Submit.
5. To add more channels, click **Add integration** again and add **MeTube Manager** (URL and quality will default from your first entry).

## Finding the integration

- **Add integration**: **Settings → Devices & services → Add integration** → search for **MeTube Manager**. If it does not appear, ensure `custom_components/metube_manager` is in your config folder and restart Home Assistant.
- **After setup**: Each channel appears as its own card (e.g. "MrBeast"). Click a card to see **Configure** and the sensor for that channel.

## Using the integration

- **Add a channel**: **Settings → Devices & services → Add integration** → **MeTube Manager**. Enter MeTube URL, quality, **one YouTube channel name** (e.g. `MrBeast`), and optionally check **Fetch backlog**. Submit. Each integration card = one channel.
- **Edit a channel**: Click that channel's card (e.g. "MrBeast"), then **Configure**. Change MeTube URL, quality, channel name, or **Fetch backlog** checkbox. Submit.
- **Remove a channel**: Click the channel's card → **⋮** (top right) → **Delete**.
- **Dashboard**: A **MeTube Manager** dashboard is created and shows all your channels. Open it from the **sidebar** or go to `/metube-manager`.

## Configuration

- **MeTube base URL**: Full URL to your MeTube instance (e.g. `http://metube.local:8081`), no trailing slash. When you add a second (or later) channel, this field is pre-filled from your first MeTube Manager entry.
- **Quality**: Value sent to MeTube (e.g. `best`, `worst`, `1080p`). Also pre-filled when adding more channels.
- **YouTube channel name**: One channel per integration. Enter the channel name or handle (e.g. `MrBeast` or `@MrBeast`). The integration resolves it and uses the channel's **Videos** feed. **You cannot enter RSS or other URLs—only YouTube channel names.**
- **Fetch backlog**: Check this to download existing videos from the channel once (via yt-dlp). After that, only new videos are sent on the hourly check.

To change any of these, open the integration card for that channel and click **Configure**.

## How it works

1. For any channel with **Fetch backlog** checked: the backlog playlist URL is built from the channel. All backlog items are sent to MeTube once via yt-dlp.
2. The first check runs right after setup; then every **hour** (at the top of the hour) the integration fetches each channel's feed.
3. It parses the feed and collects every item `link` (video URL).
4. URLs that have not been seen before are sent to MeTube with `POST /add` and `{"url": "<link>", "quality": "<your quality>", "format": "mp4"}`.
5. Seen URLs are stored locally so each video is only sent once.

## Icon

**HACS does not use `icon.png` from your repo.** Both HACS and Home Assistant load integration icons only from [brands.home-assistant.io](https://github.com/home-assistant/brands) (using the integration domain). So the icon will not show in HACS or in **Settings → Integrations** until it is in the brands repository.

To fix it:

1. Open the [Home Assistant brands repository](https://github.com/home-assistant/brands) and add a new folder `custom_integrations/metube_manager/`.
2. Add your **`icon.png`** (the one in the root of this repo is fine; it should be 256×256 PNG) as `custom_integrations/metube_manager/icon.png` in that repo.
3. Submit a pull request. Once it is merged, the icon will appear in both HACS and **Settings → Integrations**.

The repo also has `custom_components/metube_manager/icon.svg` as the source; you can keep `icon.png` in the repo root for reference.

## Requirements

- Home Assistant (tested on recent versions).
- MeTube instance (e.g. [alexta69/metube](https://github.com/alexta69/metube)) with its HTTP API reachable from Home Assistant.
- Dependencies (installed automatically): `feedparser`, `aiohttp`, `yt-dlp` (for optional backlog playlists).

## License

MIT
