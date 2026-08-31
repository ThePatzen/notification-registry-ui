from __future__ import annotations

import pytest


@pytest.fixture
def valid_entry():
    def make(**overrides):
        data = {
            "key": "technikraum::wasseralarm",
            "titel": "Wasseralarm",
            "text": "Wasser bei {geraet}",
            "schweregrad": "warnung",
            "zielgruppe": "alle",
            "kanaele": ["persistent"],
            "tag": "wasseralarm",
        }
        data.update(overrides)
        return data

    return make
