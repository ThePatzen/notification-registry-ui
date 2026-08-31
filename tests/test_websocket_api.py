from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.notification_registry.reference import async_find_references
from custom_components.notification_registry.registry import NotificationRegistry
from custom_components.notification_registry.storage import RegistryStorage
from custom_components.notification_registry.websocket_api import (
    async_handle_create,
    async_handle_delete,
    async_handle_list,
    async_handle_references,
    async_handle_rename,
    async_handle_update,
)


class MemoryStore:
    def __init__(self, data=None):
        self.data = data

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        self.data = data


class Connection:
    def __init__(self):
        self.messages = []

    def send_message(self, message):
        self.messages.append(message)

    def send_result(self, msg_id, result):
        self.messages.append(
            {"id": msg_id, "type": "result", "success": True, "result": result}
        )

    def send_error(self, msg_id, code, message, *args, **kwargs):
        self.messages.append(
            {
                "id": msg_id,
                "type": "result",
                "success": False,
                "error": {"code": code, "message": message, **kwargs},
            }
        )


@pytest.fixture
async def registry(valid_entry):
    instance = await NotificationRegistry.async_create(RegistryStorage(MemoryStore()))
    await instance.create(valid_entry())
    return instance


@pytest.fixture
def hass(registry):
    return SimpleNamespace(
        data={"notification_registry": {"entry": registry}},
        states={
            "automation.water_alarm": SimpleNamespace(name="Water alarm"),
        },
    )


def message(connection):
    assert len(connection.messages) == 1
    return connection.messages[0]


@pytest.mark.asyncio
async def test_list_returns_confirmed_entries_and_data_revision(hass):
    connection = Connection()
    await async_handle_list(
        hass, connection, {"id": 1, "type": "notification_registry/list"}
    )

    response = message(connection)
    assert response["success"] is True
    assert response["result"]["data_revision"] == 1
    assert response["result"]["entries"][0]["key"] == "technikraum::wasseralarm"


@pytest.mark.asyncio
async def test_create_update_and_rename_return_confirmed_entry(hass, valid_entry):
    connection = Connection()
    await async_handle_create(
        hass,
        connection,
        {
            "id": 1,
            "type": "notification_registry/create",
            **valid_entry(key="test::new"),
        },
    )
    created = message(connection)["result"]["entry"]
    assert created["revision"] == 1

    connection = Connection()
    await async_handle_update(
        hass,
        connection,
        {
            "id": 2,
            "type": "notification_registry/update",
            "key": "test::new",
            "expected_revision": 1,
            "entry": {**created, "titel": "Changed"},
        },
    )
    updated = message(connection)["result"]["entry"]
    assert updated["titel"] == "Changed"
    assert updated["revision"] == 2

    connection = Connection()
    await async_handle_rename(
        hass,
        connection,
        {
            "id": 3,
            "type": "notification_registry/rename",
            "key": "test::new",
            "new_key": "test::renamed",
            "expected_revision": 2,
        },
    )
    assert message(connection)["result"]["entry"]["key"] == "test::renamed"


@pytest.mark.asyncio
async def test_stale_revision_returns_current_entry(hass, valid_entry):
    await hass.data["notification_registry"]["entry"].update(
        "technikraum::wasseralarm",
        {**valid_entry(), "titel": "Current"},
        expected_revision=1,
    )
    connection = Connection()
    await async_handle_update(
        hass,
        connection,
        {
            "id": 1,
            "type": "notification_registry/update",
            "key": "technikraum::wasseralarm",
            "expected_revision": 1,
            "entry": {**valid_entry(), "titel": "Stale"},
        },
    )
    error = message(connection)["error"]
    assert error["code"] == "revision_conflict"
    assert error["current"]["titel"] == "Current"


@pytest.mark.asyncio
async def test_referenced_key_cannot_be_deleted(hass):
    hass.data["automation"] = {
        "water_alarm": {
            "id": "water_alarm",
            "alias": "Water alarm",
            "action": [
                {
                    "service": "notify.mobile",
                    "data": {"message": "technikraum::wasseralarm"},
                }
            ],
        }
    }
    connection = Connection()
    await async_handle_delete(
        hass,
        connection,
        {
            "id": 1,
            "type": "notification_registry/delete",
            "key": "technikraum::wasseralarm",
            "expected_revision": 1,
        },
    )
    error = message(connection)["error"]
    assert error["code"] == "key_in_use"
    assert error["references"] == [
        {
            "entity_id": "automation.water_alarm",
            "friendly_name": "Water alarm",
            "path": "action[0].data.message",
        }
    ]
    assert hass.data["notification_registry"]["entry"].get("technikraum::wasseralarm")


@pytest.mark.asyncio
async def test_rename_requires_confirmation_but_does_not_mutate_references(hass):
    hass.data["script"] = {
        "send_water": {
            "id": "send_water",
            "alias": "Send water",
            "sequence": [
                {
                    "service": "notify.mobile",
                    "data": {"message": "technikraum::wasseralarm"},
                }
            ],
        }
    }
    connection = Connection()
    await async_handle_rename(
        hass,
        connection,
        {
            "id": 1,
            "type": "notification_registry/rename",
            "key": "technikraum::wasseralarm",
            "new_key": "technikraum::wasserwarnung",
            "expected_revision": 1,
        },
    )
    error = message(connection)["error"]
    assert error["code"] == "references_require_confirmation"
    assert error["references"][0]["entity_id"] == "script.send_water"
    assert hass.data["notification_registry"]["entry"].get("technikraum::wasseralarm")

    connection = Connection()
    await async_handle_references(
        hass,
        connection,
        {
            "id": 2,
            "type": "notification_registry/references",
            "key": "technikraum::wasseralarm",
        },
    )
    assert (
        message(connection)["result"]["references"][0]["path"]
        == "sequence[0].data.message"
    )


@pytest.mark.asyncio
async def test_invalid_entry_returns_validation_issues(hass, valid_entry):
    connection = Connection()
    await async_handle_create(
        hass,
        connection,
        {"id": 1, "type": "notification_registry/create", **valid_entry(titel="")},
    )
    error = message(connection)["error"]
    assert error["code"] == "validation_failed"
    assert any(issue["field"] == "titel" for issue in error["issues"])


@pytest.mark.asyncio
async def test_references_read_loaded_entity_components_raw_config(hass):
    entity = SimpleNamespace(
        entity_id="automation.component_water",
        name="Component water",
        raw_config={
            "alias": "Component water",
            "actions": [{"data": {"key": "technikraum::wasseralarm"}}],
        },
    )
    hass.data["automation"] = SimpleNamespace(entities=[entity])
    references = await async_find_references(hass, "technikraum::wasseralarm")
    assert references == [
        {
            "entity_id": "automation.component_water",
            "friendly_name": "Component water",
            "path": "actions[0].data.key",
        }
    ]
