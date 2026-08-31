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

    class _Required(str):
        required = True

    class _Optional(str):
        required = False

    class _FallbackSchema:
        def __init__(self, schema: Any):
            self.schema = schema

        def __call__(self, data: Any) -> dict[str, Any]:
            if not isinstance(data, Mapping):
                raise TypeError("WebSocket message must be an object")
            output = dict(data)
            for marker, validator in self.schema.items():
                name = str(marker)
                if getattr(marker, "required", False) and name not in data:
                    raise ValueError(f"required key not provided: {name}")
                if name not in data:
                    continue
                _fallback_validate(data[name], validator, name)
            declared = {str(marker) for marker in self.schema}
            declared.update({"id"})
            if any(name not in declared for name in data):
                raise ValueError("extra keys not allowed")
            return output

    class _FallbackCombined:
        def __init__(self, validators: tuple[Any, ...]):
            self.validators = validators
            first = validators[0] if validators else None
            self.command = (
                str(first.schema.get("type"))
                if isinstance(first, _FallbackSchema)
                else ""
            )

        def __call__(self, data: Any) -> Mapping[str, Any]:
            result = data
            for validator in self.validators:
                if callable(validator):
                    result = validator(result)
            return result

    def _fallback_validate(value: Any, validator: Any, field: str) -> None:
        if isinstance(validator, tuple):
            for candidate in validator:
                try:
                    _fallback_validate(value, candidate, field)
                    return
                except (TypeError, ValueError):
                    continue
            raise TypeError(f"{field} has an invalid type")
        if validator is None:
            if value is not None:
                raise TypeError(f"{field} must be null")
            return
        if isinstance(validator, str):
            if value != validator:
                raise ValueError(f"{field} has an invalid value")
            return
        if validator is str and not isinstance(value, str):
            raise TypeError(f"{field} must be a string")
        if validator is int and (isinstance(value, bool) or not isinstance(value, int)):
            raise TypeError(f"{field} must be an integer")
        if validator is dict and not isinstance(value, Mapping):
            raise TypeError(f"{field} must be an object")
        if isinstance(validator, list):
            if not isinstance(value, list):
                raise TypeError(f"{field} must be a list")
            for child in value:
                _fallback_validate(child, validator[0], field)
        if isinstance(validator, _FallbackSchema):
            validator(value)
            return
        if callable(validator):
            validator(value)

    class _FallbackWebsocket:
        @staticmethod
        def websocket_command(schema: Any):
            def decorate(function: Any) -> Any:
                function._ws_schema = (
                    _FallbackSchema(schema) if isinstance(schema, dict) else schema
                )
                function._ws_command = (
                    str(schema.get("type"))
                    if isinstance(schema, dict)
                    else getattr(schema, "command", "")
                )
                return function

            return decorate

        @staticmethod
        def async_response(function):
            return function

        @staticmethod
        def require_admin(function):
            function._requires_admin = True
            return function

        @staticmethod
        def async_register_command(_hass: Any, _handler: Any) -> None:
            return None

    websocket_api = _FallbackWebsocket()

try:
    import voluptuous as vol
except ImportError:  # pragma: no cover - only used without HA dependencies

    class _FallbackVol:
        Required = staticmethod(lambda value: _Required(value))
        Optional = staticmethod(lambda value, **_kwargs: _Optional(value))
        Schema = _FallbackSchema

        @staticmethod
        def Any(*validators: Any) -> Any:
            return validators

        @staticmethod
        def All(*validators: Any) -> Any:
            return _FallbackCombined(validators)

        Invalid = ValueError

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


def _positive_integer(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise vol.Invalid("must be a positive integer")
    return value


_ENTRY_FIELDS = {
    vol.Required("key"): str,
    vol.Required("titel"): str,
    vol.Required("text"): str,
    vol.Required("schweregrad"): str,
    vol.Required("zielgruppe"): str,
    vol.Required("kanaele"): [str],
    vol.Optional("tag"): vol.Any(str, None),
    vol.Optional("revision"): _positive_integer,
    vol.Optional("created_at"): str,
    vol.Optional("updated_at"): str,
}


def _entry_schema() -> Any:
    return vol.Schema(_ENTRY_FIELDS)


def _validate_entry_message(data: Mapping[str, Any]) -> Mapping[str, Any]:
    entry = data.get("entry", data.get("data"))
    if isinstance(entry, Mapping):
        _entry_schema()(entry)
        return data
    if all(
        name in data
        for name in ("key", "titel", "text", "schweregrad", "zielgruppe", "kanaele")
    ):
        _entry_schema()(
            {
                name: data[name]
                for name in (
                    "key",
                    "titel",
                    "text",
                    "schweregrad",
                    "zielgruppe",
                    "kanaele",
                    "tag",
                    "revision",
                    "created_at",
                    "updated_at",
                )
                if name in data
            }
        )
        return data
    raise vol.Invalid("entry or complete entry fields are required")


def _schema(command: str) -> Any:
    base: dict[Any, Any] = {vol.Required("type"): command}
    if command == "notification_registry/list":
        return base
    if command in {
        "notification_registry/get",
        "notification_registry/references",
    }:
        base[vol.Required("key")] = str
    elif command == "notification_registry/create":
        base.update(
            {
                vol.Optional("entry"): _entry_schema(),
                vol.Optional("data"): _entry_schema(),
            }
        )
        base.update(
            {
                vol.Optional(str(marker)): validator
                for marker, validator in _ENTRY_FIELDS.items()
            }
        )
        return vol.All(vol.Schema(base), _validate_entry_message)
    elif command == "notification_registry/update":
        base.update(
            {
                vol.Required("key"): str,
                vol.Required("expected_revision"): _positive_integer,
                vol.Optional("entry"): _entry_schema(),
                vol.Optional("data"): _entry_schema(),
            }
        )
        base.update(
            {
                vol.Optional(str(marker)): validator
                for marker, validator in _ENTRY_FIELDS.items()
                if str(marker) not in {"key", "revision"}
            }
        )
        return vol.All(vol.Schema(base), _validate_entry_message)
    elif command == "notification_registry/duplicate":
        base.update({vol.Required("source_key"): str, vol.Required("new_key"): str})
    elif command == "notification_registry/rename":
        base.update(
            {
                vol.Required("key"): str,
                vol.Required("new_key"): str,
                vol.Required("expected_revision"): _positive_integer,
                vol.Optional("confirm_references"): bool,
            }
        )
    elif command == "notification_registry/delete":
        base.update(
            {
                vol.Required("key"): str,
                vol.Required("expected_revision"): _positive_integer,
            }
        )
    return base


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


@websocket_api.require_admin
@websocket_api.websocket_command(_schema("notification_registry/list"))
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


@websocket_api.require_admin
@websocket_api.websocket_command(_schema("notification_registry/get"))
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


@websocket_api.require_admin
@websocket_api.websocket_command(_schema("notification_registry/create"))
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


@websocket_api.require_admin
@websocket_api.websocket_command(_schema("notification_registry/update"))
@websocket_api.async_response
async def async_handle_update(
    hass: Any, connection: Any, msg: Mapping[str, Any]
) -> None:
    await _update(hass, connection, msg)


@websocket_api.require_admin
@websocket_api.websocket_command(_schema("notification_registry/duplicate"))
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
    except RegistrySaveError as err:
        _error(connection, msg, "save_failed", str(err))
        return
    _result(connection, msg, {"entry": entry.to_dict(), **_registry_result(registry)})


@websocket_api.require_admin
@websocket_api.websocket_command(_schema("notification_registry/references"))
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
    current = registry.get(old_key)
    if current is not None and current.revision != revision:
        _error(
            connection,
            msg,
            "revision_conflict",
            f"Revision conflict for {old_key}.",
            current=current.to_dict(),
        )
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
    except RegistrySaveError as err:
        _error(connection, msg, "save_failed", str(err))
        return
    _result(connection, msg, {"entry": entry.to_dict(), **_registry_result(registry)})


@websocket_api.require_admin
@websocket_api.websocket_command(_schema("notification_registry/rename"))
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
    current = registry.get(key)
    if current is not None and current.revision != revision:
        _error(
            connection,
            msg,
            "revision_conflict",
            f"Revision conflict for {key}.",
            current=current.to_dict(),
        )
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
    except RegistrySaveError as err:
        _error(connection, msg, "save_failed", str(err))
        return
    _result(
        connection, msg, {"key": key, "deleted": True, **_registry_result(registry)}
    )


@websocket_api.require_admin
@websocket_api.websocket_command(_schema("notification_registry/delete"))
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
