"""Home Assistant actions exposed by the notification registry."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any

from .const import DOMAIN, SCHEMA_VERSION
from .registry import NotificationRegistry
from .resolve import resolve_entry
from .storage import STORE_KEY, RegistryStorage

try:  # Home Assistant is available in the running integration, not unit tests.
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers.service import SupportsResponse
    from homeassistant.helpers.storage import Store
except ImportError:  # pragma: no cover - exercised by the focused API doubles

    class HomeAssistantError(Exception):
        """Small compatibility error for tests without Home Assistant installed."""

    from enum import Enum

    class SupportsResponse(Enum):
        ONLY = "only"

    class Store:  # type: ignore[no-redef]
        def __init__(self, hass: Any, version: int, key: str):
            self.hass = hass
            self.version = version
            self.key = key

        async def async_load(self) -> Any:
            return None

        async def async_save(self, data: Any) -> None:
            return None


SERVICE_RESOLVE = "resolve"


async def _async_load_registry(hass: Any, _entry: Any) -> NotificationRegistry:
    """Build the registry from HA's versioned Store and perform first import."""
    store = Store(hass, SCHEMA_VERSION, STORE_KEY)
    storage = RegistryStorage(store)
    snapshot = await storage.async_load_or_import()
    return NotificationRegistry(storage, snapshot)


def _registry_from_hass(hass: Any) -> NotificationRegistry:
    domain_data = hass.data.get(DOMAIN, {})
    if not domain_data:
        raise HomeAssistantError("registry_unavailable")
    return next(iter(domain_data.values()))


def _resolved_to_dict(resolved: Any) -> dict[str, Any]:
    """Serialize a resolved notification without exposing registry internals."""
    serializer = getattr(resolved, "to_dict", None)
    if serializer is not None:
        return serializer()
    return {
        "titel": resolved.titel,
        "text": resolved.text,
        "schweregrad": resolved.schweregrad,
        "zielgruppe": resolved.zielgruppe,
        "kanaele": list(resolved.kanaele),
        "tag": resolved.tag,
        "missing_placeholders": list(resolved.missing_placeholders),
    }


async def _async_resolve(call: Any) -> dict[str, Any]:
    return await _async_resolve_for_hass(call.hass, call)


async def _async_resolve_for_hass(hass: Any, call: Any) -> dict[str, Any]:
    """Resolve a service call against the registry owned by ``hass``."""
    data = call.data
    key = data.get("key") if isinstance(data, Mapping) else None
    if not isinstance(key, str):
        raise HomeAssistantError("invalid_key")
    payload = data.get("payload", {})
    if not isinstance(payload, Mapping):
        raise HomeAssistantError("invalid_payload")
    registry = _registry_from_hass(hass)
    entry = registry.get(key)
    if entry is None:
        raise HomeAssistantError("unknown_key")
    return _resolved_to_dict(resolve_entry(entry, payload))


def async_register_services(hass: Any) -> None:
    """Register response-only actions exactly once."""
    has_service = getattr(hass.services, "has_service", None)
    if has_service is not None and has_service(DOMAIN, SERVICE_RESOLVE):
        return

    async def handle(call: Any) -> dict[str, Any]:
        return await _async_resolve_for_hass(hass, call)

    hass.services.async_register(
        DOMAIN,
        SERVICE_RESOLVE,
        handle,
        supports_response=SupportsResponse.ONLY,
    )


def async_remove_services(hass: Any) -> None:
    """Remove actions when the final config entry is unloaded."""
    has_service = getattr(hass.services, "has_service", None)
    if has_service is None or not has_service(DOMAIN, SERVICE_RESOLVE):
        return
    remove = getattr(hass.services, "async_remove", None)
    if remove is not None:
        remove(DOMAIN, SERVICE_RESOLVE)


async def async_maybe_await(value: Any) -> Any:
    """Accept a synchronous test loader while keeping HA setup fully async."""
    return await value if inspect.isawaitable(value) else value
