"""Register a MeTube Manager Lovelace dashboard (feeds and stats)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)

DASHBOARD_URL_PATH = "metube-manager"
DASHBOARD_TITLE = "MeTube Manager"
DASHBOARD_ICON = "mdi:youtube"
LOVELACE_DASHBOARDS_KEY = "lovelace_dashboards"
LOVELACE_DASHBOARDS_VERSION = 1
LOVELACE_CONFIG_KEY_TEMPLATE = "lovelace.{}"
LOVELACE_CONFIG_VERSION = 1


async def ensure_dashboard(hass: HomeAssistant, entry_id: str | None = None) -> None:
    """Create or ensure the MeTube Manager dashboard exists. Shows all channels (all config entries)."""
    dashboards_store = Store(hass, LOVELACE_DASHBOARDS_VERSION, LOVELACE_DASHBOARDS_KEY)
    data = await dashboards_store.async_load() or {}
    items = list(data.get("items") or [])

    if not any(item.get("id") == DASHBOARD_URL_PATH or item.get("url_path") == DASHBOARD_URL_PATH for item in items):
        new_item = {
            "id": DASHBOARD_URL_PATH,
            "url_path": DASHBOARD_URL_PATH,
            "title": DASHBOARD_TITLE,
            "icon": DASHBOARD_ICON,
            "show_in_sidebar": True,
            "require_admin": False,
        }
        items.append(new_item)
        await dashboards_store.async_save({"items": items})

    # Collect entities from ALL MeTube Manager config entries (one integration per channel).
    ent_reg = er.async_get(hass)
    all_feed_entries: list[tuple[str, str]] = []  # (entity_id, channel/feed name)
    status_entity_ids: list[str] = []
    for config_entry in hass.config_entries.async_entries("metube_manager"):
        for reg_entry in er.async_entries_for_config_entry(ent_reg, config_entry.entry_id):
            if not reg_entry.entity_id:
                continue
            name = reg_entry.original_name or reg_entry.entity_id or ""
            if (reg_entry.unique_id or "").endswith("_status"):
                status_entity_ids.append(reg_entry.entity_id)
            else:
                all_feed_entries.append((reg_entry.entity_id, name))

    integrations_path = "/config/integrations"
    add_feeds_markdown = (
        f"**To add a channel:** [Settings → Devices & services]({integrations_path}) → **Add integration** → **MeTube Manager**. "
        "One integration = one channel. To edit a channel, click its card and **Configure**."
    )

    cards: list[dict[str, Any]] = [
        {"type": "markdown", "content": add_feeds_markdown, "title": "Channels"},
    ]
    if status_entity_ids:
        cards.append({
            "type": "entities",
            "title": "Overview",
            "entities": status_entity_ids,
        })

    for eid, channel_name in all_feed_entries:
        state = hass.states.get(eid)
        attrs = (state.attributes or {}) if state else {}
        youtube_url = attrs.get("youtube_channel_url") or ""
        rows: list[dict[str, Any]] = []
        if youtube_url:
            rows.append({
                "type": "weblink",
                "url": youtube_url,
                "name": "YouTube channel",
                "icon": "mdi:youtube",
                "new_tab": True,
            })
        rows.extend([
            {"entity": eid},
            {"type": "attribute", "entity": eid, "attribute": "channel_id", "name": "Channel ID"},
            {"type": "attribute", "entity": eid, "attribute": "rss_feed", "name": "Feed URL"},
            {"type": "attribute", "entity": eid, "attribute": "backlog_url", "name": "Backlog URL"},
            {"type": "attribute", "entity": eid, "attribute": "backlog_enabled", "name": "Backlog enabled"},
            {"type": "attribute", "entity": eid, "attribute": "videos_downloaded", "name": "Videos downloaded"},
            {"type": "attribute", "entity": eid, "attribute": "last_downloaded", "name": "Last downloaded", "format": "datetime"},
        ])
        cards.append({
            "type": "entities",
            "title": channel_name or eid,
            "entities": rows,
        })

    view_config: dict[str, Any] = {
        "title": DASHBOARD_TITLE,
        "path": DASHBOARD_URL_PATH,
        "cards": cards,
    }

    dashboard_config = {"views": [view_config]}

    # Prefer updating via Lovelace component so in-memory cache is updated (fixes stale device_id config)
    try:
        lovelace_data = hass.data.get("lovelace")
        if lovelace_data and hasattr(lovelace_data, "dashboards"):
            dash = lovelace_data.dashboards.get(DASHBOARD_URL_PATH)
            if dash is not None and hasattr(dash, "async_save"):
                await dash.async_save(dashboard_config)
                _LOGGER.info(
                    "MeTube Manager dashboard updated (entity list and link). Open from sidebar or /%s",
                    DASHBOARD_URL_PATH,
                )
                return
    except Exception as e:
        _LOGGER.debug("Could not update dashboard via Lovelace API: %s", e)

    # Fallback: write directly to store (in-memory cache may stay stale until HA restart)
    config_store = Store(
        hass,
        LOVELACE_CONFIG_VERSION,
        LOVELACE_CONFIG_KEY_TEMPLATE.format(DASHBOARD_URL_PATH),
    )
    await config_store.async_save({"config": dashboard_config})
    try:
        hass.bus.async_fire("lovelace_updated", {"url_path": DASHBOARD_URL_PATH})
    except Exception:
        pass
    _LOGGER.info(
        "MeTube Manager dashboard saved. If the dashboard still shows an error, restart Home Assistant. Open from sidebar or /%s",
        DASHBOARD_URL_PATH,
    )