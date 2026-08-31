"""Diagnostic sensor for registry health and revision metadata."""

from __future__ import annotations

from typing import Any

from .const import DOMAIN

try:
    from homeassistant.components.sensor import SensorEntity
    from homeassistant.helpers.entity import Entity
except ImportError:  # pragma: no cover - used by focused tests without HA

    class Entity:
        _attr_entity_id = None

        @property
        def entity_id(self) -> str:
            return self._attr_entity_id

    class SensorEntity(Entity):
        @property
        def native_value(self) -> Any:
            return None

        @property
        def extra_state_attributes(self) -> dict[str, Any]:
            return {}


class NotificationRegistrySensor(SensorEntity):
    """Expose count and storage metadata, never notification content."""

    _attr_entity_id = "sensor.benachrichtigungs_registry"
    _attr_name = "Benachrichtigungs-Registry"
    _attr_unique_id = "notification_registry_diagnostic"
    _attr_should_poll = False

    def __init__(self, registry: Any):
        self._registry = registry
        self._attr_available = True

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
