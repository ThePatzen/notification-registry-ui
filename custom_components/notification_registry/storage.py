"""Versioned persistence for the notification registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .model import NotificationEntry

STORE_KEY = "notification_registry.registry"
SCHEMA_VERSION = 1
SCHEMA_MINOR_VERSION = 1


class Store(Protocol):
    async def async_load(self) -> Any: ...

    async def async_save(self, data: Any) -> None: ...


class RegistrySchemaError(ValueError):
    """Raised when persisted registry data cannot be read safely."""


# Public spelling aliases keep callers independent of the implementation name.
StorageSchemaError = RegistrySchemaError
UnsupportedSchemaVersion = RegistrySchemaError


@dataclass(frozen=True)
class RegistrySnapshot:
    schema_version: int = SCHEMA_VERSION
    data_revision: int = 0
    entries: tuple[NotificationEntry, ...] = ()
    schema_minor_version: int = SCHEMA_MINOR_VERSION


class RegistryStorage:
    """Adapt a Home Assistant Store (or a small async test fake)."""

    def __init__(self, store: Store):
        self.store = store

    async def async_load(self) -> RegistrySnapshot:
        raw = await self.store.async_load()
        if raw is None:
            return RegistrySnapshot()
        if not isinstance(raw, dict):
            raise RegistrySchemaError("Registry store must contain an object.")

        major = raw.get("schema_version", SCHEMA_VERSION)
        if type(major) is not int:
            raise RegistrySchemaError("Invalid registry schema version.")
        if major > SCHEMA_VERSION:
            raise RegistrySchemaError(f"Unsupported registry schema version: {major}.")
        if major < 1:
            raise RegistrySchemaError(f"Unsupported registry schema version: {major}.")

        minor = raw.get("schema_minor_version", SCHEMA_MINOR_VERSION)
        if type(minor) is not int or minor < 0:
            raise RegistrySchemaError("Invalid registry schema minor version.")
        data_revision = raw.get("data_revision", 0)
        if type(data_revision) is not int or data_revision < 0:
            raise RegistrySchemaError("Invalid registry data revision.")
        raw_entries = raw.get("entries", [])
        if not isinstance(raw_entries, list):
            raise RegistrySchemaError("Registry entries must be a list.")

        entries: list[NotificationEntry] = []
        seen: set[str] = set()
        for raw_entry in raw_entries:
            if not isinstance(raw_entry, dict):
                raise RegistrySchemaError("Registry entry must be an object.")
            entry = NotificationEntry.from_dict(raw_entry)
            if entry.key in seen:
                raise RegistrySchemaError(f"Duplicate registry key: {entry.key}.")
            seen.add(entry.key)
            entries.append(entry)
        return RegistrySnapshot(major, data_revision, tuple(entries), minor)

    async def async_save(self, snapshot: RegistrySnapshot) -> None:
        payload = {
            "schema_version": snapshot.schema_version,
            "schema_minor_version": snapshot.schema_minor_version,
            "data_revision": snapshot.data_revision,
            "entries": [entry.to_dict() for entry in snapshot.entries],
        }
        await self.store.async_save(payload)


# A short alias is useful for callers that refer to this as the registry store.
RegistryStore = RegistryStorage
