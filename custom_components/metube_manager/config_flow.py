"""Config flow for MeTube Manager."""

from __future__ import annotations

import re
from typing import Any

import aiohttp
import feedparser
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_BACKLOG_PLAYLIST_URL,
    CONF_FEED_NAME,
    CONF_FEED_URL,
    CONF_METUBE_URL,
    CONF_QUALITY,
    CONF_RSS_FEEDS,
    DEFAULT_QUALITY,
    DOMAIN,
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


def _parse_rss_feeds(raw: str) -> list[str]:
    """Parse one URL per line into a list, skipping empty lines."""
    return [line.strip() for line in (raw or "").strip().splitlines() if line.strip()]


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
        title = (
            (info.get("channel") or info.get("uploader") or info.get("title") or "")
        ).strip()
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


def _feed_title_from_parsed(parsed: Any) -> str:
    """Extract channel/feed display name from parsed feed."""
    try:
        feed = getattr(parsed, "feed", {}) or {}
        title = (feed.get("title") or "").strip()
        if title:
            return title
        author = feed.get("author")
        if isinstance(author, str) and author.strip():
            return author.strip()
        authors = feed.get("authors") or []
        if authors and isinstance(authors[0], dict) and authors[0].get("name"):
            return str(authors[0]["name"]).strip()
    except Exception:
        pass
    return ""


async def _fetch_feed_name(hass: HomeAssistant, feed_url: str) -> str:
    """Fetch an RSS feed and return its title (channel name)."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                feed_url,
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"User-Agent": "MeTubeManager/1.0 (Home Assistant)"},
            ) as resp:
                if resp.status != 200:
                    return ""
                text = await resp.text()
        parsed = await hass.async_add_executor_job(feedparser.parse, text)
        name = _feed_title_from_parsed(parsed)
        return name or feed_url
    except Exception:
        return feed_url


async def _fetch_feed_names(hass: HomeAssistant, urls: list[str]) -> list[dict[str, str]]:
    """Fetch each feed URL and return list of {url, name}."""
    result: list[dict[str, str]] = []
    for url in urls:
        if not url.strip():
            continue
        name = await _fetch_feed_name(hass, url)
        result.append({CONF_FEED_URL: url.strip(), CONF_FEED_NAME: name or url.strip()})
    return result


def _parse_feeds_text_lines(raw: str) -> list[tuple[bool, str, str, str]]:
    """Parse lines into (is_youtube, part1, part2, backlog).
    YouTube: (True, channel_ref, feed_type, backlog). Manual: (False, name, rss_url, backlog).
    """
    out: list[tuple[bool, str, str, str]] = []
    for line in (raw or "").strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(" | ")]
        if len(parts) >= 3:
            backlog = " | ".join(parts[2:]).strip()
            first, second = parts[0], parts[1]
        elif len(parts) == 2:
            backlog = ""
            first, second = parts[0], parts[1]
        else:
            first, second, backlog = parts[0], "", ""

        if _looks_like_youtube_channel(first) and _is_youtube_feed_type(second):
            out.append((True, first, second, backlog))
        elif second and (second.startswith("http://") or second.startswith("https://")):
            out.append((False, first, second, backlog))
        elif first and (first.startswith("http://") or first.startswith("https://")):
            out.append((False, "", first, backlog))
        elif _looks_like_youtube_channel(first):
            out.append((True, first, YOUTUBE_FEED_ALL, backlog))
        else:
            out.append((False, first, second, backlog))
    return out


async def _parse_feeds_text_and_fetch_names(
    hass: HomeAssistant,
    raw: str,
    existing_url_to_name: dict[str, str] | None = None,
    existing_url_to_backlog: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    """Parse feed lines: YouTube 'channel | feed_type | backlog' or manual 'Name | RSS URL | backlog'.
    Resolves YouTube channels to channel_id and builds RSS URL (All/Videos/Shorts/Live).
    """
    existing_name = existing_url_to_name or {}
    existing_backlog = existing_url_to_backlog or {}
    lines = _parse_feeds_text_lines(raw)
    result: list[dict[str, str]] = []
    for is_youtube, part1, part2, backlog_url in lines:
        backlog = (backlog_url or "").strip()

        if is_youtube:
            resolved = await _resolve_youtube_channel(hass, part1)
            if not resolved:
                continue
            channel_id, channel_name = resolved
            feed_type = (part2 or YOUTUBE_FEED_ALL).lower().strip()
            if feed_type not in YOUTUBE_FEED_TYPES:
                feed_type = YOUTUBE_FEED_ALL
            rss_url = _youtube_feed_url(channel_id, feed_type)
            display_name = channel_name or part1
            result.append({
                CONF_FEED_URL: rss_url,
                CONF_FEED_NAME: display_name,
                CONF_BACKLOG_PLAYLIST_URL: backlog or existing_backlog.get(rss_url, ""),
            })
        else:
            rss_url = part2
            if not rss_url:
                continue
            if part1:
                display_name = part1
            elif rss_url in existing_name:
                display_name = existing_name[rss_url]
            else:
                display_name = await _fetch_feed_name(hass, rss_url) or rss_url
            backlog = backlog or existing_backlog.get(rss_url, "")
            result.append({
                CONF_FEED_URL: rss_url,
                CONF_FEED_NAME: display_name,
                CONF_BACKLOG_PLAYLIST_URL: backlog.strip(),
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
        return MeTubeManagerOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            url = _normalize_url(user_input.get(CONF_METUBE_URL, ""))
            if not _validate_metube_url(url):
                errors["base"] = "invalid_url"
            else:
                ok = await _test_metube_connection(self.hass, url)
                if not ok:
                    errors["base"] = "cannot_connect"
                else:
                    self._user_step_data = {
                        CONF_METUBE_URL: url,
                        CONF_QUALITY: user_input.get(CONF_QUALITY, DEFAULT_QUALITY),
                    }
                    return self.async_show_form(
                        step_id="rss",
                        data_schema=vol.Schema(
                            {
                                vol.Required(CONF_RSS_FEEDS, default=""): str,
                            }
                        ),
                    )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_METUBE_URL, default="http://localhost:8081"): str,
                vol.Required(CONF_QUALITY, default=DEFAULT_QUALITY): str,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_rss(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle RSS feeds step (optional). Fetches channel name for each feed."""
        if user_input is not None:
            step_data = getattr(self, "_user_step_data", {}) or {}
            metube_url = step_data.get(CONF_METUBE_URL, "")
            quality = step_data.get(CONF_QUALITY, DEFAULT_QUALITY)

            rss_raw = user_input.get(CONF_RSS_FEEDS, "")
            feeds_with_names = await _parse_feeds_text_and_fetch_names(
                self.hass, rss_raw, {}, {}
            )

            return self.async_create_entry(
                title=metube_url or "MeTube",
                data={
                    CONF_METUBE_URL: metube_url,
                    CONF_QUALITY: quality,
                },
                options={CONF_RSS_FEEDS: feeds_with_names},
            )

        return self.async_show_form(
            step_id="rss",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_RSS_FEEDS, default=""): str,
                }
            ),
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> FlowResult:
        """Handle import from configuration.yaml (optional)."""
        return await self.async_step_user(import_data)


class MeTubeManagerOptionsFlow(config_entries.OptionsFlow):
    """Handle MeTube Manager options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options. Feeds shown as 'Name | URL'; new URLs get name fetched."""
        if user_input is not None:
            url = _normalize_url(user_input.get(CONF_METUBE_URL, ""))
            if not _validate_metube_url(url):
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._schema(),
                    errors={"base": "invalid_url"},
                )
            ok = await _test_metube_connection(self.hass, url)
            if not ok:
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._schema(),
                    errors={"base": "cannot_connect"},
                )
            feeds_text = user_input.get(CONF_RSS_FEEDS, "")
            names, backlogs = self._current_feed_names_and_backlogs()
            feeds_with_names = await _parse_feeds_text_and_fetch_names(
                self.hass,
                feeds_text,
                existing_url_to_name=names,
                existing_url_to_backlog=backlogs,
            )
            return self.async_create_entry(
                title="",
                data={
                    CONF_METUBE_URL: url,
                    CONF_QUALITY: user_input.get(CONF_QUALITY, DEFAULT_QUALITY),
                    CONF_RSS_FEEDS: feeds_with_names,
                },
            )

        return self.async_show_form(
            step_id="init",
            data_schema=self._schema(),
        )

    def _current_feed_names_and_backlogs(self) -> tuple[dict[str, str], dict[str, str]]:
        """Return (feed URL -> name, feed URL -> backlog playlist URL) from current config."""
        options = self.config_entry.options or {}
        feeds_list = options.get(CONF_RSS_FEEDS) or []
        names: dict[str, str] = {}
        backlogs: dict[str, str] = {}
        for f in feeds_list:
            if isinstance(f, dict):
                u = (f.get(CONF_FEED_URL) or "").strip()
                if not u:
                    continue
                names[u] = (f.get(CONF_FEED_NAME) or "").strip() or u
                b = (f.get(CONF_BACKLOG_PLAYLIST_URL) or "").strip()
                if b:
                    backlogs[u] = b
            elif isinstance(f, str) and f.strip():
                names[f.strip()] = f.strip()
        return names, backlogs

    def _schema(self) -> vol.Schema:
        """Build options schema. Feeds: 'Name | RSS URL' or 'Name | RSS URL | Backlog playlist URL'."""
        data = self.config_entry.data
        options = self.config_entry.options or {}
        url = options.get(CONF_METUBE_URL) or data.get(CONF_METUBE_URL, "")
        quality = options.get(CONF_QUALITY) or data.get(CONF_QUALITY, DEFAULT_QUALITY)
        feeds_list = options.get(CONF_RSS_FEEDS) or []
        lines = []
        for f in feeds_list:
            if isinstance(f, dict):
                u = (f.get(CONF_FEED_URL) or "").strip()
                n = (f.get(CONF_FEED_NAME) or "").strip() or u
                b = (f.get(CONF_BACKLOG_PLAYLIST_URL) or "").strip()
                if u:
                    if b:
                        lines.append(f"{n} | {u} | {b}")
                    else:
                        lines.append(f"{n} | {u}")
            elif isinstance(f, str) and f.strip():
                lines.append(f.strip())
        feeds_text = "\n".join(lines)
        return vol.Schema(
            {
                vol.Required(CONF_METUBE_URL, default=url): str,
                vol.Required(CONF_QUALITY, default=quality): str,
                vol.Required(CONF_RSS_FEEDS, default=feeds_text): str,
            }
        )
