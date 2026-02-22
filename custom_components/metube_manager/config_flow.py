"""Config flow for MeTube Manager."""

from __future__ import annotations

import re
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_BACKLOG_PLAYLIST_URL,
    CONF_CHANNEL_ID,
    CONF_CHANNEL_NAME,
    CONF_FEED_NAME,
    CONF_FEED_URL,
    CONF_FETCH_BACKLOG,
    CONF_METUBE_URL,
    CONF_QUALITY,
    CONF_RSS_FEEDS,
    DEFAULT_QUALITY,
    DOMAIN,
    QUALITY_OPTIONS,
    YOUTUBE_FEED_ALL,
    YOUTUBE_FEED_VIDEOS,
    YOUTUBE_FEED_SHORTS,
    YOUTUBE_FEED_LIVE,
    YOUTUBE_FEED_TYPES,
)


def _normalize_url(url: str) -> str:
    """Strip trailing slash and ensure scheme."""
    url = (url or "").strip()
    if url and not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url.rstrip("/")


def _normalize_channel_name(s: str) -> str:
    """Strip and collapse multiple spaces so channel names don't get extra spaces."""
    return " ".join((s or "").strip().split())


def _validate_metube_url(url: str) -> bool:
    """Validate MeTube base URL."""
    try:
        normalized = _normalize_url(url)
        if not normalized:
            return False
        # Basic URL check
        return bool(re.match(r"^https?://[^/]+", normalized))
    except Exception:
        return False


def _youtube_feed_url(channel_id: str, feed_type: str) -> str:
    """Build YouTube RSS feed URL from channel_id and feed type (all/videos/shorts/live)."""
    feed_type = (feed_type or YOUTUBE_FEED_ALL).lower().strip()
    if feed_type not in YOUTUBE_FEED_TYPES:
        feed_type = YOUTUBE_FEED_ALL
    if feed_type == YOUTUBE_FEED_ALL:
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    # Playlist IDs: Videos=UULF, Shorts=UUSH, Live=UULV + channel_id without leading "UC"
    prefix = {
        YOUTUBE_FEED_VIDEOS: "UULF",
        YOUTUBE_FEED_SHORTS: "UUSH",
        YOUTUBE_FEED_LIVE: "UULV",
    }.get(feed_type, "UULF")
    playlist_id = prefix + channel_id[2:] if len(channel_id) > 2 else channel_id
    return f"https://www.youtube.com/feeds/videos.xml?playlist_id={playlist_id}"


def _youtube_backlog_playlist_url(channel_id: str, feed_type: str) -> str:
    """Generate YouTube backlog playlist URL from channel_id and feed type (for backlog checkbox)."""
    feed_type = (feed_type or YOUTUBE_FEED_ALL).lower().strip()
    if feed_type not in YOUTUBE_FEED_TYPES:
        feed_type = YOUTUBE_FEED_ALL
    # All = uploads playlist UU+channel_id[2:]; Videos/Shorts/Live = same as feed playlist
    if feed_type == YOUTUBE_FEED_ALL:
        prefix = "UU"
    else:
        prefix = {
            YOUTUBE_FEED_VIDEOS: "UULF",
            YOUTUBE_FEED_SHORTS: "UUSH",
            YOUTUBE_FEED_LIVE: "UULV",
        }.get(feed_type, "UULF")
    playlist_id = prefix + channel_id[2:] if len(channel_id) > 2 else channel_id
    return f"https://www.youtube.com/playlist?list={playlist_id}"


def _is_backlog_checkbox(val: str) -> bool:
    """True if the third column is a backlog checkbox (not a custom URL)."""
    v = (val or "").strip().lower()
    return v in ("backlog", "yes", "1", "true", "on")


def _is_youtube_feed_type(s: str) -> bool:
    """True if s is a known YouTube feed type (All, Videos, Shorts, Live)."""
    return (s or "").strip().lower() in YOUTUBE_FEED_TYPES


def _looks_like_youtube_channel(s: str) -> bool:
    """True if s looks like a YouTube channel reference (URL or @handle)."""
    s = (s or "").strip()
    if not s:
        return False
    if s.startswith("@"):
        return True
    s_lower = s.lower()
    return (
        "youtube.com/channel/" in s_lower
        or "youtube.com/@" in s_lower
        or "youtu.be/" in s_lower
    )


def _normalize_youtube_channel_input(s: str) -> str:
    """Turn handle or name into a URL for yt-dlp (channel/videos page for reliable extraction)."""
    s = (s or "").strip()
    if not s:
        return ""
    if s.startswith("http://") or s.startswith("https://"):
        url = s
        if "/videos" not in url and "/channel/" not in url and "/@" in url:
            url = url.rstrip("/") + "/videos"
        return url
    if s.startswith("@"):
        return f"https://www.youtube.com/{s}/videos"
    return f"https://www.youtube.com/@{s}/videos"


def _resolve_youtube_channel_sync(url: str) -> tuple[str, str] | None:
    """Resolve YouTube channel URL to (channel_id, channel_title). Runs in executor."""
    import yt_dlp
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False, process=False)
        if not info:
            return None
        channel_id = (
            info.get("channel_id")
            or info.get("id")
            or (info.get("uploader_id") if info.get("channel") else None)
        )
        if not channel_id and info.get("entries"):
            first = info["entries"][0]
            if isinstance(first, dict):
                channel_id = first.get("channel_id") or first.get("uploader_id")
        raw_title = (
            (info.get("channel") or info.get("uploader") or info.get("title") or "")
        ).strip()
        title = _normalize_channel_name(raw_title)
        if channel_id and len(channel_id) >= 2:
            return (str(channel_id), title or channel_id)
    except Exception:
        pass
    return None


async def _resolve_youtube_channel(hass: HomeAssistant, channel_input: str) -> tuple[str, str] | None:
    """Resolve YouTube channel URL or @handle to (channel_id, channel_title)."""
    url = _normalize_youtube_channel_input(channel_input)
    if not url:
        return None
    return await hass.async_add_executor_job(_resolve_youtube_channel_sync, url)


def _line_contains_url(line: str) -> bool:
    """True if the line contains an http(s) URL (we only allow channel names, not manual RSS)."""
    return "http://" in line or "https://" in line


def _parse_feeds_text_lines(raw: str) -> list[tuple[bool, str, str, str]]:
    """Parse lines into (is_youtube, channel_ref, feed_type, backlog). Only YouTube channel names allowed.
    Format: channel_name   or   channel_name | backlog   or   channel_name | feed_type | backlog
    Default feed type is Videos. Lines containing URLs are skipped (channel names only).
    """
    out: list[tuple[bool, str, str, str]] = []
    default_feed_type = YOUTUBE_FEED_VIDEOS
    for line in (raw or "").strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if _line_contains_url(line):
            continue
        parts = [p.strip() for p in line.split(" | ")]
        first = parts[0] if parts else ""
        second = parts[1] if len(parts) > 1 else ""
        third = " | ".join(parts[2:]).strip() if len(parts) > 2 else ""

        if not first:
            continue

        # 1 part: channel name only
        if len(parts) == 1:
            out.append((True, first, default_feed_type, ""))
            continue

        # 2 parts: channel | backlog  or  channel | feed_type
        if len(parts) == 2:
            if _is_youtube_feed_type(second):
                out.append((True, first, second, ""))
            elif _is_backlog_checkbox(second):
                out.append((True, first, default_feed_type, second))
            else:
                out.append((True, first, default_feed_type, ""))
            continue

        # 3+ parts: channel | feed_type | backlog
        if _is_youtube_feed_type(second):
            out.append((True, first, second, third))
        else:
            out.append((True, first, default_feed_type, third))
    return out


async def _parse_feeds_text_and_fetch_names(
    hass: HomeAssistant,
    raw: str,
    existing_url_to_name: dict[str, str] | None = None,
    existing_url_to_backlog: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Parse feed lines: YouTube channel names only (no backlog in text; backlog set by checkbox in UI).
    Resolves each channel to channel_id and builds feed URLs; backlog comes from existing or step 2."""
    existing_backlog = existing_url_to_backlog or {}
    lines = _parse_feeds_text_lines(raw)
    result: list[dict[str, Any]] = []
    for _is_youtube, part1, part2, _backlog_ignored in lines:
        resolved = await _resolve_youtube_channel(hass, part1)
        if not resolved:
            continue
        channel_id, channel_name = resolved
        feed_type = (part2 or YOUTUBE_FEED_VIDEOS).lower().strip()
        if feed_type not in YOUTUBE_FEED_TYPES:
            feed_type = YOUTUBE_FEED_VIDEOS
        rss_url = _youtube_feed_url(channel_id, feed_type)
        display_name = _normalize_channel_name(channel_name or part1)
        backlog_url = existing_backlog.get(rss_url, "")
        result.append({
            CONF_FEED_URL: rss_url,
            CONF_FEED_NAME: display_name,
            CONF_BACKLOG_PLAYLIST_URL: backlog_url,
            CONF_CHANNEL_ID: channel_id,
            "_feed_type": feed_type,
        })
    return result


async def _test_metube_connection(hass: HomeAssistant, base_url: str) -> bool:
    """Test that we can reach MeTube (optional: GET / or /add might return 405 which is ok)."""
    import aiohttp
    base_url = _normalize_url(base_url)
    try:
        async with aiohttp.ClientSession() as session:
            # MeTube might not have a root that returns 200; /add with GET may 405. Just check reachability.
            async with session.get(base_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                return resp.status in (200, 405)
    except Exception:
        return False


class MeTubeManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MeTube Manager."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "MeTubeManagerOptionsFlow":
        """Return the options flow."""
        return MeTubeManagerOptionsFlow(config_entry.entry_id)

    def _default_url_and_quality(self) -> tuple[str, str]:
        """Return (url, quality) from first existing MeTube Manager entry, or defaults."""
        entries = self.hass.config_entries.async_entries(DOMAIN)
        if not entries:
            return ("http://localhost:8081", DEFAULT_QUALITY)
        first = entries[0]
        opts = first.options or {}
        data = first.data or {}
        url = (opts.get(CONF_METUBE_URL) or data.get(CONF_METUBE_URL) or "").strip()
        if not url:
            url = "http://localhost:8081"
        quality = opts.get(CONF_QUALITY) or data.get(CONF_QUALITY) or DEFAULT_QUALITY
        if quality not in [v for v, _ in QUALITY_OPTIONS]:
            quality = DEFAULT_QUALITY
        return (url, quality)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step: one channel per integration. URL/quality default from first existing entry."""
        errors: dict[str, str] = {}
        default_url, default_quality = self._default_url_and_quality()
        if user_input is not None:
            url = _normalize_url(user_input.get(CONF_METUBE_URL, ""))
            if not _validate_metube_url(url):
                errors["base"] = "invalid_url"
            else:
                ok = await _test_metube_connection(self.hass, url)
                if not ok:
                    errors["base"] = "cannot_connect"
                else:
                    channel_name = (user_input.get(CONF_CHANNEL_NAME) or "").strip()
                    if not channel_name:
                        errors["base"] = "invalid_feed"
                    else:
                        resolved = await _resolve_youtube_channel(self.hass, channel_name)
                        if not resolved:
                            errors["base"] = "invalid_feed"
                        else:
                            channel_id, display_name = resolved
                            feed_type = YOUTUBE_FEED_VIDEOS
                            rss_url = _youtube_feed_url(channel_id, feed_type)
                            fetch_backlog = bool(user_input.get(CONF_FETCH_BACKLOG, False))
                            backlog_url = (
                                _youtube_backlog_playlist_url(channel_id, feed_type)
                                if fetch_backlog
                                else ""
                            )
                            name = _normalize_channel_name(display_name or channel_name)
                            feed = {
                                CONF_FEED_URL: rss_url,
                                CONF_FEED_NAME: name,
                                CONF_BACKLOG_PLAYLIST_URL: backlog_url,
                                CONF_CHANNEL_ID: channel_id,
                            }
                            quality = user_input.get(CONF_QUALITY, default_quality)
                            return self.async_create_entry(
                                title=name,
                                data={
                                    CONF_METUBE_URL: url,
                                    CONF_QUALITY: quality,
                                },
                                options={CONF_RSS_FEEDS: [feed]},
                            )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_METUBE_URL, default=default_url): str,
                vol.Required(CONF_QUALITY, default=default_quality): vol.In(
                    [v for v, _ in QUALITY_OPTIONS]
                ),
                vol.Required(CONF_CHANNEL_NAME, default=""): str,
                vol.Required(CONF_FETCH_BACKLOG, default=False): cv.boolean,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> FlowResult:
        """Handle import from configuration.yaml (optional)."""
        return await self.async_step_user(import_data)


class MeTubeManagerOptionsFlow(config_entries.OptionsFlow):
    """Handle MeTube Manager options."""

    def __init__(self, entry_id: str) -> None:
        """Initialize options flow. Store entry_id only (base class config_entry is read-only)."""
        self._entry_id = entry_id

    @property
    def _config_entry(self) -> config_entries.ConfigEntry | None:
        """Look up the config entry by id."""
        return self.hass.config_entries.async_get_entry(self._entry_id)

    def _current_single_feed(self) -> dict[str, Any] | None:
        """Return the single feed dict for this entry, or None."""
        entry = self._config_entry
        if not entry:
            return None
        feeds = entry.options.get(CONF_RSS_FEEDS) or entry.data.get(CONF_RSS_FEEDS) or []
        if not feeds or not isinstance(feeds[0], dict):
            return None
        return feeds[0]

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit this channel: MeTube URL, quality, channel name, fetch backlog."""
        entry = self._config_entry
        if not entry:
            return self.async_abort(reason="config_entry_not_found")
        errors: dict[str, str] = {}
        if user_input is not None:
            url = _normalize_url(user_input.get(CONF_METUBE_URL, ""))
            if not _validate_metube_url(url):
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._schema(user_input),
                    errors={"base": "invalid_url"},
                )
            ok = await _test_metube_connection(self.hass, url)
            if not ok:
                pass
            channel_name = (user_input.get(CONF_CHANNEL_NAME) or "").strip()
            if not channel_name:
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._schema(user_input),
                    errors={"base": "invalid_feed"},
                )
            resolved = await _resolve_youtube_channel(self.hass, channel_name)
            if not resolved:
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._schema(user_input),
                    errors={"base": "invalid_feed"},
                )
            channel_id, display_name = resolved
            feed_type = YOUTUBE_FEED_VIDEOS
            rss_url = _youtube_feed_url(channel_id, feed_type)
            fetch_backlog = bool(user_input.get(CONF_FETCH_BACKLOG, False))
            backlog_url = (
                _youtube_backlog_playlist_url(channel_id, feed_type) if fetch_backlog else ""
            )
            name = _normalize_channel_name(display_name or channel_name)
            feed = {
                CONF_FEED_URL: rss_url,
                CONF_FEED_NAME: name,
                CONF_BACKLOG_PLAYLIST_URL: backlog_url,
                CONF_CHANNEL_ID: channel_id,
            }
            quality = user_input.get(CONF_QUALITY, DEFAULT_QUALITY)
            return self.async_create_entry(
                title=name,
                data={
                    CONF_METUBE_URL: url,
                    CONF_QUALITY: quality,
                    CONF_RSS_FEEDS: [feed],
                },
            )

        return self.async_show_form(
            step_id="init",
            data_schema=self._schema(),
        )

    def _schema(self, user_input: dict[str, Any] | None = None) -> vol.Schema:
        """Build options schema: URL, quality, channel name, fetch backlog (one channel per entry)."""
        entry = self._config_entry
        if not entry:
            url, quality = "http://localhost:8081", DEFAULT_QUALITY
            channel_name, fetch_backlog = "", False
        else:
            data = entry.data or {}
            options = entry.options or {}
            url = (options.get(CONF_METUBE_URL) or data.get(CONF_METUBE_URL) or "").strip()
            quality = options.get(CONF_QUALITY) or data.get(CONF_QUALITY) or DEFAULT_QUALITY
            feed = self._current_single_feed()
            if feed:
                channel_name = _normalize_channel_name(
                    feed.get(CONF_FEED_NAME) or feed.get("name") or ""
                )
                fetch_backlog = bool(
                    (feed.get(CONF_BACKLOG_PLAYLIST_URL) or feed.get("backlog_playlist_url") or "").strip()
                )
            else:
                channel_name, fetch_backlog = "", False
        if user_input:
            url = (user_input.get(CONF_METUBE_URL) or url or "").strip()
            quality = user_input.get(CONF_QUALITY) or quality
            channel_name = (user_input.get(CONF_CHANNEL_NAME) or channel_name or "").strip()
            fetch_backlog = bool(user_input.get(CONF_FETCH_BACKLOG, fetch_backlog))
        quality_values = [v for v, _ in QUALITY_OPTIONS]
        if quality not in quality_values:
            quality = DEFAULT_QUALITY
        return vol.Schema(
            {
                vol.Required(CONF_METUBE_URL, default=url or "http://localhost:8081"): str,
                vol.Required(CONF_QUALITY, default=quality): vol.In(quality_values),
                vol.Required(CONF_CHANNEL_NAME, default=channel_name): str,
                vol.Required(CONF_FETCH_BACKLOG, default=fetch_backlog): cv.boolean,
            }
        )
