from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Mapping

from .const import CHANNELS, SEVERITIES, TARGET_GROUPS

_KEY_RE = re.compile(r"^[a-z0-9_]+::[a-z0-9_]+$")
_PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")
@dataclass(frozen=True)
class ValidationIssue:
    field: str
    code: str
    message: str


class EntryValidationError(ValueError):
    def __init__(self, issues: list[ValidationIssue]):
        self.issues = tuple(issues)
        super().__init__("; ".join(issue.message for issue in self.issues))


def _timestamp(value: Any, field: str, issues: list[ValidationIssue]) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            issues.append(ValidationIssue(field, "invalid_timestamp", "Ungültiger UTC-Zeitstempel."))
            return datetime.now(timezone.utc)
    else:
        issues.append(ValidationIssue(field, "invalid_timestamp", "Ungültiger UTC-Zeitstempel."))
        return datetime.now(timezone.utc)
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _check_text(value: Any, field: str, issues: list[ValidationIssue]) -> str:
    if not isinstance(value, str) or not value.strip():
        issues.append(ValidationIssue(field, "required", f"{field} darf nicht leer sein."))
        return ""
    text = value.strip()
    remaining = _PLACEHOLDER_RE.sub("", text)
    if remaining.find("{") >= 0 or remaining.find("}") >= 0:
        if not any(issue.field == field and issue.code == "invalid_placeholder" for issue in issues):
            issues.append(ValidationIssue(field, "invalid_placeholder", "Ungültiger Platzhalter."))
    return text


@dataclass(frozen=True)
class NotificationEntry:
    key: str
    titel: str
    text: str
    schweregrad: str
    zielgruppe: str
    kanaele: tuple[str, ...]
    tag: str | None = None
    revision: int = 1
    created_at: datetime = datetime.min.replace(tzinfo=timezone.utc)
    updated_at: datetime = datetime.min.replace(tzinfo=timezone.utc)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> NotificationEntry:
        issues = validate_entry(data)
        if issues:
            raise EntryValidationError(issues)
        now = datetime.now(timezone.utc)
        created = _timestamp(data.get("created_at"), "created_at", [])
        updated = _timestamp(data.get("updated_at"), "updated_at", [])
        if data.get("created_at") is None:
            created = now
        if data.get("updated_at") is None:
            updated = created
        tag = data.get("tag")
        return cls(
            key=data["key"].strip(),
            titel=data["titel"].strip(),
            text=data["text"].strip(),
            schweregrad=data["schweregrad"],
            zielgruppe=data["zielgruppe"],
            kanaele=tuple(dict.fromkeys(data["kanaele"])),
            tag=tag.strip() if isinstance(tag, str) and tag.strip() else None,
            revision=data.get("revision", 1),
            created_at=created,
            updated_at=updated,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "titel": self.titel,
            "text": self.text,
            "schweregrad": self.schweregrad,
            "zielgruppe": self.zielgruppe,
            "kanaele": list(self.kanaele),
            "tag": self.tag,
            "revision": self.revision,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


def validate_entry(data: Mapping[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    key = data.get("key")
    if not isinstance(key, str) or not _KEY_RE.fullmatch(key.strip()):
        issues.append(ValidationIssue("key", "invalid_key", "Key muss bereich::name entsprechen."))
    for field in ("titel", "text"):
        if field in data:
            _check_text(data[field], field, issues)
        else:
            issues.append(ValidationIssue(field, "required", f"{field} darf nicht leer sein."))
    tag = data.get("tag")
    if tag is not None and (not isinstance(tag, str) or tag.strip()):
        _check_text(tag, "tag", issues)
    for field, allowed in (("schweregrad", SEVERITIES), ("zielgruppe", TARGET_GROUPS)):
        if data.get(field) not in allowed:
            issues.append(ValidationIssue(field, "invalid_enum", f"Ungültiger Wert für {field}."))
    channels = data.get("kanaele")
    if not isinstance(channels, (list, tuple)) or not channels:
        issues.append(ValidationIssue("kanaele", "required", "Mindestens ein Kanal ist erforderlich."))
    elif any(channel not in CHANNELS for channel in channels):
        issues.append(ValidationIssue("kanaele", "invalid_enum", "Ungültiger Kanal."))
    if data.get("schweregrad") == "kritisch" and isinstance(channels, (list, tuple)):
        if not {"mobil", "persistent"}.issubset(channels):
            issues.append(ValidationIssue("kanaele", "critical_channels_required", "Kritische Einträge benötigen mobil und persistent."))
    revision = data.get("revision", 1)
    if not isinstance(revision, int) or revision < 1:
        issues.append(ValidationIssue("revision", "invalid_revision", "Revision muss positiv sein."))
    for field in ("created_at", "updated_at"):
        if field in data:
            _timestamp(data[field], field, issues)
    return issues
