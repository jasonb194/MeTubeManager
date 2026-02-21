"""Config flow for MeTube Manager."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_METUBE_URL, CONF_QUALITY, CONF_RSS_FEEDS, DEFAULT_QUALITY, DOMAIN


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
        """Handle RSS feeds step (optional)."""
        if user_input is not None:
            step_data = getattr(self, "_user_step_data", {}) or {}
            metube_url = step_data.get(CONF_METUBE_URL, "")
            quality = step_data.get(CONF_QUALITY, DEFAULT_QUALITY)

            rss_raw = user_input.get(CONF_RSS_FEEDS, "")
            feeds = _parse_rss_feeds(rss_raw)

            return self.async_create_entry(
                title=metube_url or "MeTube",
                data={
                    CONF_METUBE_URL: metube_url,
                    CONF_QUALITY: quality,
                },
                options={CONF_RSS_FEEDS: feeds},
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
        """Manage the options."""
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
            feeds = _parse_rss_feeds(user_input.get(CONF_RSS_FEEDS, ""))
            return self.async_create_entry(
                title="",
                data={
                    CONF_METUBE_URL: url,
                    CONF_QUALITY: user_input.get(CONF_QUALITY, DEFAULT_QUALITY),
                    CONF_RSS_FEEDS: feeds,
                },
            )

        return self.async_show_form(
            step_id="init",
            data_schema=self._schema(),
        )

    def _schema(self) -> vol.Schema:
        """Build options schema with current values."""
        data = self.config_entry.data
        options = self.config_entry.options or {}
        url = options.get(CONF_METUBE_URL) or data.get(CONF_METUBE_URL, "")
        quality = options.get(CONF_QUALITY) or data.get(CONF_QUALITY, DEFAULT_QUALITY)
        feeds_list = options.get(CONF_RSS_FEEDS) or []
        feeds_text = "\n".join(feeds_list) if isinstance(feeds_list, list) else str(feeds_list or "")
        return vol.Schema(
            {
                vol.Required(CONF_METUBE_URL, default=url): str,
                vol.Required(CONF_QUALITY, default=quality): str,
                vol.Required(CONF_RSS_FEEDS, default=feeds_text): str,
            }
        )
