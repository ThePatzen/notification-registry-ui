from __future__ import annotations

import pytest

from custom_components.notification_registry.model import (
    EntryValidationError,
    NotificationEntry,
    validate_entry,
)


def test_normalizes_valid_entry():
    entry = NotificationEntry.from_dict(
        {
            "key": "technikraum::wasseralarm",
            "titel": " Alarm ",
            "text": "Wasser bei {geraet}",
            "schweregrad": "kritisch",
            "zielgruppe": "alle",
            "kanaele": ["persistent", "mobil", "mobil"],
            "tag": " wasseralarm ",
        }
    )
    assert entry.titel == "Alarm"
    assert entry.kanaele == ("persistent", "mobil")
    assert entry.tag == "wasseralarm"


@pytest.mark.parametrize("key", ["foo", "Foo::bar", "a::", "a::b-c"])
def test_rejects_invalid_key(key, valid_entry):
    with pytest.raises(EntryValidationError) as exc:
        NotificationEntry.from_dict(valid_entry(key=key))
    assert exc.value.issues[0].field == "key"


def test_critical_requires_mobile_and_persistent(valid_entry):
    with pytest.raises(EntryValidationError):
        NotificationEntry.from_dict(
            valid_entry(schweregrad="kritisch", kanaele=["mobil"])
        )


def test_rejects_invalid_placeholder(valid_entry):
    issues = validate_entry(valid_entry(text="Wasser bei {geraet"))
    assert any(issue.code == "invalid_placeholder" for issue in issues)


def test_round_trips_optional_metadata(valid_entry):
    entry = NotificationEntry.from_dict(
        valid_entry(
            revision=3,
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-02T00:00:00+00:00",
        )
    )
    data = entry.to_dict()
    assert data["revision"] == 3
    assert data["kanaele"] == ["persistent"]
    assert data["created_at"] == "2026-01-01T00:00:00+00:00"
