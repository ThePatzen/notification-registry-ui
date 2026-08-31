"""Read-only lookup of registry-key references in automation and script config."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any


async def _resolve(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def _as_configurations(raw: Any) -> list[tuple[str | None, Any]]:
    """Normalize the public component exports used by HA and focused doubles."""
    if raw is None:
        return []
    entities = getattr(raw, "entities", None)
    if entities is not None:
        return [(getattr(entity, "entity_id", None), entity) for entity in entities]
    if isinstance(raw, Mapping):
        # A single configuration is commonly represented directly as a mapping.
        if any(name in raw for name in ("action", "sequence", "trigger", "alias")):
            return [(None, raw)]
        return [(str(key), value) for key, value in raw.items()]
    if isinstance(raw, (list, tuple, set)):
        return [(None, value) for value in raw]
    return [(None, raw)]


async def _component_configurations(
    hass: Any, domain: str
) -> list[tuple[str | None, Any]]:
    """Get configurations without reading HA's private storage files.

    Home Assistant components expose their loaded configuration through ``hass.data``;
    the small method probes below also support component test doubles that provide an
    explicit public ``async_get_configurations`` method.
    """
    component = getattr(hass, "components", None)
    component = getattr(component, domain, None) if component is not None else None
    for owner in (component, hass):
        if owner is None:
            continue
        for name in ("async_get_configurations", "get_configurations"):
            getter = getattr(owner, name, None)
            if getter is None:
                continue
            try:
                result = await _resolve(getter(domain) if owner is hass else getter())
            except (AttributeError, TypeError):
                continue
            if result is not None:
                return _as_configurations(result)

    data = getattr(hass, "data", {})
    if not isinstance(data, Mapping):
        return []
    raw = data.get(domain)
    if raw is None:
        # HA's typed HassKey uses a key object internally; support it without
        # importing private component constants.
        for data_key, data_value in data.items():
            if data_key == domain or getattr(data_key, "key", None) == domain:
                raw = data_value
                break
    return _as_configurations(raw)


def _entity_id(domain: str, key: str | None, item: Any, config: Any) -> str:
    for value in (
        getattr(item, "entity_id", None),
        _value(item, "entity_id"),
        _value(config, "entity_id"),
    ):
        if isinstance(value, str) and value:
            return value
    identifier = _value(config, "id") or _value(item, "id") or key or "unknown"
    if isinstance(identifier, str) and identifier.startswith(f"{domain}."):
        return identifier
    return f"{domain}.{identifier}"


def _value(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _friendly_name(hass: Any, entity_id: str, item: Any, config: Any) -> str:
    for value in (
        _value(config, "friendly_name"),
        _value(config, "alias"),
        _value(config, "name"),
        _value(item, "friendly_name"),
        _value(item, "alias"),
        _value(item, "name"),
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()
    states = getattr(hass, "states", None)
    state = states.get(entity_id) if hasattr(states, "get") else None
    name = getattr(state, "name", None) if state is not None else None
    return name if isinstance(name, str) and name else entity_id


def _find_exact(value: Any, target: str, path: str = "") -> list[str]:
    if isinstance(value, str):
        return [path] if value == target else []
    if isinstance(value, Mapping):
        matches: list[str] = []
        for name, child in value.items():
            # Keys are field names, not references. Only string values count.
            child_path = f"{path}.{name}" if path else str(name)
            matches.extend(_find_exact(child, target, child_path))
        return matches
    if isinstance(value, (list, tuple)):
        matches = []
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            matches.extend(_find_exact(child, target, child_path))
        return matches
    return []


async def async_find_references(hass: Any, key: str) -> list[dict[str, str]]:
    """Return every exact string-value occurrence of ``key`` in loaded configs."""
    references: list[dict[str, str]] = []
    for domain in ("automation", "script"):
        for identifier, item in await _component_configurations(hass, domain):
            config = _value(item, "raw_config") or _value(item, "config") or item
            entity_id = _entity_id(domain, identifier, item, config)
            for path in _find_exact(config, key):
                references.append(
                    {
                        "entity_id": entity_id,
                        "friendly_name": _friendly_name(hass, entity_id, item, config),
                        "path": path,
                    }
                )
    return references


# Short aliases are convenient for integrations and make the read-only nature clear.
find_references = async_find_references
