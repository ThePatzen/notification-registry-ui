from __future__ import annotations

import pytest

from custom_components.notification_registry.registry import (
    DuplicateKeyError,
    NotificationRegistry,
    RegistrySaveError,
    RevisionConflict,
)
from custom_components.notification_registry.storage import RegistryStorage


class MemoryStore:
    def __init__(self, data=None):
        self.data = data
        self.fail_next_save = False
        self.save_count = 0

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        self.save_count += 1
        if self.fail_next_save:
            self.fail_next_save = False
            raise OSError("disk full")
        self.data = data


@pytest.fixture
async def registry(valid_entry):
    store = MemoryStore()
    storage = RegistryStorage(store)
    return await NotificationRegistry.async_create(storage), store


@pytest.mark.asyncio
async def test_create_update_duplicate_rename_delete(registry, valid_entry):
    instance, _ = registry
    created = await instance.create(valid_entry(key="test::one"))
    assert created.revision == 1
    assert instance.get("test::one") == created

    updated = await instance.update(
        "test::one", {**created.to_dict(), "titel": "Neu"}, created.revision
    )
    assert updated.titel == "Neu"
    assert updated.revision == 2

    copied = await instance.duplicate("test::one", "test::copy")
    assert copied.key == "test::copy"
    assert copied.revision == 1
    renamed = await instance.rename("test::copy", "test::renamed", copied.revision)
    assert renamed.key == "test::renamed"
    await instance.delete("test::renamed", renamed.revision)
    assert instance.get("test::renamed") is None


@pytest.mark.asyncio
async def test_update_rejects_stale_revision(registry, valid_entry):
    instance, _ = registry
    created = await instance.create(valid_entry(key="test::one"))
    await instance.update(
        "test::one", {**created.to_dict(), "titel": "Neu"}, created.revision
    )
    with pytest.raises(RevisionConflict) as exc:
        await instance.update(
            "test::one", {**created.to_dict(), "titel": "Alt"}, created.revision
        )
    assert exc.value.current.titel == "Neu"


@pytest.mark.asyncio
async def test_failed_save_keeps_previous_snapshot(registry, valid_entry):
    instance, store = registry
    before = instance.snapshot()
    store.fail_next_save = True
    with pytest.raises(RegistrySaveError):
        await instance.create(valid_entry(key="test::failed"))
    assert instance.snapshot() == before
    assert instance.list_entries() == []


@pytest.mark.asyncio
async def test_duplicate_key_is_rejected_without_save(registry, valid_entry):
    instance, store = registry
    await instance.create(valid_entry(key="test::one"))
    saves = store.save_count
    with pytest.raises(DuplicateKeyError):
        await instance.create(valid_entry(key="test::one"))
    assert store.save_count == saves


@pytest.mark.asyncio
async def test_registry_can_reload_persisted_snapshot(valid_entry):
    store = MemoryStore()
    first = await NotificationRegistry.async_create(RegistryStorage(store))
    await first.create(valid_entry(key="test::one"))
    second = await NotificationRegistry.async_create(RegistryStorage(store))
    assert second.get("test::one").titel == "Wasseralarm"
    assert second.snapshot().data_revision == 1
