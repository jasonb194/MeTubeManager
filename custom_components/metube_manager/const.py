"""Constants for the MeTube Manager integration."""

from datetime import timedelta

DOMAIN = "metube_manager"
CONF_METUBE_URL = "metube_url"
CONF_RSS_FEEDS = "rss_feeds"
CONF_FEED_URL = "url"
CONF_FEED_NAME = "name"
CONF_BACKLOG_PLAYLIST_URL = "backlog_playlist_url"
CONF_QUALITY = "quality"
# Quality dropdown options (value, display label) for MeTube/yt-dlp
QUALITY_OPTIONS: list[tuple[str, str]] = [
    ("best", "Best"),
    ("2160p", "2160p"),
    ("1440p", "1440p"),
    ("1080p", "1080p"),
    ("720p", "720p"),
    ("480p", "480p"),
    ("360p", "360p"),
    ("240p", "240p"),
    ("worst", "Worst"),
]
# YouTube feed types (like https://www.newskeeper.io/tools/youtube-rss)
YOUTUBE_FEED_ALL = "all"
YOUTUBE_FEED_VIDEOS = "videos"
YOUTUBE_FEED_SHORTS = "shorts"
YOUTUBE_FEED_LIVE = "live"
YOUTUBE_FEED_TYPES = (YOUTUBE_FEED_ALL, YOUTUBE_FEED_VIDEOS, YOUTUBE_FEED_SHORTS, YOUTUBE_FEED_LIVE)
DEFAULT_QUALITY = "best"
STORAGE_KEY = "metube_manager_seen"
STORAGE_VERSION = 1
# Cron-style: interval for polling (used with async_track_time_interval)
SCAN_INTERVAL = timedelta(hours=1)
