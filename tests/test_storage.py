from __future__ import annotations

import pytest

from custom_components.notification_registry.model import (
    EntryValidationError,
    NotificationEntry,
)
from custom_components.notification_registry.storage import (
    RegistrySchemaError,
    RegistrySnapshot,
    RegistryStorage,
    SCHEMA_MINOR_VERSION,
    SCHEMA_VERSION,
    STORE_KEY,
)


class MemoryStore:
    def __init__(self, data=None):
        self.data = data
        self.saved = []

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        self.saved.append(data)
        self.data = data


@pytest.mark.asyncio
async def test_missing_store_loads_empty_snapshot():
    store = MemoryStore()
    snapshot = await RegistryStorage(store).async_load()
    assert snapshot == RegistrySnapshot(SCHEMA_VERSION, 0, ())


@pytest.mark.asyncio
async def test_store_round_trip_normalizes_entries(valid_entry):
    store = MemoryStore(
        {
            "schema_version": SCHEMA_VERSION,
            "schema_minor_version": SCHEMA_MINOR_VERSION,
            "data_revision": 4,
            "entries": [{**valid_entry(key="test::one"), "titel": " Alarm "}],
        }
    )
    snapshot = await RegistryStorage(store).async_load()
    assert snapshot.data_revision == 4
    assert snapshot.entries[0].titel == "Alarm"


@pytest.mark.asyncio
async def test_save_uses_versioned_store_payload(valid_entry):
    store = MemoryStore()
    storage = RegistryStorage(store)
    entry = NotificationEntry.from_dict(valid_entry(key="test::one"))
    await storage.async_save(RegistrySnapshot(1, 7, (entry,)))
    assert store.saved == [
        {
            "schema_version": 1,
            "schema_minor_version": 1,
            "data_revision": 7,
            "entries": [entry.to_dict()],
        }
    ]
    assert STORE_KEY == "notification_registry.registry"


@pytest.mark.asyncio
async def test_newer_major_schema_is_rejected():
    store = MemoryStore({"schema_version": SCHEMA_VERSION + 1, "entries": []})
    with pytest.raises(RegistrySchemaError):
        await RegistryStorage(store).async_load()


@pytest.mark.asyncio
async def test_invalid_stored_entry_is_rejected_without_normalization():
    store = MemoryStore(
        {
            "schema_version": SCHEMA_VERSION,
            "entries": [{"key": "not-valid"}],
        }
    )
    with pytest.raises(EntryValidationError):
        await RegistryStorage(store).async_load()
