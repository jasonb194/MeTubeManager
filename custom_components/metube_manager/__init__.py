"""MeTube Manager: poll RSS feeds and send new videos to MeTube."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import aiohttp
import feedparser
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

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

    async def _load_feed_stats() -> dict[str, Any]:
        """Load feed_stats from store for coordinator."""
        data = await store.async_load() or {}
        return data.get("feed_stats") or {}

    coordinator = DataUpdateCoordinator(
        hass,
        logging.getLogger(__name__),
        name=DOMAIN,
        update_method=_load_feed_stats,
    )
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    def _update_feed_stats(
        stats: dict[str, dict[str, Any]], feed_url: str, sent_count: int = 0
    ) -> None:
        """Update feed_stats for a feed with last_fetched and total_sent."""
        now = datetime.now(timezone.utc).isoformat()
        prev = stats.get(feed_url) or {}
        total = (prev.get("total_sent") or 0) + sent_count
        stats[feed_url] = {"last_fetched": now, "total_sent": total}

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
            feed_stats: dict[str, dict[str, Any]] = dict(seen_data.get("feed_stats") or {})
        except Exception as e:
            _LOGGER.warning("Loading seen URLs failed: %s", e)
            seen = set()
            backlog_done = set()
            feed_stats = {}

        add_url = base_url.rstrip("/") + "/add"

        async with aiohttp.ClientSession() as session:
            for feed in feeds:
                feed_url = feed["url"]
                feed_name = feed.get("name") or feed_url
                backlog_playlist = (feed.get(CONF_BACKLOG_PLAYLIST_URL) or "").strip()

                # One-time backlog: generate URL from feed (YouTube playlist or RSS feed)
                backlog_sent = 0
                if backlog_playlist and feed_url not in backlog_done:
                    if backlog_playlist == feed_url:
                        # RSS backlog: fetch feed and send all current items once
                        _LOGGER.info("Fetching RSS backlog for %s", feed_name)
                        try:
                            async with session.get(
                                feed_url,
                                timeout=aiohttp.ClientTimeout(total=30),
                                headers={"User-Agent": "MeTubeManager/1.0 (Home Assistant)"},
                            ) as resp:
                                if resp.status != 200:
                                    raise OSError(f"RSS returned {resp.status}")
                                text = await resp.text()
                            parsed = await hass.async_add_executor_job(feedparser.parse, text)
                            for item in getattr(parsed, "entries", []) or []:
                                link = (item.get("link") or "").strip()
                                if not link or link in seen:
                                    continue
                                seen.add(link)
                                try:
                                    async with session.post(
                                        add_url,
                                        json={"url": link, "quality": quality, "format": "mp4"},
                                        timeout=aiohttp.ClientTimeout(total=30),
                                    ) as add_resp:
                                        if add_resp.status in (200, 201):
                                            _LOGGER.info("Sent to MeTube (RSS backlog): %s", link)
                                            backlog_sent += 1
                                except Exception as e:
                                    _LOGGER.warning("MeTube /add failed for %s: %s", link, e)
                            backlog_done.add(feed_url)
                        except Exception as e:
                            _LOGGER.exception("RSS backlog failed for %s: %s", feed_name, e)
                    else:
                        # YouTube playlist: fetch via yt-dlp
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
                                            backlog_sent += 1
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
                _update_feed_stats(feed_stats, feed_url, backlog_sent)

            for feed in feeds:
                feed_url = feed["url"]
                feed_name = feed.get("name") or feed_url
                rss_sent = 0
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
                        _update_feed_stats(feed_stats, feed_url, 0)
                        continue
                    text = await resp.text()
                except Exception as e:
                    _LOGGER.warning("Failed to fetch RSS %s (%s): %s", feed_name, feed_url, e)
                    _update_feed_stats(feed_stats, feed_url, 0)
                    continue

                try:
                    parsed = await hass.async_add_executor_job(feedparser.parse, text)
                except Exception as e:
                    _LOGGER.warning("Failed to parse RSS %s (%s): %s", feed_name, feed_url, e)
                    _update_feed_stats(feed_stats, feed_url, 0)
                    continue

                for item in getattr(parsed, "entries", []) or []:
                    link = (item.get("link") or "").strip()
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
                                _LOGGER.info("Sent to MeTube: %s", link)
                                rss_sent += 1
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
                _update_feed_stats(feed_stats, feed_url, rss_sent)

        try:
            await store.async_save({
                "urls": list(seen),
                "backlog_done": list(backlog_done),
                "feed_stats": feed_stats,
            })
        except Exception as e:
            _LOGGER.warning("Saving seen URLs failed: %s", e)
        coordinator.async_set_updated_data(feed_stats)

    # Use HA's track_time_interval (cron-style, robust, survives reloads)
    remove = async_track_time_interval(hass, _poll_feeds, SCAN_INTERVAL)
    entry.async_on_unload(remove)

    # Reload when options change (add/remove feeds) so sensor list stays in sync
    entry.async_on_unload(entry.add_update_listener(lambda _hass, _entry: _hass.config_entries.async_reload(_entry.entry_id)))

    # Set up sensor so the integration has a visible entity (feed count, scan interval)
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    # Create/update MeTube Manager dashboard (shows all channels from all entries)
    try:
        from .dashboard import ensure_dashboard
        await ensure_dashboard(hass)
    except Exception as e:
        _LOGGER.warning("Could not create MeTube Manager dashboard: %s", e)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry; remove interval listener and sensors."""
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove a config entry and delete all stored data (seen URLs, backlog state)."""
    store_key = f"{DOMAIN}_{entry.entry_id}_{STORAGE_KEY}"
    store = Store(hass, STORAGE_VERSION, store_key)
    await store.async_remove()
    _LOGGER.debug("Removed storage for MeTube Manager entry %s", entry.entry_id)
