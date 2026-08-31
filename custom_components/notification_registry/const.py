from __future__ import annotations

from pathlib import Path

DOMAIN = "notification_registry"
SCHEMA_VERSION = 1
INTEGRATION_VERSION = "0.1.0"
URL_BASE = "/notification_registry"
FRONTEND_DIR = Path(__file__).parent / "frontend"
CARD_RESOURCE_URL = f"{URL_BASE}/notification-registry-card.js?v={INTEGRATION_VERSION}"

SEVERITIES = ("info", "hinweis", "warnung", "kritisch")
TARGET_GROUPS = ("alle", "david", "isabella", "anwesende")
CHANNELS = ("mobil", "persistent", "durchsage", "durchsage_alle")
