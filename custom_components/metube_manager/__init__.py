"""MeTube Manager: poll RSS feeds and send new videos to MeTube."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import feedparser
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .const import (
    CONF_BACKLOG_PLAYLIST_URL,
    CONF_FEED_NAME,
    CONF_FEED_URL,
    CONF_METUBE_URL,
    CONF_QUALITY,
    CONF_RSS_FEEDS,
    DEFAULT_QUALITY,
    DOMAIN,
    SCAN_INTERVAL,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


def _yt_dlp_playlist_video_urls(playlist_url: str) -> list[str]:
    """Extract all video watch URLs from a playlist using yt-dlp (flat, no download)."""
    import yt_dlp
    urls: list[str] = []
    opts = {
        "extract_flat": "in_playlist",
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(playlist_url, download=False)
        if not info:
            return urls
        entries = info.get("entries") or []
        for entry in entries:
            if not entry:
                continue
            vid_id = entry.get("id")
            if vid_id:
                urls.append(f"https://www.youtube.com/watch?v={vid_id}")
            elif entry.get("url"):
                urls.append(entry["url"])
    except Exception as e:
        _LOGGER.warning("yt-dlp playlist extract failed for %s: %s", playlist_url, e)
    return urls


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the MeTube Manager domain."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MeTube Manager from a config entry."""
    store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}_{STORAGE_KEY}")

    def _normalize_feed(f: Any) -> dict[str, Any] | None:
        """Return {url, name, backlog_playlist_url?} from feed item (dict or legacy string)."""
        if isinstance(f, dict):
            url = (f.get(CONF_FEED_URL) or "").strip()
            name = (f.get(CONF_FEED_NAME) or url or "").strip()
            backlog = (f.get(CONF_BACKLOG_PLAYLIST_URL) or "").strip()
            if not url:
                return None
            out: dict[str, Any] = {"url": url, "name": name}
            if backlog:
                out[CONF_BACKLOG_PLAYLIST_URL] = backlog
            return out
        if isinstance(f, str) and f.strip():
            return {"url": f.strip(), "name": f.strip()}
        return None

    async def _poll_feeds(*_args: Any, **_kwargs: Any) -> None:
        """Fetch all RSS feeds, find new video URLs, send to MeTube."""
        options = entry.options or entry.data
        raw_feeds = options.get(CONF_RSS_FEEDS) or []
        feeds = [f for f in (_normalize_feed(x) for x in raw_feeds) if f]
        base_url = (options.get(CONF_METUBE_URL) or entry.data.get(CONF_METUBE_URL) or "").rstrip("/")
        quality = options.get(CONF_QUALITY) or entry.data.get(CONF_QUALITY) or DEFAULT_QUALITY

        if not base_url or not feeds:
            return

        try:
            seen_data = await store.async_load() or {}
            seen: set[str] = set(seen_data.get("urls", []) or [])
            backlog_done: set[str] = set(seen_data.get("backlog_done", []) or [])
        except Exception as e:
            _LOGGER.warning("Loading seen URLs failed: %s", e)
            seen = set()
            backlog_done = set()

        add_url = base_url.rstrip("/") + "/add"

        async with aiohttp.ClientSession() as session:
            for feed in feeds:
                feed_url = feed["url"]
                feed_name = feed.get("name") or feed_url
                backlog_playlist = (feed.get(CONF_BACKLOG_PLAYLIST_URL) or "").strip()

                # One-time backlog: fetch full playlist via yt-dlp and send to MeTube
                if backlog_playlist and feed_url not in backlog_done:
                    _LOGGER.info("Fetching backlog playlist for %s: %s", feed_name, backlog_playlist)
                    try:
                        playlist_urls = await hass.async_add_executor_job(
                            _yt_dlp_playlist_video_urls, backlog_playlist
                        )
                        for link in playlist_urls:
                            if not link or link in seen:
                                continue
                            seen.add(link)
                            try:
                                async with session.post(
                                    add_url,
                                    json={
                                        "url": link,
                                        "quality": quality,
                                        "format": "mp4",
                                    },
                                    timeout=aiohttp.ClientTimeout(total=30),
                                ) as add_resp:
                                    if add_resp.status in (200, 201):
                                        _LOGGER.info("Sent to MeTube (backlog): %s", link)
                                    else:
                                        body = await add_resp.text()
                                        _LOGGER.warning(
                                            "MeTube /add failed for %s: %s %s",
                                            link,
                                            add_resp.status,
                                            body[:200],
                                        )
                            except Exception as e:
                                _LOGGER.warning("MeTube /add request failed for %s: %s", link, e)
                        backlog_done.add(feed_url)
                    except Exception as e:
                        _LOGGER.exception("Backlog fetch failed for %s: %s", feed_name, e)

            for feed in feeds:
                feed_url = feed["url"]
                feed_name = feed.get("name") or feed_url
                if not feed_url:
                    continue
                try:
                    resp = await session.get(
                        feed_url,
                        timeout=aiohttp.ClientTimeout(total=30),
                        headers={"User-Agent": "MeTubeManager/1.0 (Home Assistant)"},
                    )
                    if resp.status != 200:
                        _LOGGER.warning(
                            "RSS feed %s (%s) returned %s",
                            feed_name,
                            feed_url,
                            resp.status,
                        )
                        continue
                    text = await resp.text()
                except Exception as e:
                    _LOGGER.warning("Failed to fetch RSS %s (%s): %s", feed_name, feed_url, e)
                    continue

                try:
                    parsed = await hass.async_add_executor_job(feedparser.parse, text)
                except Exception as e:
                    _LOGGER.warning("Failed to parse RSS %s (%s): %s", feed_name, feed_url, e)
                    continue

                for item in getattr(parsed, "entries", []) or []:
                    link = (item.get("link") or "").strip()
                    if not link or link in seen:
                        continue
                    # Optional: only treat known video domains if you want
                    seen.add(link)

                    try:
                        async with session.post(
                            add_url,
                            json={
                                "url": link,
                                "quality": quality,
                                "format": "mp4",
                            },
                            timeout=aiohttp.ClientTimeout(total=30),
                        ) as add_resp:
                            if add_resp.status in (200, 201):
                                _LOGGER.info("Sent to MeTube: %s", link)
                            else:
                                body = await add_resp.text()
                                _LOGGER.warning(
                                    "MeTube /add failed for %s: %s %s",
                                    link,
                                    add_resp.status,
                                    body[:200],
                                )
                    except Exception as e:
                        _LOGGER.warning("MeTube /add request failed for %s: %s", link, e)

        try:
            await store.async_save({
                "urls": list(seen),
                "backlog_done": list(backlog_done),
            })
        except Exception as e:
            _LOGGER.warning("Saving seen URLs failed: %s", e)

    # Use HA's track_time_interval (cron-style, robust, survives reloads)
    remove = async_track_time_interval(hass, _poll_feeds, SCAN_INTERVAL)
    entry.async_on_unload(remove)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry; interval listener is removed via async_on_unload."""
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove a config entry and delete all stored data (seen URLs, backlog state)."""
    store_key = f"{DOMAIN}_{entry.entry_id}_{STORAGE_KEY}"
    store = Store(hass, STORAGE_VERSION, store_key)
    await store.async_remove()
    _LOGGER.debug("Removed storage for MeTube Manager entry %s", entry.entry_id)
