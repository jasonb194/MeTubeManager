"""Constants for the MeTube Manager integration.

MeTube + YouTube RSS: poll feeds, send new videos to MeTube for download.
Config keys, quality options, feed types, and storage/scan settings.
"""

from datetime import timedelta

# -----------------------------------------------------------------------------
# Integration identity
# -----------------------------------------------------------------------------
DOMAIN = "metube_manager"

# -----------------------------------------------------------------------------
# Config entry keys (from config flow)
# -----------------------------------------------------------------------------
CONF_METUBE_URL = "metube_url"              # MeTube instance URL
CONF_RSS_FEEDS = "rss_feeds"                # List of feed configs (url, name, type, etc.)
CONF_FEED_URL = "url"
CONF_FEED_NAME = "name"
CONF_BACKLOG_PLAYLIST_URL = "backlog_playlist_url"
CONF_CHANNEL_ID = "channel_id"              # Resolved YouTube channel ID (for device display)
CONF_CHANNEL_NAME = "channel_name"          # User input: channel name or @handle
CONF_FETCH_BACKLOG = "fetch_backlog"        # Whether to fetch backlog on add
CONF_QUALITY = "quality"                    # yt-dlp quality (best, 1080p, etc.)

# -----------------------------------------------------------------------------
# Quality options (value, label) for MeTube / yt-dlp
# -----------------------------------------------------------------------------
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
DEFAULT_QUALITY = "best"

# -----------------------------------------------------------------------------
# YouTube RSS feed types (e.g. newskeeper-style URLs)
# -----------------------------------------------------------------------------
YOUTUBE_FEED_ALL = "all"
YOUTUBE_FEED_VIDEOS = "videos"
YOUTUBE_FEED_SHORTS = "shorts"
YOUTUBE_FEED_LIVE = "live"
YOUTUBE_FEED_TYPES = (YOUTUBE_FEED_ALL, YOUTUBE_FEED_VIDEOS, YOUTUBE_FEED_SHORTS, YOUTUBE_FEED_LIVE)

# -----------------------------------------------------------------------------
# Persistent storage and polling
# -----------------------------------------------------------------------------
STORAGE_KEY = "metube_manager_seen"
STORAGE_VERSION = 1
# How often to poll RSS feeds (used with async_track_time_interval)
SCAN_INTERVAL = timedelta(hours=1)
