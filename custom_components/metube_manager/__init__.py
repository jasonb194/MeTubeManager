"""MeTube Manager: poll RSS feeds and send new videos to MeTube."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
import feedparser
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    CONF_METUBE_URL,
    CONF_QUALITY,
    CONF_RSS_FEEDS,
    DEFAULT_QUALITY,
    DOMAIN,
    SCAN_INTERVAL_SECONDS,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the MeTube Manager domain."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MeTube Manager from a config entry."""
    store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}_{STORAGE_KEY}")

    async def _poll_feeds() -> None:
        """Fetch all RSS feeds, find new video URLs, send to MeTube."""
        options = entry.options or entry.data
        feeds: list[str] = options.get(CONF_RSS_FEEDS) or []
        base_url = (options.get(CONF_METUBE_URL) or entry.data.get(CONF_METUBE_URL) or "").rstrip("/")
        quality = options.get(CONF_QUALITY) or entry.data.get(CONF_QUALITY) or DEFAULT_QUALITY

        if not base_url or not feeds:
            return

        try:
            seen_data = await store.async_load() or {}
            seen: set[str] = set(seen_data.get("urls", []) or [])
        except Exception as e:
            _LOGGER.warning("Loading seen URLs failed: %s", e)
            seen = set()

        new_urls: list[str] = []
        add_url = base_url.rstrip("/") + "/add"

        async with aiohttp.ClientSession() as session:
            for feed_url in feeds:
                if not feed_url.strip():
                    continue
                try:
                    resp = await session.get(
                        feed_url,
                        timeout=aiohttp.ClientTimeout(total=30),
                        headers={"User-Agent": "MeTubeManager/1.0 (Home Assistant)"},
                    )
                    if resp.status != 200:
                        _LOGGER.warning("RSS feed %s returned %s", feed_url, resp.status)
                        continue
                    text = await resp.text()
                except Exception as e:
                    _LOGGER.warning("Failed to fetch RSS %s: %s", feed_url, e)
                    continue

                try:
                    parsed = await hass.async_add_executor_job(feedparser.parse, text)
                except Exception as e:
                    _LOGGER.warning("Failed to parse RSS %s: %s", feed_url, e)
                    continue

                for item in getattr(parsed, "entries", []) or []:
                    link = (item.get("link") or "").strip()
                    if not link or link in seen:
                        continue
                    # Optional: only treat known video domains if you want
                    seen.add(link)
                    new_urls.append(link)

                    try:
                        async with session.post(
                            add_url,
                            json={"url": link, "quality": quality},
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

        if new_urls:
            try:
                await store.async_save({"urls": list(seen)})
            except Exception as e:
                _LOGGER.warning("Saving seen URLs failed: %s", e)

    async def _schedule() -> None:
        while True:
            try:
                await _poll_feeds()
            except Exception as e:
                _LOGGER.exception("MeTube Manager poll error: %s", e)
            await asyncio.sleep(SCAN_INTERVAL_SECONDS)

    hass.async_create_task(_schedule())
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry (tasks are fire-and-forget; no cleanup needed)."""
    return True
