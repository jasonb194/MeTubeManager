# MeTube Manager

A **Home Assistant** custom integration that watches RSS feeds and sends new videos to your [MeTube](https://github.com/alexta69/metube) instance for download.

## Features

- **MeTube connection**: Configure your MeTube base URL and download quality (e.g. `best`).
- **RSS feeds**: Add one or more RSS feed URLs (e.g. YouTube channel feeds). One URL per line in settings.
- **Hourly check**: Every hour the integration fetches all feeds, finds new video links, and sends them to MeTube via its `/add` API.
- **Seen tracking**: Already-seen video URLs are stored so each video is only sent to MeTube once.

## Installation

1. Copy the `custom_components/metube_manager` folder into your Home Assistant `custom_components` directory (e.g. `config/custom_components/metube_manager`).
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and search for **MeTube Manager**.
4. Enter your MeTube base URL (e.g. `http://metube.local:8081` or `https://metube.example.com`) and quality (default `best`).
5. On the next step, add RSS feed URLs (one per line). You can leave this empty and add feeds later via the integration’s **Configure**.
6. Finish the setup.

## Configuration

- **MeTube base URL**: Full URL to your MeTube instance (no trailing slash). Must be reachable from Home Assistant.
- **Download quality**: Value sent to MeTube as `quality` (e.g. `best`, `worst`, `bestvideo`).
- **RSS feed URLs**: One feed URL per line. Typical examples:
  - YouTube channel feed:  
    `https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID`
  - Or with handle:  
    `https://www.youtube.com/feeds/videos.xml?channel_id=UC...` (get channel ID from the channel’s “About” page or an RSS app).

After setup you can change the URL, quality, and list of feeds via the integration’s **Configure** (options).

## How it works

1. Every **hour** the integration fetches each configured RSS feed.
2. It parses the feed and collects every item `link` (video URL).
3. URLs that have not been seen before are sent to MeTube with `POST /add` and `{"url": "<link>", "quality": "<your quality>"}`.
4. Seen URLs are stored locally so they are not sent again.

## Requirements

- Home Assistant (tested on recent versions).
- MeTube instance (e.g. [alexta69/metube](https://github.com/alexta69/metube)) with its HTTP API reachable from Home Assistant.
- Dependencies (installed automatically): `feedparser`, `aiohttp`.

## License

MIT
