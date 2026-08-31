"""Home Assistant integration for the notification registry."""

from __future__ import annotations

from typing import Any

from . import services, websocket_api
from .const import DOMAIN
from .frontend import async_register_frontend

PLATFORMS = ["sensor"]


async def async_setup(hass: Any, _config: dict[str, Any]) -> bool:
    hass.data.setdefault(DOMAIN, {})
    websocket_api.async_register_commands(hass)
    await async_register_frontend(hass)
    return True


async def async_setup_entry(hass: Any, entry: Any) -> bool:
    domain_data = hass.data.setdefault(DOMAIN, {})
    if entry.entry_id in domain_data:
        return True
    registry = await services.async_maybe_await(
        services._async_load_registry(hass, entry)
    )
    domain_data[entry.entry_id] = registry
    websocket_api.async_register_commands(hass)
    services.async_register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: Any, entry: Any) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        return False
    domain_data = hass.data.get(DOMAIN, {})
    domain_data.pop(entry.entry_id, None)
    if not domain_data:
        services.async_remove_services(hass)
        hass.data.pop(DOMAIN, None)
    return True
