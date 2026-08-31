"""Checks for the locally installable notification-registry deliverables."""

from __future__ import annotations

import json
from pathlib import Path

from custom_components.notification_registry.model import NotificationEntry


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "notification_registry"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def structure(value):
    """Return JSON shape without comparing translated string values."""
    if isinstance(value, dict):
        return {key: structure(item) for key, item in value.items()}
    if isinstance(value, list):
        return [structure(item) for item in value]
    return type(value).__name__


def test_manual_install_deliverables_are_complete():
    hacs = load_json(ROOT / "hacs.json")
    assert hacs["name"] == "Notification Registry"
    assert hacs["content_in_root"] is False
    assert hacs["homeassistant"] == "2026.8.0"
    assert hacs["render_readme"] is True
    manifest = load_json(INTEGRATION / "manifest.json")
    assert manifest["codeowners"] == ["@ThePatzen"]
    assert manifest["issue_tracker"].endswith("/issues")
    assert manifest["dependencies"] == ["frontend", "http", "lovelace"]
    assert (INTEGRATION / "manifest.json").is_file()
    assert (INTEGRATION / "config_flow.py").is_file()
    assert (INTEGRATION / "frontend" / "notification-registry-card.js").is_file()
    assert (ROOT / "brand" / "icon.png").is_file()
    assert (ROOT / "brand" / "icon.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert 'customElements.define("notification-registry-card"' in (
        INTEGRATION / "frontend" / "notification-registry-card.js"
    ).read_text(encoding="utf-8")


def test_legacy_and_hacs_card_copies_stay_in_sync():
    bundled = (INTEGRATION / "frontend" / "notification-registry-card.js").read_bytes()
    legacy = (ROOT / "www" / "notification-registry-card.js").read_bytes()
    assert bundled == legacy


def test_initial_registry_entries_are_nonempty_and_fully_valid():
    entries = load_json(INTEGRATION / "initial_registry.json")
    assert entries
    for raw_entry in entries:
        assert set(raw_entry) <= {
            "key",
            "titel",
            "text",
            "schweregrad",
            "zielgruppe",
            "kanaele",
            "tag",
            "revision",
            "created_at",
            "updated_at",
        }
        entry = NotificationEntry.from_dict(raw_entry)
        assert entry.key and entry.titel and entry.text and entry.kanaele


def test_all_translation_files_match_strings_structure():
    strings = load_json(INTEGRATION / "strings.json")
    for language in ("de", "en"):
        translation = load_json(INTEGRATION / "translations" / f"{language}.json")
        assert structure(translation) == structure(strings)
        assert translation["entity"]["sensor"]["notification_registry_diagnostic"]["name"]

    sensor_source = (INTEGRATION / "sensor.py").read_text(encoding="utf-8")
    assert '_attr_translation_key = "notification_registry_diagnostic"' in sensor_source


def test_readme_documents_manual_paths_and_safe_rollback():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "HACS" in readme
    assert "ThePatzen/notification-registry-ui" in readme
    assert "protokolliert" in readme
    for required in (
        "custom_components/notification_registry",
        "custom_components/notification_registry/frontend/notification-registry-card.js",
        "/notification_registry/notification-registry-card.js",
        "notification_registry",
        "script.benachrichtigung_senden",
        "Backup",
        "Rückweg",
    ):
        assert required in readme


def test_ci_uses_a_deterministic_frontend_install():
    workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text(
        encoding="utf-8"
    )
    package = load_json(ROOT / "package.json")
    lock = load_json(ROOT / "package-lock.json")
    assert "npm ci" in workflow
    assert "npm install" not in workflow
    assert "cache: npm" in workflow
    assert (ROOT / "package-lock.json").is_file()
    for name, version in package["devDependencies"].items():
        assert version == lock["packages"][""].get("devDependencies", {})[name]
        assert version == lock["packages"][f"node_modules/{name}"]["version"]
    assert "live-preflight" in workflow


def test_gitignore_excludes_local_tooling_and_test_caches():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("node_modules/", ".venv/", ".pytest_cache/", ".ruff_cache/"):
        assert pattern in ignored
