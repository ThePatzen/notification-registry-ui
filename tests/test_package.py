"""Checks that the repository can be installed as a HACS local integration."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "notification_registry"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_hacs_metadata_targets_home_assistant_2026_8():
    metadata = load_json(ROOT / "hacs.json")

    assert metadata == {
        "name": "Notification Registry",
        "render_readme": True,
        "homeassistant": "2026.8.0",
    }


def test_integration_manifest_and_runtime_assets_are_complete():
    manifest = load_json(INTEGRATION / "manifest.json")
    assert manifest["domain"] == "notification_registry"
    assert manifest["config_flow"] is True
    assert manifest["integration_type"] == "service"
    assert manifest["iot_class"] == "local_push"
    assert (INTEGRATION / "config_flow.py").is_file()
    assert (ROOT / "www" / "notification-registry-card.js").is_file()
    assert 'customElements.define("notification-registry-card"' in (
        ROOT / "www" / "notification-registry-card.js"
    ).read_text(encoding="utf-8")


def test_translations_have_matching_entity_localization():
    strings = load_json(INTEGRATION / "strings.json")
    entity = strings["entity"]["sensor"]["notification_registry_diagnostic"]
    assert entity["name"]

    for language in ("de", "en"):
        translation = load_json(INTEGRATION / "translations" / f"{language}.json")
        translated = translation["entity"]["sensor"]["notification_registry_diagnostic"]
        assert set(translated) == set(entity)
        assert translated["name"]

    sensor_source = (INTEGRATION / "sensor.py").read_text(encoding="utf-8")
    assert '_attr_translation_key = "notification_registry_diagnostic"' in sensor_source


def test_initial_registry_contains_only_model_fields():
    allowed = {
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
    entries = load_json(INTEGRATION / "initial_registry.json")
    assert entries
    assert all(set(entry) <= allowed for entry in entries)


def test_readme_documents_local_installation_and_safe_rollback():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for required in (
        "HACS",
        "notification_registry",
        "script.benachrichtigung_senden",
        "Backup",
        "Rückweg",
        "/local/notification-registry-card.js",
    ):
        assert required in readme


def test_ci_runs_pinned_unit_and_frontend_checks_without_stale_ha_plugin():
    workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text(
        encoding="utf-8"
    )
    assert "ruff check custom_components tests" in workflow
    assert "pytest -v" in workflow
    assert "npm test -- --run" in workflow
    assert 'python-version: "3.14"' in workflow
    assert '"pytest==9.0.3"' in workflow
    assert '"pytest-homeassistant-custom-component==0.13.354"' in workflow
    assert '"ruff==0.16.5"' in workflow
    assert "live-preflight" in workflow


def test_gitignore_excludes_local_tooling_and_test_caches():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("node_modules/", ".venv/", ".pytest_cache/", ".ruff_cache/"):
        assert pattern in ignored
