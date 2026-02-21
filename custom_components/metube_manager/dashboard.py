"""Register a MeTube Manager Lovelace dashboard (feeds and stats)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store

from .const import DOMAIN

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

    if any(item.get("id") == DASHBOARD_URL_PATH or item.get("url_path") == DASHBOARD_URL_PATH for item in items):
        return

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

    dev_reg = dr.async_get(hass)
    device_id = None
    for dev in dr.async_entries_for_config_entry(dev_reg, entry_id):
        device_id = dev.id
        break

    if device_id:
        view_config: dict[str, Any] = {
            "title": DASHBOARD_TITLE,
            "path": DASHBOARD_URL_PATH,
            "cards": [
                {
                    "type": "entities",
                    "title": "Feeds & status",
                    "entities": [
                        {"entity": "sensor.metube_manager_status"},
                        {"device_id": device_id},
                    ],
                }
            ],
        }
    else:
        view_config = {
            "title": DASHBOARD_TITLE,
            "path": DASHBOARD_URL_PATH,
            "cards": [
                {
                    "type": "entities",
                    "title": "Feeds & status",
                    "entities": [{"entity": "sensor.metube_manager_status"}],
                }
            ],
        }

    config_store = Store(
        hass,
        LOVELACE_CONFIG_VERSION,
        LOVELACE_CONFIG_KEY_TEMPLATE.format(DASHBOARD_URL_PATH),
    )
    await config_store.async_save({"config": {"views": [view_config]}})
    try:
        hass.bus.async_fire("lovelace_updated", {"url_path": DASHBOARD_URL_PATH})
    except Exception:
        pass
    _LOGGER.info(
        "MeTube Manager dashboard created. Open it from the sidebar (MeTube Manager) or go to /%s. If you don't see it, restart Home Assistant.",
        DASHBOARD_URL_PATH,
    )