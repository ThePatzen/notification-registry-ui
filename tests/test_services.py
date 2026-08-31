from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from custom_components.notification_registry import DOMAIN, async_setup_entry, services
from custom_components.notification_registry.model import NotificationEntry
from custom_components.notification_registry.registry import NotificationRegistry
from custom_components.notification_registry.storage import (
    RegistrySnapshot,
    RegistryStorage,
)


class FakeServices:
    def __init__(self):
        self.handlers = {}
        self.registrations = []

    def async_register(self, domain, service, handler, **kwargs):
        self.handlers[(domain, service)] = handler
        self.registrations.append((domain, service, kwargs))

    def has_service(self, domain, service):
        return (domain, service) in self.handlers

    def async_remove(self, domain, service):
        self.handlers.pop((domain, service), None)

    async def async_call(
        self, domain, service, data, *, blocking=False, return_response=False
    ):
        response = await self.handlers[(domain, service)](SimpleNamespace(data=data))
        return response if return_response else None


class MemoryStore:
    async def async_load(self):
        return None

    async def async_save(self, data):
        self.data = data


class FakeConfigEntries:
    def __init__(self):
        self.unload_calls = 0

    async def async_forward_entry_setups(self, entry, platforms):
        return True

    async def async_unload_platforms(self, entry, platforms):
        self.unload_calls += 1
        return True


@dataclass
class FakeHass:
    services: FakeServices
    config_entries: FakeConfigEntries
    data: dict


@pytest.fixture
async def setup_integration(monkeypatch):
    hass = FakeHass(FakeServices(), FakeConfigEntries(), {})
    entry = SimpleNamespace(entry_id="test-entry")
    source = NotificationEntry.from_dict(
        {
            "key": "technikraum::wasseralarm",
            "titel": "Wasseralarm",
            "text": "Wasser bei {geraet}",
            "schweregrad": "kritisch",
            "zielgruppe": "david",
            "kanaele": ["mobil", "persistent"],
            "tag": "wasseralarm",
        }
    )
    registry = NotificationRegistry(
        RegistryStorage(MemoryStore()),
        RegistrySnapshot(entries=(source,), data_revision=7),
    )
    monkeypatch.setattr(
        services, "_async_load_registry", lambda _hass, _entry: registry
    )
    await async_setup_entry(hass, entry)
    return hass


@pytest.mark.asyncio
async def test_setup_entry_is_idempotent(setup_integration):
    from custom_components.notification_registry import async_setup_entry

    entry = SimpleNamespace(entry_id="test-entry")
    await async_setup_entry(setup_integration, entry)

    assert len(setup_integration.services.registrations) == 1


@pytest.mark.asyncio
async def test_unload_entry_removes_final_service(setup_integration):
    from custom_components.notification_registry import async_unload_entry

    entry = SimpleNamespace(entry_id="test-entry")
    assert await async_unload_entry(setup_integration, entry) is True
    assert not setup_integration.services.has_service(DOMAIN, "resolve")
    assert DOMAIN not in setup_integration.data


@pytest.mark.asyncio
async def test_resolve_service_returns_notification(setup_integration):
    response = await setup_integration.services.async_call(
        DOMAIN,
        "resolve",
        {"key": "technikraum::wasseralarm", "payload": {}},
        blocking=True,
        return_response=True,
    )

    assert response["schweregrad"] == "kritisch"
    assert response["kanaele"] == ["mobil", "persistent"]


@pytest.mark.asyncio
async def test_resolve_service_rejects_unknown_key(setup_integration):
    with pytest.raises(services.HomeAssistantError, match="unknown_key"):
        await setup_integration.services.async_call(
            DOMAIN,
            "resolve",
            {"key": "technikraum::missing", "payload": {}},
            blocking=True,
            return_response=True,
        )


@pytest.mark.asyncio
async def test_resolve_service_serializes_missing_placeholders(setup_integration):
    response = await setup_integration.services.async_call(
        DOMAIN,
        "resolve",
        {"key": "technikraum::wasseralarm"},
        return_response=True,
    )

    assert response["text"] == "Wasser bei {geraet}"
    assert response["missing_placeholders"] == ["geraet"]


@pytest.mark.asyncio
async def test_resolve_service_is_response_only(setup_integration):
    registration = setup_integration.services.registrations[0]
    assert registration[2]["supports_response"].name == "ONLY"


@pytest.mark.asyncio
async def test_resolve_service_schema_validates_key_and_payload(setup_integration):
    schema = setup_integration.services.registrations[0][2]["schema"]

    assert schema({"key": "technikraum::wasseralarm"})["payload"] == {}
    with pytest.raises(Exception):  # noqa: B017
        schema({"key": ""})
    with pytest.raises(Exception):  # noqa: B017
        schema({"key": 42})
    with pytest.raises(Exception):  # noqa: B017
        schema({"key": "technikraum::wasseralarm", "payload": []})


@pytest.mark.asyncio
async def test_resolve_service_reports_unavailable_registry():
    from custom_components.notification_registry import services

    hass = FakeHass(FakeServices(), FakeConfigEntries(), {})
    services.async_register_services(hass)
    with pytest.raises(services.HomeAssistantError, match="registry_unavailable"):
        await hass.services.async_call(
            DOMAIN,
            "resolve",
            {"key": "technikraum::wasseralarm"},
            return_response=True,
        )
