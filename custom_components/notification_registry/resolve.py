"""Resolve notification placeholders against a caller-provided payload."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .model import NotificationEntry

_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class PayloadValidationError(ValueError):
    """Raised when a resolver payload is not a mapping."""


@dataclass(frozen=True)
class ResolvedNotification:
    titel: str
    text: str
    schweregrad: str
    zielgruppe: str
    kanaele: tuple[str, ...]
    tag: str | None
    missing_placeholders: tuple[str, ...] = ()


def resolve_entry(
    entry: NotificationEntry, payload: Mapping[str, Any]
) -> ResolvedNotification:
    """Resolve recognized placeholders while retaining unknown placeholders."""
    if not isinstance(payload, Mapping):
        raise PayloadValidationError("Payload muss ein Mapping sein.")

    missing: list[str] = []
    missing_seen: set[str] = set()

    def resolve(value: str | None) -> str | None:
        if value is None:
            return None

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name in payload:
                return str(payload[name])
            if name not in missing_seen:
                missing_seen.add(name)
                missing.append(name)
            return match.group(0)

        return _PLACEHOLDER_RE.sub(replace, value)

    return ResolvedNotification(
        titel=resolve(entry.titel) or "",
        text=resolve(entry.text) or "",
        schweregrad=entry.schweregrad,
        zielgruppe=entry.zielgruppe,
        kanaele=entry.kanaele,
        tag=resolve(entry.tag),
        missing_placeholders=tuple(missing),
    )
