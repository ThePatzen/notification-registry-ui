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

    async def async_load(self):
        self.loaded = True

    def async_items(self):
        return list(self.items)

    async def async_create_item(self, item):
        self.created.append(item)
        self.items.append({"id": str(len(self.items) + 1), **item})


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
            "url": "/notification_registry/notification-registry-card.js?v=0.1.0",
        }
    ]


@pytest.mark.asyncio
async def test_does_not_modify_yaml_resources(hass):
    hass.data["lovelace"].resource_mode = "yaml"

    await async_register_frontend(hass)

    assert hass.data["lovelace"].resources.created == []
