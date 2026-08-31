from __future__ import annotations

import pytest

from custom_components.notification_registry.reference import _find_exact


def test_finds_registry_key_token_inside_jinja_mapping_string() -> None:
    value = "{{ {'waschmaschine::beendet': {'titel': 'Fertig'}}[trigger.id] }}"

    assert _find_exact({"message": value}, "waschmaschine::beendet") == ["message"]


@pytest.mark.parametrize(
    "value",
    [
        "foo::bar_extra",
        "prefixfoo::bar",
        "foo::barSuffix",
    ],
)
def test_does_not_match_registry_key_inside_a_larger_token(value: str) -> None:
    assert _find_exact(value, "foo::bar") == []
