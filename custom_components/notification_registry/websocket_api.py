"""Admin-only WebSocket API for the notification registry."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .model import EntryValidationError
from .reference import async_find_references
from .registry import (
    DuplicateKeyError,
    NotificationRegistry,
    RegistrySaveError,
    RevisionConflict,
)
from .services import _registry_from_hass

try:  # HA imports are intentionally optional for focused API tests.
    from homeassistant.components import websocket_api
except ImportError:  # pragma: no cover - used by focused tests without HA

    class _FallbackWebsocket:
        @staticmethod
        def websocket_command(_schema: Any):
            return lambda function: function

        @staticmethod
        def async_response(function):
            return function

        @staticmethod
        def require_admin(function):
            return function

        @staticmethod
        def async_register_command(_hass: Any, _handler: Any) -> None:
            return None

    websocket_api = _FallbackWebsocket()

try:
    import voluptuous as vol
except ImportError:  # pragma: no cover - only used without HA dependencies

    class _FallbackVol:
        Required = staticmethod(lambda value: value)
        Optional = staticmethod(lambda value, **_kwargs: value)

    vol = _FallbackVol()


_REGISTERED_HASS_IDS: set[int] = set()
_CONTROL_FIELDS = {
    "id",
    "type",
    "expected_revision",
    "entry",
    "data",
    "confirm_references",
}


def _schema(command: str) -> dict[str, Any]:
    return {vol.Required("type"): command}


def _result(connection: Any, msg: Mapping[str, Any], result: dict[str, Any]) -> None:
    connection.send_result(msg.get("id"), result)


def _error(
    connection: Any, msg: Mapping[str, Any], code: str, message: str, **details: Any
) -> None:
    msg_id = msg.get("id")
    # ActiveConnection.send_message is the public escape hatch for the additional
    # typed error fields needed by the card (send_error itself has no details arg).
    if details:
        try:
            connection.send_error(msg_id, code, message, **details)
            return
        except TypeError:
            if hasattr(connection, "send_message"):
                connection.send_message(
                    {
                        "id": msg_id,
                        "type": "result",
                        "success": False,
                        "error": {"code": code, "message": message, **details},
                    }
                )
                return
    connection.send_error(msg_id, code, message)


def _issue(field: str, code: str, message: str) -> dict[str, str]:
    return {"field": field, "code": code, "message": message}


def _entry_payload(msg: Mapping[str, Any]) -> Mapping[str, Any]:
    for name in ("entry", "data"):
        value = msg.get(name)
        if isinstance(value, Mapping):
            return value
    return {key: value for key, value in msg.items() if key not in _CONTROL_FIELDS}


def _required_string(
    msg: Mapping[str, Any], name: str
) -> tuple[str | None, list[dict[str, str]]]:
    value = msg.get(name)
    if not isinstance(value, str) or not value.strip():
        return None, [_issue(name, "required", f"{name} darf nicht leer sein.")]
    return value.strip(), []


def _expected_revision(
    msg: Mapping[str, Any],
) -> tuple[int | None, list[dict[str, str]]]:
    value = msg.get("expected_revision")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None, [
            _issue(
                "expected_revision", "invalid_revision", "Revision muss positiv sein."
            )
        ]
    return value, []


def _registry_result(registry: NotificationRegistry) -> dict[str, Any]:
    snapshot = registry.snapshot()
    return {"data_revision": snapshot.data_revision}


@websocket_api.websocket_command(_schema("notification_registry/list"))
@websocket_api.require_admin
@websocket_api.async_response
async def async_handle_list(hass: Any, connection: Any, msg: Mapping[str, Any]) -> None:
    registry = _registry_from_hass(hass)
    snapshot = registry.snapshot()
    _result(
        connection,
        msg,
        {
            "entries": [entry.to_dict() for entry in snapshot.entries],
            "data_revision": snapshot.data_revision,
            "schema_version": snapshot.schema_version,
        },
    )


@websocket_api.websocket_command(_schema("notification_registry/get"))
@websocket_api.require_admin
@websocket_api.async_response
async def async_handle_get(hass: Any, connection: Any, msg: Mapping[str, Any]) -> None:
    key, issues = _required_string(msg, "key")
    if issues:
        _error(
            connection, msg, "validation_failed", "Ungültige Eingabe.", issues=issues
        )
        return
    registry = _registry_from_hass(hass)
    entry = registry.get(key)
    if entry is None:
        _error(connection, msg, "unknown_key", f"Unbekannter Key: {key}.")
        return
    _result(connection, msg, {"entry": entry.to_dict(), **_registry_result(registry)})


async def _create(hass: Any, connection: Any, msg: Mapping[str, Any]) -> None:
    registry = _registry_from_hass(hass)
    try:
        entry = await registry.create(_entry_payload(msg))
    except EntryValidationError as err:
        _error(
            connection,
            msg,
            "validation_failed",
            "Ungültige Eingabe.",
            issues=[issue.__dict__ for issue in err.issues],
        )
        return
    except DuplicateKeyError as err:
        _error(connection, msg, "duplicate_key", str(err))
        return
    except (TypeError, ValueError) as err:
        _error(
            connection,
            msg,
            "validation_failed",
            str(err),
            issues=[_issue("entry", "invalid", str(err))],
        )
        return
    except RegistrySaveError as err:
        _error(connection, msg, "save_failed", str(err))
        return
    _result(connection, msg, {"entry": entry.to_dict(), **_registry_result(registry)})


@websocket_api.websocket_command(_schema("notification_registry/create"))
@websocket_api.require_admin
@websocket_api.async_response
async def async_handle_create(
    hass: Any, connection: Any, msg: Mapping[str, Any]
) -> None:
    await _create(hass, connection, msg)


async def _update(hass: Any, connection: Any, msg: Mapping[str, Any]) -> None:
    key, issues = _required_string(msg, "key")
    revision, revision_issues = _expected_revision(msg)
    issues += revision_issues
    if issues:
        _error(
            connection, msg, "validation_failed", "Ungültige Eingabe.", issues=issues
        )
        return
    registry = _registry_from_hass(hass)
    try:
        entry = await registry.update(key, _entry_payload(msg), revision)
    except RevisionConflict as err:
        _error(
            connection,
            msg,
            "revision_conflict",
            str(err),
            current=err.current.to_dict(),
        )
        return
    except KeyError:
        _error(connection, msg, "unknown_key", f"Unbekannter Key: {key}.")
        return
    except EntryValidationError as err:
        _error(
            connection,
            msg,
            "validation_failed",
            "Ungültige Eingabe.",
            issues=[issue.__dict__ for issue in err.issues],
        )
        return
    except RegistrySaveError as err:
        _error(connection, msg, "save_failed", str(err))
        return
    _result(connection, msg, {"entry": entry.to_dict(), **_registry_result(registry)})


@websocket_api.websocket_command(_schema("notification_registry/update"))
@websocket_api.require_admin
@websocket_api.async_response
async def async_handle_update(
    hass: Any, connection: Any, msg: Mapping[str, Any]
) -> None:
    await _update(hass, connection, msg)


@websocket_api.websocket_command(_schema("notification_registry/duplicate"))
@websocket_api.require_admin
@websocket_api.async_response
async def async_handle_duplicate(
    hass: Any, connection: Any, msg: Mapping[str, Any]
) -> None:
    source_value = msg.get("source_key", msg.get("key"))
    source, issues = _required_string({"source_key": source_value}, "source_key")
    new_key, new_issues = _required_string(msg, "new_key")
    if issues or new_issues:
        _error(
            connection,
            msg,
            "validation_failed",
            "Ungültige Eingabe.",
            issues=issues + new_issues,
        )
        return
    registry = _registry_from_hass(hass)
    try:
        entry = await registry.duplicate(source, new_key)
    except KeyError:
        _error(connection, msg, "unknown_key", f"Unbekannter Key: {source}.")
        return
    except DuplicateKeyError as err:
        _error(connection, msg, "duplicate_key", str(err))
        return
    except EntryValidationError as err:
        _error(
            connection,
            msg,
            "validation_failed",
            "Ungültige Eingabe.",
            issues=[issue.__dict__ for issue in err.issues],
        )
        return
    _result(connection, msg, {"entry": entry.to_dict(), **_registry_result(registry)})


@websocket_api.websocket_command(_schema("notification_registry/references"))
@websocket_api.require_admin
@websocket_api.async_response
async def async_handle_references(
    hass: Any, connection: Any, msg: Mapping[str, Any]
) -> None:
    key, issues = _required_string(msg, "key")
    if issues:
        _error(
            connection, msg, "validation_failed", "Ungültige Eingabe.", issues=issues
        )
        return
    registry = _registry_from_hass(hass)
    if registry.get(key) is None:
        _error(connection, msg, "unknown_key", f"Unbekannter Key: {key}.")
        return
    _result(
        connection,
        msg,
        {
            "key": key,
            "references": await async_find_references(hass, key),
            **_registry_result(registry),
        },
    )


async def _rename(hass: Any, connection: Any, msg: Mapping[str, Any]) -> None:
    old_key, issues = _required_string(msg, "key")
    new_key, new_issues = _required_string(msg, "new_key")
    revision, revision_issues = _expected_revision(msg)
    issues += new_issues + revision_issues
    if issues:
        _error(
            connection, msg, "validation_failed", "Ungültige Eingabe.", issues=issues
        )
        return
    registry = _registry_from_hass(hass)
    if registry.get(old_key) is None:
        _error(connection, msg, "unknown_key", f"Unbekannter Key: {old_key}.")
        return
    references = await async_find_references(hass, old_key)
    if references and msg.get("confirm_references") is not True:
        _error(
            connection,
            msg,
            "references_require_confirmation",
            "Referenzen müssen bestätigt werden.",
            references=references,
        )
        return
    try:
        entry = await registry.rename(old_key, new_key, revision)
    except RevisionConflict as err:
        _error(
            connection,
            msg,
            "revision_conflict",
            str(err),
            current=err.current.to_dict(),
        )
        return
    except DuplicateKeyError as err:
        _error(connection, msg, "duplicate_key", str(err))
        return
    except EntryValidationError as err:
        _error(
            connection,
            msg,
            "validation_failed",
            "Ungültige Eingabe.",
            issues=[issue.__dict__ for issue in err.issues],
        )
        return
    _result(connection, msg, {"entry": entry.to_dict(), **_registry_result(registry)})


@websocket_api.websocket_command(_schema("notification_registry/rename"))
@websocket_api.require_admin
@websocket_api.async_response
async def async_handle_rename(
    hass: Any, connection: Any, msg: Mapping[str, Any]
) -> None:
    await _rename(hass, connection, msg)


async def _delete(hass: Any, connection: Any, msg: Mapping[str, Any]) -> None:
    key, issues = _required_string(msg, "key")
    revision, revision_issues = _expected_revision(msg)
    issues += revision_issues
    if issues:
        _error(
            connection, msg, "validation_failed", "Ungültige Eingabe.", issues=issues
        )
        return
    registry = _registry_from_hass(hass)
    if registry.get(key) is None:
        _error(connection, msg, "unknown_key", f"Unbekannter Key: {key}.")
        return
    # This lookup is intentionally unconditional: deletion is never allowed to
    # skip reference protection, even when no matches are expected.
    references = await async_find_references(hass, key)
    if references:
        _error(
            connection,
            msg,
            "key_in_use",
            "Key wird noch verwendet.",
            references=references,
        )
        return
    try:
        await registry.delete(key, revision)
    except RevisionConflict as err:
        _error(
            connection,
            msg,
            "revision_conflict",
            str(err),
            current=err.current.to_dict(),
        )
        return
    _result(
        connection, msg, {"key": key, "deleted": True, **_registry_result(registry)}
    )


@websocket_api.websocket_command(_schema("notification_registry/delete"))
@websocket_api.require_admin
@websocket_api.async_response
async def async_handle_delete(
    hass: Any, connection: Any, msg: Mapping[str, Any]
) -> None:
    await _delete(hass, connection, msg)


COMMAND_HANDLERS = (
    async_handle_list,
    async_handle_get,
    async_handle_create,
    async_handle_update,
    async_handle_duplicate,
    async_handle_references,
    async_handle_rename,
    async_handle_delete,
)


def async_register_commands(hass: Any) -> None:
    """Register all commands once per Home Assistant instance."""
    identity = id(hass)
    if identity in _REGISTERED_HASS_IDS:
        return
    for handler in COMMAND_HANDLERS:
        websocket_api.async_register_command(hass, handler)
    _REGISTERED_HASS_IDS.add(identity)
