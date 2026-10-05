"""Tests for the bundled Lovelace card transport."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from custom_components.notification_registry.const import URL_BASE
from custom_components.notification_registry.frontend import async_register_frontend


class FakeHttp:
    def __init__(self) -> None:
        self.static_paths = []

    async def async_register_static_paths(self, configs):
        self.static_paths.extend(configs)


class FakeResources:
    def __init__(self, *, loaded=False, items=None) -> None:
        self.loaded = loaded
        self.items = list(items or [])
        self.created = []
        self.updated = []
        self.fail_create = False

    async def async_load(self):
        self.loaded = True

    def async_items(self):
        return list(self.items)

    async def async_create_item(self, item):
        if self.fail_create:
            raise RuntimeError("resource storage unavailable")
        self.created.append(item)
        self.items.append({"id": str(len(self.items) + 1), **item})

    async def async_update_item(self, item_id, updates):
        self.updated.append((item_id, updates))


@pytest.fixture
def hass():
    resources = FakeResources()
    return SimpleNamespace(
        http=FakeHttp(),
        data={"lovelace": SimpleNamespace(resource_mode="storage", resources=resources)},
    )


@pytest.mark.asyncio
async def test_registers_bundled_card_path(hass):
    await async_register_frontend(hass)

    assert len(hass.http.static_paths) == 1
    config = hass.http.static_paths[0]
    assert config.url_path == URL_BASE
    assert Path(config.path).parts[-2:] == ("notification_registry", "frontend")


@pytest.mark.asyncio
async def test_registers_lovelace_resource_once_after_loading(hass):
    resources = hass.data["lovelace"].resources

    await async_register_frontend(hass)
    await async_register_frontend(hass)

    assert resources.created == [
        {
            "res_type": "module",
            "url": "/notification_registry/notification-registry-card.js?v=0.1.1",
        }
    ]


@pytest.mark.asyncio
async def test_updates_existing_resource_with_stale_version(hass):
    resources = hass.data["lovelace"].resources
    resources.loaded = True
    resources.items = [
        {
            "id": "legacy-card",
            "res_type": "module",
            "url": "/notification_registry/notification-registry-card.js?v=0.0.9",
        }
    ]

    await async_register_frontend(hass)

    assert resources.created == []
    assert resources.updated == [
        (
            "legacy-card",
            {
                "res_type": "module",
                "url": "/notification_registry/notification-registry-card.js?v=0.1.1",
            },
        )
    ]


@pytest.mark.asyncio
async def test_lovelace_resource_write_failure_does_not_block_setup(hass):
    resources = hass.data["lovelace"].resources
    resources.fail_create = True

    await async_register_frontend(hass)

    assert hass.data["notification_registry_frontend"]["_frontend_registered"] is True


@pytest.mark.asyncio
async def test_does_not_modify_yaml_resources(hass):
    hass.data["lovelace"].resource_mode = "yaml"

    await async_register_frontend(hass)

    assert hass.data["lovelace"].resources.created == []
