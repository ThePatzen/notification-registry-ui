"""Config flow for the single notification registry instance."""

from __future__ import annotations

from typing import Any

from .const import DOMAIN

try:
    from homeassistant import config_entries
    from homeassistant.config_entries import ConfigFlow
except ImportError:  # pragma: no cover - used by focused tests without HA

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs):
            kwargs.pop("domain", None)
            super().__init_subclass__(**kwargs)

        def __init__(self) -> None:
            self.hass = None

        def _async_current_entries(self):
            return []

        def async_abort(self, **kwargs):
            return {"type": "abort", **kwargs}

        def async_create_entry(self, **kwargs):
            return {"type": "create_entry", **kwargs}

    config_entries = None


class NotificationRegistryConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create one registry config entry without asking for user input."""

    VERSION = 1

    async def async_step_user(self, _user_input: dict[str, Any] | None = None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        return self.async_create_entry(
            title="Benachrichtigungs-Registry",
            data={},
        )
