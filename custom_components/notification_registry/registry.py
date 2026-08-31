"""Validated, revisioned, copy-on-write notification registry."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from .model import NotificationEntry
from .storage import RegistrySnapshot, RegistryStorage, Store


class RegistryError(Exception):
    """Base class for registry operation errors."""


class RegistrySaveError(RegistryError):
    """Raised when a candidate snapshot could not be persisted."""


class RevisionConflict(RegistryError):
    def __init__(self, current: NotificationEntry):
        self.current = current
        super().__init__(f"Revision conflict for {current.key}.")


class DuplicateKeyError(RegistryError):
    """Raised when an operation would create an existing key."""


RegistryListener = Callable[[RegistrySnapshot], None]


class NotificationRegistry:
    def __init__(
        self,
        storage: RegistryStorage | Store,
        snapshot: RegistrySnapshot | None = None,
    ):
        self._storage = (
            storage
            if isinstance(storage, RegistryStorage)
            else RegistryStorage(storage)
        )
        self._snapshot = snapshot or RegistrySnapshot()
        self._lock = asyncio.Lock()
        self._listeners: list[RegistryListener] = []

    @classmethod
    async def async_create(
        cls, storage: RegistryStorage | Store
    ) -> NotificationRegistry:
        adapter = (
            storage
            if isinstance(storage, RegistryStorage)
            else RegistryStorage(storage)
        )
        return cls(adapter, await adapter.async_load())

    async def async_load(self) -> NotificationRegistry:
        """Reload the active snapshot and return this registry."""
        async with self._lock:
            self._snapshot = await self._storage.async_load()
        return self

    def snapshot(self) -> RegistrySnapshot:
        return self._snapshot

    def list_entries(self) -> list[NotificationEntry]:
        return list(self._snapshot.entries)

    def get(self, key: str) -> NotificationEntry | None:
        return next(
            (entry for entry in self._snapshot.entries if entry.key == key), None
        )

    def add_listener(self, listener: RegistryListener) -> Callable[[], None]:
        """Subscribe to snapshots after successful mutations.

        The returned callback is safe to invoke more than once. Listeners are
        synchronous and receive the already-swapped immutable snapshot.
        """
        self._listeners.append(listener)
        removed = False

        def remove_listener() -> None:
            nonlocal removed
            if removed:
                return
            removed = True
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass

        return remove_listener

    async def create(
        self, data: Mapping[str, Any] | NotificationEntry
    ) -> NotificationEntry:
        candidate = self._entry_from_data(data)
        async with self._lock:
            if self.get(candidate.key) is not None:
                raise DuplicateKeyError(f"Key already exists: {candidate.key}.")
            now = datetime.now(UTC)
            candidate = NotificationEntry.from_dict(
                {
                    **candidate.to_dict(),
                    "revision": 1,
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                }
            )
            entries = (*self._snapshot.entries, candidate)
            await self._persist_candidate(entries)
            return candidate

    async def update(
        self,
        key: str,
        data: Mapping[str, Any] | NotificationEntry,
        expected_revision: int,
    ) -> NotificationEntry:
        async with self._lock:
            current = self._require(key)
            self._check_revision(current, expected_revision)
            candidate_data = self._entry_from_data(data).to_dict()
            candidate_data["key"] = key
            candidate_data["revision"] = current.revision + 1
            candidate_data["created_at"] = current.created_at.isoformat()
            candidate_data["updated_at"] = datetime.now(UTC).isoformat()
            candidate = NotificationEntry.from_dict(candidate_data)
            entries = tuple(
                candidate if item.key == key else item
                for item in self._snapshot.entries
            )
            await self._persist_candidate(entries)
            return candidate

    async def duplicate(self, source_key: str, new_key: str) -> NotificationEntry:
        async with self._lock:
            source = self._require(source_key)
            normalized_key = new_key.strip() if isinstance(new_key, str) else new_key
            if self.get(normalized_key) is not None:
                raise DuplicateKeyError(f"Key already exists: {normalized_key}.")
            now = datetime.now(UTC)
            candidate = NotificationEntry.from_dict(
                {
                    **source.to_dict(),
                    "key": normalized_key,
                    "revision": 1,
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                }
            )
            await self._persist_candidate((*self._snapshot.entries, candidate))
            return candidate

    async def rename(
        self, old_key: str, new_key: str, expected_revision: int
    ) -> NotificationEntry:
        async with self._lock:
            current = self._require(old_key)
            self._check_revision(current, expected_revision)
            normalized_key = new_key.strip() if isinstance(new_key, str) else new_key
            if old_key != normalized_key and self.get(normalized_key) is not None:
                raise DuplicateKeyError(f"Key already exists: {normalized_key}.")
            candidate_data = {
                **current.to_dict(),
                "key": normalized_key,
                "revision": current.revision + 1,
            }
            candidate_data["updated_at"] = datetime.now(UTC).isoformat()
            candidate = NotificationEntry.from_dict(candidate_data)
            entries = tuple(
                candidate if item.key == old_key else item
                for item in self._snapshot.entries
            )
            await self._persist_candidate(entries)
            return candidate

    async def delete(self, key: str, expected_revision: int) -> None:
        async with self._lock:
            current = self._require(key)
            self._check_revision(current, expected_revision)
            entries = tuple(item for item in self._snapshot.entries if item.key != key)
            await self._persist_candidate(entries)

    def _entry_from_data(
        self, data: Mapping[str, Any] | NotificationEntry
    ) -> NotificationEntry:
        if isinstance(data, NotificationEntry):
            return data
        if not isinstance(data, Mapping):
            raise TypeError("Entry data must be a mapping.")
        return NotificationEntry.from_dict(data)

    def _require(self, key: str) -> NotificationEntry:
        current = self.get(key)
        if current is None:
            raise KeyError(key)
        return current

    @staticmethod
    def _check_revision(current: NotificationEntry, expected_revision: int) -> None:
        if current.revision != expected_revision:
            raise RevisionConflict(current)

    async def _persist_candidate(self, entries: tuple[NotificationEntry, ...]) -> None:
        candidate = RegistrySnapshot(
            schema_version=self._snapshot.schema_version,
            data_revision=self._snapshot.data_revision + 1,
            entries=entries,
            schema_minor_version=self._snapshot.schema_minor_version,
        )
        try:
            await self._storage.async_save(candidate)
        except Exception as err:
            raise RegistrySaveError("Could not save notification registry.") from err
        self._snapshot = candidate
        for listener in tuple(self._listeners):
            try:
                listener(candidate)
            except Exception:  # noqa: BLE001, S112
                # A diagnostic observer must not turn a committed mutation into
                # a failed one or roll back the in-memory snapshot.
                continue
