"""Diagnostic sensor for registry health and revision metadata."""

from __future__ import annotations

import re
from typing import Any

from .const import DOMAIN

try:
    from homeassistant.components.sensor import SensorEntity
    from homeassistant.helpers.entity import Entity
except ImportError:  # pragma: no cover - used by focused tests without HA

    class Entity:
        _attr_name = None
        hass = None

        @property
        def name(self) -> str | None:
            return self._attr_name

        @property
        def entity_id(self) -> str:
            object_id = re.sub(
                r"[^a-z0-9]+", "_", (self.name or "entity").lower()
            ).strip("_")
            return f"sensor.{object_id}"

        async def async_added_to_hass(self) -> None:
            return None

        async def async_will_remove_from_hass(self) -> None:
            return None

        def async_write_ha_state(self) -> None:
            return None

    class SensorEntity(Entity):
        @property
        def native_value(self) -> Any:
            return None

        @property
        def extra_state_attributes(self) -> dict[str, Any]:
            return {}


class NotificationRegistrySensor(SensorEntity):
    """Expose count and storage metadata, never notification content."""

    _attr_name = "Benachrichtigungs-Registry"
    _attr_has_entity_name = True
    _attr_translation_key = "notification_registry_diagnostic"
    _attr_unique_id = "notification_registry_diagnostic"
    _attr_should_poll = False

    def __init__(self, registry: Any):
        self._registry = registry
        self._attr_available = True
        self._remove_registry_listener = None

    def _registry_changed(self, _snapshot: Any) -> None:
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._remove_registry_listener = self._registry.add_listener(
            self._registry_changed
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_registry_listener is not None:
            self._remove_registry_listener()
            self._remove_registry_listener = None
        await super().async_will_remove_from_hass()

    @property
    def native_value(self) -> int:
        return len(self._registry.list_entries())

    @property
    def available(self) -> bool:
        return self._attr_available

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        snapshot = self._registry.snapshot()
        updated = [entry.updated_at for entry in snapshot.entries if entry.updated_at]
        last_updated = max(updated).isoformat() if updated else None
        return {
            "data_revision": snapshot.data_revision,
            "schema_version": snapshot.schema_version,
            "last_updated": last_updated,
            "available": self.available,
        }


async def async_setup_entry(hass: Any, entry: Any, async_add_entities: Any) -> None:
    registry = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([NotificationRegistrySensor(registry)])
