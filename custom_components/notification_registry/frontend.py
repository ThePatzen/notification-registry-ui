"""Serve and register the bundled Lovelace card."""

from __future__ import annotations

import logging
from typing import Any

from .const import CARD_RESOURCE_URL, FRONTEND_DIR, URL_BASE

try:
    from homeassistant.components.http import StaticPathConfig
    from homeassistant.exceptions import HomeAssistantError
except ImportError:  # pragma: no cover - used by focused API doubles
    from dataclasses import dataclass

    class HomeAssistantError(Exception):  # type: ignore[no-redef]
        """Small compatibility error for tests without Home Assistant installed."""

    @dataclass(frozen=True)
    class StaticPathConfig:  # type: ignore[no-redef]
        """Small stand-in for Home Assistant's static path descriptor."""

        url_path: str
        path: str
        cache_headers: bool = True


_SETUP_MARKER = "_frontend_registered"
_LOGGER = logging.getLogger(__name__)


def _resource_mode(lovelace: Any) -> str:
    return getattr(lovelace, "resource_mode", getattr(lovelace, "mode", "yaml"))


async def _async_register_resource(lovelace: Any) -> None:
    resources = getattr(lovelace, "resources", None)
    if resources is None:
        return

    if not getattr(resources, "loaded", True):
        load = getattr(resources, "async_load", None)
        if load is not None:
            await load()

    items = resources.async_items()
    path = CARD_RESOURCE_URL.split("?", 1)[0]
    existing = next(
        (
            item
            for item in items
            if str(item.get("url", "")).split("?", 1)[0] == path
        ),
        None,
    )
    if existing is None:
        await resources.async_create_item(
            {"res_type": "module", "url": CARD_RESOURCE_URL}
        )
        return

    if existing.get("url") != CARD_RESOURCE_URL:
        update = getattr(resources, "async_update_item", None)
        if update is not None:
            await update(
                existing["id"],
                {"res_type": "module", "url": CARD_RESOURCE_URL},
            )


async def async_register_frontend(hass: Any) -> None:
    """Register the bundled card once per Home Assistant instance."""
    markers = hass.data.setdefault("notification_registry_frontend", {})
    if markers.get(_SETUP_MARKER):
        return

    await hass.http.async_register_static_paths(
        [StaticPathConfig(URL_BASE, str(FRONTEND_DIR), True)]
    )

    lovelace = hass.data.get("lovelace")
    if lovelace is not None and _resource_mode(lovelace) == "storage":
        try:
            await _async_register_resource(lovelace)
        except (HomeAssistantError, OSError, RuntimeError):
            _LOGGER.warning(
                "Could not register the Lovelace card resource", exc_info=True
            )

    markers[_SETUP_MARKER] = True
