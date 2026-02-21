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


async def ensure_dashboard(hass: HomeAssistant, entry_id: str) -> None:
    """Create or ensure the MeTube Manager dashboard exists. Uses Lovelace storage."""
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

    # Always update view config: fix broken device_id format and keep entity list in sync when feeds change.
    # Entities must be a list of entity ID strings only (Lovelace does not support device_id in entities card).
    ent_reg = er.async_get(hass)
    entity_ids: list[str] = []
    for reg_entry in er.async_entries_for_config_entry(ent_reg, entry_id):
        if reg_entry.entity_id:
            entity_ids.append(reg_entry.entity_id)
    if not entity_ids:
        entity_ids = ["sensor.metube_manager_status"]

    # Link to integrations list; users click MeTube Manager → Configure to add feeds (no separate integration per feed)
    integrations_path = "/config/integrations"
    add_feeds_markdown = (
        f"**To add or edit feeds:** Go to [Settings → Devices & services]({integrations_path}), "
        "find **MeTube Manager**, click it, then click **Configure**. "
        "Add YouTube channels (e.g. `@Channel | Videos`) or RSS URLs in the text area — one per line. "
        "Do **not** use \"Add integration\"; feeds are added inside MeTube Manager."
    )

    view_config: dict[str, Any] = {
        "title": DASHBOARD_TITLE,
        "path": DASHBOARD_URL_PATH,
        "cards": [
            {
                "type": "markdown",
                "content": add_feeds_markdown,
                "title": "Manage feeds",
            },
            {
                "type": "entities",
                "title": "Feeds & status",
                "entities": entity_ids,
            },
        ],
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