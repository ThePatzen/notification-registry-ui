from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.notification_registry.model import (
    EntryValidationError,
    NotificationEntry,
)
from custom_components.notification_registry.storage import (
    SCHEMA_MINOR_VERSION,
    SCHEMA_VERSION,
    STORE_KEY,
    RegistrySchemaError,
    RegistrySnapshot,
    RegistryStorage,
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


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["schema_version", "data_revision"])
async def test_boolean_version_values_are_rejected(field):
    store = MemoryStore({"schema_version": 1, "entries": []})
    store.data[field] = True
    with pytest.raises(RegistrySchemaError):
        await RegistryStorage(store).async_load()


EXPECTED_INITIAL_KEYS = [
    "backofen::beendet",
    "backofen::tuer_offen",
    "backup::automatisches_backup_fehlgeschlagen",
    "backup::automatisches_backup_ok",
    "downloader::dienst_ausgefallen",
    "geschirrspueler::abgebrochen",
    "geschirrspueler::beendet",
    "geschirrspueler::tuer_offen",
    "goe::http_api_fehler",
    "kaffeemaschine::bohnen_nachfuellen",
    "kaffeemaschine::bohnen_ok",
    "kaffeemaschine::tropfschale_ok",
    "kaffeemaschine::tropfschale_problem",
    "kaffeemaschine::wassertank_ok",
    "kaffeemaschine::wassertank_problem",
    "kehrrobi::wartung_erforderlich",
    "kehrrobi::wartung_ok",
    "klima::aussentemperatur_kuehler",
    "klima::aussentemperatur_waermer",
    "pv_warmwasser::boost_gestartet",
    "raffstore::nicht_verfuegbar",
    "raffstore::nicht_verfuegbar_durchsage",
    "system::automation_state_ok",
    "system::automation_state_ungueltig",
    "technikraum::infrastruktur_ausgefallen",
    "technikraum::racktemperatur_hoch",
    "technikraum::stoerung",
    "technikraum::stromnetz_ausgefallen",
    "technikraum::wasseralarm",
    "wartung::taegliche_uebersicht",
    "waschmaschine::abgebrochen",
    "waschmaschine::beendet",
    "waschmaschine::tuer_offen",
]


@pytest.mark.asyncio
async def test_missing_store_imports_exact_live_registry():
    store = MemoryStore()

    snapshot = await RegistryStorage(store).async_load_or_import()

    assert len(snapshot.entries) == 33
    assert [entry.key for entry in snapshot.entries] == EXPECTED_INITIAL_KEYS
    assert store.data["import_completed"] is True
    assert len(store.saved) == 1


@pytest.mark.asyncio
async def test_import_is_idempotent_after_completion_marker_is_saved():
    store = MemoryStore()
    storage = RegistryStorage(store)

    first = await storage.async_load_or_import()
    second = await storage.async_load_or_import()

    assert second == first
    assert len(store.saved) == 1


@pytest.mark.asyncio
async def test_existing_store_ignores_import_file():
    store = MemoryStore(
        {
            "schema_version": SCHEMA_VERSION,
            "entries": [],
            "import_completed": False,
        }
    )
    import_file = Path(__file__).with_name("_existing_initial_registry.json")
    try:
        import_file.write_text(
            json.dumps(
                [
                    {
                        "key": "test::imported",
                        "titel": "Imported",
                        "text": "Imported",
                        "schweregrad": "info",
                        "zielgruppe": "alle",
                        "kanaele": ["mobil"],
                        "tag": "",
                    }
                ]
            ),
            encoding="utf-8",
        )
        snapshot = await RegistryStorage(
            store, initial_registry_path=import_file
        ).async_load_or_import()

        assert snapshot.entries == ()
        assert store.saved == []
    finally:
        import_file.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_invalid_import_is_atomic_and_does_not_save():
    store = MemoryStore()
    import_file = Path(__file__).with_name("_invalid_initial_registry.json")
    try:
        import_file.write_text(
            json.dumps(
                [
                    {
                        "key": "test::valid",
                        "titel": "Valid",
                        "text": "Valid",
                        "schweregrad": "info",
                        "zielgruppe": "alle",
                        "kanaele": ["mobil"],
                        "tag": "",
                    },
                    {"key": "invalid"},
                ]
            ),
            encoding="utf-8",
        )

        with pytest.raises(EntryValidationError):
            await RegistryStorage(
                store, initial_registry_path=import_file
            ).async_load_or_import()

        assert store.saved == []
        assert store.data is None
    finally:
        import_file.unlink(missing_ok=True)
