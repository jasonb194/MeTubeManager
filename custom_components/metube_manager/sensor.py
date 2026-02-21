"""MeTube Manager sensors: one per feed (status, count, last fetched) + summary."""

from __future__ import annotations

import hashlib
import re
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_FEED_NAME, CONF_FEED_URL, CONF_RSS_FEEDS, DOMAIN


def _slug(s: str, max_len: int = 30) -> str:
    """Safe slug for entity id."""
    s = re.sub(r"[^a-zA-Z0-9]+", "_", (s or "").strip()).strip("_")[:max_len]
    return s or "feed"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MeTube Manager sensors: one per feed + one summary."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not coordinator:
        return
    options = entry.options or entry.data
    feeds = options.get(CONF_RSS_FEEDS) or []
    feed_list: list[tuple[str, str]] = []
    for f in feeds:
        if isinstance(f, dict):
            url = (f.get(CONF_FEED_URL) or f.get("url") or "").strip()
            name = (f.get(CONF_FEED_NAME) or "").strip() or url
            if url:
                feed_list.append((url, name))
        elif isinstance(f, str) and f.strip():
            feed_list.append((f.strip(), f.strip()))
    entities: list[SensorEntity] = [
        MeTubeManagerSensor(entry),
    ]
    for feed_url, feed_name in feed_list:
        entities.append(MeTubeManagerFeedSensor(entry, coordinator, feed_url, feed_name))
    async_add_entities(entities)


class MeTubeManagerSensor(SensorEntity):
    """Summary sensor: number of feeds configured."""

    _attr_has_entity_name = True
    _attr_name = "Status"

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_status"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "MeTube Manager",
            "manufacturer": "MeTube Manager",
        }

    @property
    def native_value(self) -> str:
        options = self._entry.options or self._entry.data
        feeds = options.get(CONF_RSS_FEEDS) or []
        count = sum(
            1
            for f in feeds
            if (isinstance(f, str) and f.strip())
            or (isinstance(f, dict) and (f.get(CONF_FEED_URL) or f.get("url")))
        )
        return str(count)

    @property
    def native_unit_of_measurement(self) -> str:
        return "feeds"

    @property
    def extra_state_attributes(self) -> dict:
        options = self._entry.options or self._entry.data
        base_url = (options.get("metube_url") or self._entry.data.get("metube_url") or "").rstrip("/")
        return {
            "scan_interval": "Every hour",
            "metube_url": base_url or None,
        }


class MeTubeManagerFeedSensor(CoordinatorEntity, SensorEntity):
    """Per-feed sensor: total sent, last fetched."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "videos"

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: "DataUpdateCoordinator",
        feed_url: str,
        feed_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._feed_url = feed_url
        self._feed_name = feed_name or feed_url
        slug = _slug(self._feed_name)
        url_hash = hashlib.md5(feed_url.encode()).hexdigest()[:10]
        self._attr_unique_id = f"{entry.entry_id}_feed_{slug}_{url_hash}"
        self._attr_name = self._feed_name
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "MeTube Manager",
            "manufacturer": "MeTube Manager",
        }

    @property
    def native_value(self) -> str:
        data = self.coordinator.data or {}
        stats = data.get(self._feed_url) or {}
        total = stats.get("total_sent") or 0
        return str(total)

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data or {}
        stats = data.get(self._feed_url) or {}
        return {
            "last_fetched": stats.get("last_fetched"),
            "feed_url": self._feed_url,
            "feed_name": self._feed_name,
        }