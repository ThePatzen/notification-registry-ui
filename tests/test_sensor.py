from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.notification_registry.model import NotificationEntry
from custom_components.notification_registry.registry import NotificationRegistry
from custom_components.notification_registry.sensor import async_setup_entry
from custom_components.notification_registry.storage import (
    RegistrySnapshot,
    RegistryStorage,
)


class MemoryStore:
    async def async_load(self):
        return None

    async def async_save(self, data):
        self.data = data


class FakeStates(dict):
    def set(self, entity_id, state, attributes=None):
        self[entity_id] = SimpleNamespace(state=str(state), attributes=attributes or {})


class FakeHass:
    def __init__(self, registry):
        self.data = {"notification_registry": {"test-entry": registry}}
        self.states = FakeStates()


@pytest.mark.asyncio
async def test_sensor_exposes_metadata_only():
    entry = NotificationEntry.from_dict(
        {
            "key": "test::one",
            "titel": "Test",
            "text": "Test",
            "schweregrad": "info",
            "zielgruppe": "alle",
            "kanaele": ["persistent"],
            "tag": "test",
        }
    )
    registry = NotificationRegistry(
        RegistryStorage(MemoryStore()),
        RegistrySnapshot(entries=(entry,), data_revision=3),
    )
    hass = FakeHass(registry)
    entities = []

    def add_entities(new_entities):
        entities.extend(new_entities)
        for entity in new_entities:
            hass.states.set(
                entity.entity_id,
                entity.native_value,
                entity.extra_state_attributes,
            )

    await async_setup_entry(hass, SimpleNamespace(entry_id="test-entry"), add_entities)

    state = hass.states["sensor.benachrichtigungs_registry"]
    assert int(state.state) > 0
    assert entities[0].name == "Benachrichtigungs-Registry"
    assert "entries" not in state.attributes
    assert state.attributes["data_revision"] == 3
    assert state.attributes["schema_version"] == 1
    assert state.attributes["available"] is True


@pytest.mark.asyncio
async def test_sensor_writes_state_after_registry_commit_and_unsubscribes():
    registry = NotificationRegistry(RegistryStorage(MemoryStore()), RegistrySnapshot())
    hass = FakeHass(registry)
    writes = []
    sensor = None

    def add_entities(new_entities):
        nonlocal sensor
        sensor = new_entities[0]
        hass.states.set(
            sensor.entity_id, sensor.native_value, sensor.extra_state_attributes
        )
        sensor.hass = hass
        sensor.async_write_ha_state = lambda: writes.append(sensor.native_value)

    await async_setup_entry(hass, SimpleNamespace(entry_id="test-entry"), add_entities)
    await sensor.async_added_to_hass()
    await registry.create(
        NotificationEntry.from_dict(
            {
                "key": "test::one",
                "titel": "Test",
                "text": "Test",
                "schweregrad": "info",
                "zielgruppe": "alle",
                "kanaele": ["persistent"],
            }
        )
    )
    assert writes == [1]

    await sensor.async_will_remove_from_hass()
    await registry.create(
        NotificationEntry.from_dict(
            {
                "key": "test::two",
                "titel": "Test",
                "text": "Test",
                "schweregrad": "info",
                "zielgruppe": "alle",
                "kanaele": ["persistent"],
            }
        )
    )
    assert writes == [1]
