# MeTube Manager

Watch RSS feeds (e.g. YouTube channels) and send new videos to your [MeTube](https://github.com/alexta69/metube) instance for download.

- Configure your MeTube URL and download quality (format is sent as MP4).
- Add RSS feed URLs; channel names are fetched and shown in settings.
- Polls every hour and sends new video links to MeTube via its `/add` API.
- Tracks seen URLs so each video is only downloaded once.

Requires a running MeTube instance reachable from Home Assistant.
