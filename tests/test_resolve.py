from __future__ import annotations

import pytest

from custom_components.notification_registry.model import NotificationEntry
from custom_components.notification_registry.resolve import (
    PayloadValidationError,
    resolve_entry,
)


def entry(**changes):
    data = {
        "key": "test::one",
        "titel": "Alarm {geraet}",
        "text": "{geraet}: {status}",
        "schweregrad": "info",
        "zielgruppe": "alle",
        "kanaele": ["mobil"],
        "tag": "alarm-{geraet}-{status}",
    }
    data.update(changes)
    return NotificationEntry.from_dict(data)


def test_resolves_known_payload_and_reports_missing():
    result = resolve_entry(entry(text="{geraet}: {status}"), {"geraet": "NAS"})

    assert result.titel == "Alarm NAS"
    assert result.text == "NAS: {status}"
    assert result.tag == "alarm-NAS-{status}"
    assert result.missing_placeholders == ("status",)


def test_replaces_values_in_title_text_and_tag_with_string_conversion():
    result = resolve_entry(
        entry(titel="{number}", text="{number}", tag="{number}"),
        {"number": 42},
    )

    assert (result.titel, result.text, result.tag) == ("42", "42", "42")


def test_reports_missing_placeholders_in_first_occurrence_order_without_duplicates():
    result = resolve_entry(
        entry(titel="{zwei} {eins}", text="{zwei} {drei}", tag="{eins}"), {}
    )

    assert result.missing_placeholders == ("zwei", "eins", "drei")


def test_leaves_invalid_brace_tokens_untouched():
    result = resolve_entry(
        NotificationEntry(
            key="test::one",
            titel="Alarm",
            text="{valid} {bad-name}",
            schweregrad="info",
            zielgruppe="alle",
            kanaele=("mobil",),
        ),
        {},
    )

    assert result.text == "{valid} {bad-name}"
    assert result.missing_placeholders == ("valid",)


def test_rejects_non_mapping_payload():
    with pytest.raises(PayloadValidationError):
        resolve_entry(entry(), ["not", "a", "mapping"])
