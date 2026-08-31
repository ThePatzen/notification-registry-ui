# Benachrichtigungs-Registry mit UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eine lokale Home-Assistant-Integration mit persistenter Benachrichtigungs-Registry, vollständiger CRUD-Tabellenkarte und sicher migriertem zentralem Dispatcher bauen.

**Architecture:** `custom_components/notification_registry` speichert validierte Einträge über `Store`, stellt adminbeschränkte WebSocket-CRUD-Befehle und die Action `notification_registry.resolve` bereit. Eine eigenständige Lovelace-Karte nutzt diese API; `script.benachrichtigung_senden` behält `key` und `payload` als Schnittstelle und verarbeitet die aufgelöste Action-Response mit einem lokalen Fallback.

**Tech Stack:** Home Assistant 2026.8+, Python 3.13, `pytest-homeassistant-custom-component`, `Store`, Home-Assistant-WebSocket-API, Service Actions mit Response, Vanilla JavaScript Web Component, Vitest und jsdom.

**Spec:** `docs/superpowers/specs/2026-08-31-benachrichtigungs-registry-ui-design.md`

## Global Constraints

- Die öffentliche Dispatcher-Schnittstelle bleibt `key: string` plus optional `payload: object`.
- Bestehende Automationen werden nicht geändert.
- Die Integration ist nach außen `notification_registry`; die Karte heißt `custom:notification-registry-card`.
- Keine direkte Änderung an Home Assistants `.storage`-Dateien.
- Vollständige Registry-Texte werden nicht als Entity-Attribute veröffentlicht.
- Schreibende und vollständig lesende WebSocket-Befehle sind adminbeschränkt.
- Kritische Einträge erzwingen die Kanäle `mobil` und `persistent`.
- Löschen referenzierter Keys ist blockiert; Umbenennen zeigt Referenzen und verlangt Bestätigung.
- Jede Produktionsänderung folgt RED–GREEN–REFACTOR und erhält einen eigenen Commit.
- Vor Live-Migration werden Edit-Backup, Config-Check und ein verifizierter Rückweg erstellt.
- Das lokale Repo enthält bereits fremde uncommittierte Dateien; Commits dürfen ausschließlich die je Task genannten Dateien enthalten.
- Git-Commits bleiben blockiert, bis eine lokale oder globale Autorenidentität durch den Benutzer konfiguriert wurde.

## Geplante Dateistruktur

```text
custom_components/notification_registry/
  __init__.py                 Integration laden, Store und Plattform koordinieren
  manifest.json               HA-Metadaten und Mindestversion
  const.py                    Domain, Versionen, Enums und Fehlerschlüssel
  config_flow.py              Einmalige UI-Einrichtung
  model.py                    Dataclass, Normalisierung und Validierung
  registry.py                 In-Memory-Registry, Revisionen und atomare Mutationen
  storage.py                  Versioniertes Store-Format und Erstimport
  resolve.py                  Payload- und Platzhalterauflösung
  reference.py                HA-Konfigurationssuche nach Key-Verwendungen
  websocket_api.py            Adminbeschränkte CRUD-Befehle
  services.py                 notification_registry.resolve mit Response
  sensor.py                   Diagnoseentität ohne Meldungstexte
  strings.json                UI-Texte
  translations/de.json        Deutsche Übersetzungen
  translations/en.json        Englische Fallback-Übersetzungen
  initial_registry.json       Einmaliger Import der aktuellen Script-Registry
www/notification-registry-card.js
tests/
  conftest.py
  test_model.py
  test_registry.py
  test_storage.py
  test_resolve.py
  test_websocket_api.py
  test_services.py
  test_sensor.py
frontend-tests/
  notification-registry-card.test.js
package.json
vitest.config.js
pyproject.toml
```

---

### Task 1: Testumgebung und validiertes Datenmodell

**Files:**
- Create: `pyproject.toml`
- Create: `custom_components/notification_registry/manifest.json`
- Create: `custom_components/notification_registry/const.py`
- Create: `custom_components/notification_registry/model.py`
- Create: `tests/conftest.py`
- Create: `tests/test_model.py`

**Interfaces:**
- Consumes: rohe Eintragsobjekte aus Import, Store und WebSocket
- Produces: `NotificationEntry.from_dict(data)`, `NotificationEntry.to_dict()`, `validate_entry(data)` und `ValidationIssue(field, code, message)`

- [ ] **Step 1: Python-Testumgebung definieren**

`pyproject.toml` enthält `pytest`, `pytest-asyncio`, `pytest-homeassistant-custom-component`, `ruff` sowie `asyncio_mode = "auto"`. `manifest.json` setzt `domain: notification_registry`, `config_flow: true`, `integration_type: service`, `iot_class: local_push` und eine mit der Zielinstanz kompatible Mindestversion.

- [ ] **Step 2: Failing Model-Tests schreiben**

```python
def test_normalizes_valid_entry():
    entry = NotificationEntry.from_dict({
        "key": "technikraum::wasseralarm",
        "titel": " Alarm ",
        "text": "Wasser bei {geraet}",
        "schweregrad": "kritisch",
        "zielgruppe": "alle",
        "kanaele": ["persistent", "mobil", "mobil"],
        "tag": " wasseralarm ",
    })
    assert entry.titel == "Alarm"
    assert entry.kanaele == ("persistent", "mobil")
    assert entry.tag == "wasseralarm"

@pytest.mark.parametrize("key", ["foo", "Foo::bar", "a::", "a::b-c"])
def test_rejects_invalid_key(key):
    with pytest.raises(EntryValidationError) as exc:
        NotificationEntry.from_dict(valid_entry(key=key))
    assert exc.value.issues[0].field == "key"

def test_critical_requires_mobile_and_persistent():
    with pytest.raises(EntryValidationError):
        NotificationEntry.from_dict(valid_entry(
            schweregrad="kritisch", kanaele=["mobil"]
        ))
```

- [ ] **Step 3: RED bestätigen**

Run: `pytest tests/test_model.py -v`

Expected: Collection schlägt fehl, weil `custom_components.notification_registry.model` noch nicht existiert.

- [ ] **Step 4: Minimales Modell implementieren**

`NotificationEntry` ist eine frozen Dataclass. `from_dict` prüft Key-RegEx `^[a-z0-9_]+::[a-z0-9_]+$`, nichtleere Titel/Texte, definierte Enums, mindestens einen eindeutigen Kanal, kritische Pflichtkanäle und Platzhalter-RegEx `\{[A-Za-z_][A-Za-z0-9_]*\}`. Nicht passende `{` oder `}` erzeugen `invalid_placeholder`.

- [ ] **Step 5: GREEN und statische Prüfung bestätigen**

Run: `pytest tests/test_model.py -v && ruff check custom_components/notification_registry/model.py tests/test_model.py`

Expected: alle Model-Tests PASS, Ruff ohne Befund.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml custom_components/notification_registry/manifest.json custom_components/notification_registry/const.py custom_components/notification_registry/model.py tests/conftest.py tests/test_model.py
git commit -m "feat: add notification registry data model"
```

---

### Task 2: Versionierter Store und atomare Registry

**Files:**
- Create: `custom_components/notification_registry/registry.py`
- Create: `custom_components/notification_registry/storage.py`
- Create: `tests/test_registry.py`
- Create: `tests/test_storage.py`

**Interfaces:**
- Consumes: `NotificationEntry`, erwartete Eintragsrevision und `Store`
- Produces: `NotificationRegistry.list_entries()`, `get(key)`, `create(data)`, `update(key, data, expected_revision)`, `duplicate(source_key, new_key)`, `rename(old_key, new_key, expected_revision)`, `delete(key, expected_revision)` und `RegistrySnapshot(schema_version, data_revision, entries)`

- [ ] **Step 1: Failing CRUD- und Konflikttests schreiben**

```python
async def test_update_rejects_stale_revision(registry):
    created = await registry.create(valid_entry(key="test::one"))
    await registry.update("test::one", {**created.to_dict(), "titel": "Neu"}, created.revision)
    with pytest.raises(RevisionConflict) as exc:
        await registry.update("test::one", {**created.to_dict(), "titel": "Alt"}, created.revision)
    assert exc.value.current.titel == "Neu"

async def test_failed_save_keeps_previous_snapshot(registry, failing_store):
    before = registry.snapshot()
    failing_store.fail_next_save = True
    with pytest.raises(RegistrySaveError):
        await registry.create(valid_entry(key="test::failed"))
    assert registry.snapshot() == before
```

- [ ] **Step 2: RED bestätigen**

Run: `pytest tests/test_registry.py tests/test_storage.py -v`

Expected: FAIL wegen fehlender Registry- und Storage-Klassen.

- [ ] **Step 3: Registry und Copy-on-write-Speicherung implementieren**

Jede Mutation läuft unter einem `asyncio.Lock`, baut eine neue Entry-Map, validiert sie vollständig, ruft `Store.async_save` auf und ersetzt erst danach den aktiven Snapshot. `data_revision` steigt pro erfolgreicher Mutation; `entry.revision` steigt nur beim betroffenen Eintrag.

- [ ] **Step 4: Store-Schema und Migration implementieren**

Store-Key ist `notification_registry.registry`, Schema-Version `1`, Minor-Version `1`. `async_load` akzeptiert fehlende Daten als leere Registry, lehnt unbekannte neuere Major-Versionen ab und normalisiert jeden Eintrag erneut über `NotificationEntry.from_dict`.

- [ ] **Step 5: GREEN bestätigen**

Run: `pytest tests/test_registry.py tests/test_storage.py -v`

Expected: CRUD, Konflikt und atomarer Fehlerfall PASS.

- [ ] **Step 6: Commit**

```bash
git add custom_components/notification_registry/registry.py custom_components/notification_registry/storage.py tests/test_registry.py tests/test_storage.py
git commit -m "feat: persist notification registry atomically"
```

---

### Task 3: Platzhalterauflösung und einmaliger Registry-Import

**Files:**
- Create: `custom_components/notification_registry/resolve.py`
- Create: `custom_components/notification_registry/initial_registry.json`
- Modify: `custom_components/notification_registry/storage.py`
- Create: `tests/test_resolve.py`
- Modify: `tests/test_storage.py`

**Interfaces:**
- Consumes: `NotificationEntry`, `payload: Mapping[str, Any]`
- Produces: `resolve_entry(entry, payload) -> ResolvedNotification` mit `titel`, `text`, `schweregrad`, `zielgruppe`, `kanaele`, `tag`, `missing_placeholders`

- [ ] **Step 1: Failing Resolver-Tests schreiben**

```python
def test_resolves_known_payload_and_reports_missing():
    result = resolve_entry(entry(text="{geraet}: {status}"), {"geraet": "NAS"})
    assert result.text == "NAS: {status}"
    assert result.missing_placeholders == ("status",)

def test_rejects_non_mapping_payload():
    with pytest.raises(PayloadValidationError):
        resolve_entry(entry(), ["not", "a", "mapping"])
```

- [ ] **Step 2: RED bestätigen**

Run: `pytest tests/test_resolve.py -v`

Expected: FAIL wegen fehlendem Resolver.

- [ ] **Step 3: Resolver implementieren**

Die Implementierung ersetzt ausschließlich exakt erkannte `{name}`-Tokens durch `str(payload[name])`, verarbeitet Titel, Text und Tag gleich und sortiert fehlende Namen in Reihenfolge ihres ersten Auftretens ohne Duplikate.

- [ ] **Step 4: Aktuelle Live-Registry vollständig exportieren**

Über das HA-Plugin `ha_config_get_script("script.benachrichtigung_senden")` frisch lesen. Das Registry-Objekt maschinell extrahieren und als JSON-Array in `initial_registry.json` speichern. Erwartet werden die aktuell zurückgelesenen Keys; Anzahl und sortierte Key-Liste werden in `tests/test_storage.py` als feste Importerwartung hinterlegt.

- [ ] **Step 5: Idempotenten Erstimport implementieren und testen**

Wenn der Store fehlt, lädt `async_load_or_import` exakt `initial_registry.json`, speichert `import_completed: true` und liest den Store zurück. Existiert ein Store, wird die Importdatei ignoriert. Ein teilweise valider Import speichert nichts.

- [ ] **Step 6: GREEN bestätigen**

Run: `pytest tests/test_resolve.py tests/test_storage.py -v`

Expected: Resolver- und Importtests PASS; importierte Anzahl und Keys stimmen exakt.

- [ ] **Step 7: Commit**

```bash
git add custom_components/notification_registry/resolve.py custom_components/notification_registry/initial_registry.json custom_components/notification_registry/storage.py tests/test_resolve.py tests/test_storage.py
git commit -m "feat: resolve and import notification mappings"
```

---

### Task 4: Home-Assistant-Integration, Action und Diagnoseentität

**Files:**
- Create: `custom_components/notification_registry/__init__.py`
- Create: `custom_components/notification_registry/config_flow.py`
- Create: `custom_components/notification_registry/services.py`
- Create: `custom_components/notification_registry/sensor.py`
- Create: `custom_components/notification_registry/strings.json`
- Create: `custom_components/notification_registry/translations/de.json`
- Create: `custom_components/notification_registry/translations/en.json`
- Create: `tests/test_services.py`
- Create: `tests/test_sensor.py`

**Interfaces:**
- Consumes: geladene `NotificationRegistry`
- Produces: Action `notification_registry.resolve` mit `SupportsResponse.ONLY` und Sensor `sensor.benachrichtigungs_registry`

- [ ] **Step 1: Failing Action- und Sensor-Tests schreiben**

```python
async def test_resolve_service_returns_notification(hass, setup_integration):
    response = await hass.services.async_call(
        "notification_registry", "resolve",
        {"key": "technikraum::wasseralarm", "payload": {}},
        blocking=True, return_response=True,
    )
    assert response["schweregrad"] == "kritisch"

async def test_sensor_exposes_metadata_only(hass, setup_integration):
    state = hass.states["sensor.benachrichtigungs_registry"]
    assert int(state.state) > 0
    assert "entries" not in state.attributes
```

- [ ] **Step 2: RED bestätigen**

Run: `pytest tests/test_services.py tests/test_sensor.py -v`

Expected: FAIL, weil Integration und Plattform nicht registriert sind.

- [ ] **Step 3: Config Flow und Setup implementieren**

Der Config Flow erlaubt genau einen Eintrag, Titel „Benachrichtigungs-Registry“, keine Nutzereingaben. `async_setup_entry` lädt Store/Import, legt die Registry unter `hass.data[DOMAIN][entry.entry_id]` ab, registriert Services einmalig und leitet `sensor` weiter.

- [ ] **Step 4: Response-Action und Diagnoseentität implementieren**

`resolve` validiert `key` als String und `payload` als Objekt, liefert `ResolvedNotification.to_dict()` und wirft bei unbekanntem Key `HomeAssistantError("unknown_key")`. Der Sensorstatus ist die Anzahl, Attribute sind `data_revision`, `schema_version`, `last_updated` und `available`.

- [ ] **Step 5: GREEN und vollständige Python-Suite bestätigen**

Run: `pytest -v && ruff check custom_components tests`

Expected: alle Python-Tests PASS, Ruff ohne Befund.

- [ ] **Step 6: Commit**

```bash
git add custom_components/notification_registry/__init__.py custom_components/notification_registry/config_flow.py custom_components/notification_registry/services.py custom_components/notification_registry/sensor.py custom_components/notification_registry/strings.json custom_components/notification_registry/translations tests/test_services.py tests/test_sensor.py
git commit -m "feat: expose notification registry to Home Assistant"
```

---

### Task 5: Admin-WebSocket-CRUD und Referenzschutz

**Files:**
- Create: `custom_components/notification_registry/reference.py`
- Create: `custom_components/notification_registry/websocket_api.py`
- Modify: `custom_components/notification_registry/__init__.py`
- Create: `tests/test_websocket_api.py`

**Interfaces:**
- Consumes: WebSocket-Nachrichten mit `expected_revision`, HA-Automation-/Script-Konfigurationen
- Produces: Befehle `notification_registry/list|get|create|update|duplicate|references|rename|delete`

- [ ] **Step 1: Failing Berechtigungs-, CRUD- und Referenztests schreiben**

```python
async def test_non_admin_cannot_list_entries(hass, hass_ws_client):
    client = await hass_ws_client(hass, user=await create_user(hass, admin=False))
    await client.send_json_auto_id({"type": "notification_registry/list"})
    assert (await client.receive_json())["error"]["code"] == "unauthorized"

async def test_delete_referenced_key_is_blocked(admin_client, registry):
    response = await ws_call(admin_client, "notification_registry/delete", {
        "key": "technikraum::wasseralarm", "expected_revision": 1
    })
    assert response["error"]["code"] == "key_in_use"
    assert response["error"]["references"]
```

- [ ] **Step 2: RED bestätigen**

Run: `pytest tests/test_websocket_api.py -v`

Expected: FAIL wegen fehlender WebSocket-Registrierung.

- [ ] **Step 3: Adminbefehle und Fehlervertrag implementieren**

Alle Handler verwenden `@websocket_api.require_admin`. Erfolgsantworten enthalten `data_revision` und bestätigte Entry-Daten; Validierungsfehler enthalten `code: validation_failed` plus `issues`; Konflikte enthalten `code: revision_conflict` plus `current`.

- [ ] **Step 4: Referenzsuche implementieren**

`reference.py` liest Automations- und Script-Konfigurationen über die öffentlichen HA-Komponenten-APIs und sucht exakte Stringwerte des Keys. Rückgaben sind `{entity_id, friendly_name, path}`. `delete` ruft die Suche zwingend auf; `rename` verlangt `confirm_references: true`, falls Treffer existieren, ändert aber keine fremde Konfiguration.

- [ ] **Step 5: GREEN bestätigen**

Run: `pytest tests/test_websocket_api.py -v && pytest -v`

Expected: Rechte, CRUD, Konflikte und Referenzschutz PASS; Gesamtsuite PASS.

- [ ] **Step 6: Commit**

```bash
git add custom_components/notification_registry/reference.py custom_components/notification_registry/websocket_api.py custom_components/notification_registry/__init__.py tests/test_websocket_api.py
git commit -m "feat: add protected notification registry API"
```

---

### Task 6: Responsive Lovelace-Tabellenkarte

**Files:**
- Create: `package.json`
- Create: `vitest.config.js`
- Create: `www/notification-registry-card.js`
- Create: `frontend-tests/notification-registry-card.test.js`

**Interfaces:**
- Consumes: WebSocket-Befehle aus Task 5
- Produces: `customElements.define("notification-registry-card", NotificationRegistryCard)`

- [ ] **Step 1: Frontend-Testumgebung und failing Rendering-Test schreiben**

```javascript
it("renders entries and switches to cards at mobile width", async () => {
  const card = document.createElement("notification-registry-card");
  card.hass = fakeHassWithEntries([criticalEntry]);
  document.body.append(card);
  await card.updateComplete;
  expect(card.shadowRoot.querySelector("table")).not.toBeNull();
  matchMediaMock.setWidth(360);
  expect(card.shadowRoot.querySelector("[data-mobile-entry]" )).not.toBeNull();
});
```

- [ ] **Step 2: RED bestätigen**

Run: `npm test -- --run`

Expected: FAIL, weil das Custom Element fehlt.

- [ ] **Step 3: Liste, Suche und Filter implementieren**

Die Karte nutzt `hass.callWS({type: "notification_registry/list"})`, rendert semantisches `<table>` ab 700 px und Eintragskarten darunter. Suche umfasst Key, Titel und Text; der Schweregradfilter arbeitet lokal auf dem bestätigten Serverstand.

- [ ] **Step 4: Editor und CRUD-Dialoge testgetrieben ergänzen**

Je Verhalten zuerst einen failing Test hinzufügen: Pflichtfelder, Enum-Auswahl, Kanal-Checkboxen, kritische Pflichtkanäle, Create, Update, Duplicate, Delete-Bestätigung, Referenzblockade, Rename-Bestätigung und Revisionskonflikt. Danach nur die minimale Implementierung ergänzen.

- [ ] **Step 5: Tastatur und Responsive-Verhalten prüfen**

Run: `npm test -- --run`

Zusätzlich Playwright/Browser-Prüfung bei 1280 px, 736 px und 360 px: keine abgeschnittenen Aktionen, Dialog ohne horizontales Seiten-Scrolling, vollständige Bedienung per Tab/Enter/Escape.

- [ ] **Step 6: Commit**

```bash
git add package.json vitest.config.js www/notification-registry-card.js frontend-tests/notification-registry-card.test.js
git commit -m "feat: add notification registry table card"
```

---

### Task 7: Lokale Gesamtprüfung und HACS-kompatibles Paket

**Files:**
- Create: `hacs.json`
- Create: `README.md`
- Create: `.github/workflows/validate.yml`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: Python-Integration und Kartenmodul
- Produces: lokal installierbares, HACS-kompatibles Repository

- [ ] **Step 1: Failing Strukturprüfung anlegen**

Ein Test prüft Manifest, Übersetzungen, Config Flow, `hacs.json`, Kartenregistrierung und dass `initial_registry.json` keine unbekannten Felder enthält. Run: `pytest tests/test_package.py -v`; Expected: FAIL, solange Paketdateien fehlen.

- [ ] **Step 2: Paketmetadaten und Installationsanleitung erstellen**

`hacs.json` setzt `name`, `render_readme: true` und `homeassistant: 2026.8.0`. README dokumentiert Installation, Config-Entry-Erstellung, Kartenressource, Backup, Rückweg und die unveränderte Dispatcher-Schnittstelle.

- [ ] **Step 3: CI und lokale Gesamtprüfung definieren**

Workflow führt `ruff check`, `pytest -v` und `npm test -- --run` aus. Lokal dieselben drei Befehle ausführen; Expected: 0 Fehler und 0 fehlgeschlagene Tests.

- [ ] **Step 4: Commit**

```bash
git add hacs.json README.md .github/workflows/validate.yml .gitignore tests/test_package.py
git commit -m "chore: package notification registry integration"
```

---

### Task 8: Kontrollierte Live-Installation und Dispatcher-Migration

**Files:**
- Modify live: `script.benachrichtigung_senden`
- Modify live: Dashboard `benachrichtigungen-dashboard`, View `kanaele-helfer`
- Create live: Config Entry `notification_registry`
- Create live: Dashboard resource `notification-registry-card.js`

**Interfaces:**
- Consumes: getestetes Paket, aktuelles Script mit Config-Hash, HA-Plugin
- Produces: aktive Registry-UI und Dispatcher mit Response-Action/Fallback

- [ ] **Step 1: Deployment-Transport vor Schreibaktionen belegen**

Bevor Dateien übertragen werden, genau einen erlaubten Weg nachweisen:

1. vorhandener beschreibbarer HA-Konfigurationspfad mit `custom_components/` und `www/`, oder
2. ein vom Benutzer benanntes GitHub-Repository `owner/repo`, das als HACS-Custom-Repository installiert werden darf.

Ist keiner verfügbar, hier anhalten und den Benutzer um den konkreten Transport bitten. Kein Repository veröffentlichen und keine Zugangsdaten anfordern oder erfinden.

- [ ] **Step 2: HA-Baseline und Rückweg sichern**

HA-Best-Practice-Guide frisch lesen, `script.benachrichtigung_senden` samt `config_hash` lesen, Edit-Backup erstellen und HA-Config-Check ausführen. Expected: gültige Konfiguration. Den alten Script-Config-Hash und die Edit-Backup-ID dokumentieren.

- [ ] **Step 3: Paket installieren und HA kontrolliert neu starten**

Dateien über den belegten Transport installieren. Vor dem notwendigen Neustart Nutzerstatus geben; anschließend Systemübersicht, Config-Check und Reparaturen prüfen. Die Integration über den Config Flow hinzufügen und `sensor.benachrichtigungs_registry` zurücklesen.

- [ ] **Step 4: Import-Readback gegen Quelle prüfen**

Admin-WebSocket-Liste lesen und Anzahl, sortierte Keys sowie jeden Feldwert gegen `initial_registry.json` vergleichen. Bei irgendeiner Abweichung Dispatcher unverändert lassen und Import korrigieren.

- [ ] **Step 5: Dispatcher testgetrieben umstellen**

Vor dem Schreiben als RED-Prüfung bestätigen, dass das Script noch das eingebettete `registry`-Objekt enthält. Danach mit frischem Config-Hash nur die Registry-Ermittlung ersetzen:

```yaml
- variables:
    fallback_config:
      titel: Unbekannter Benachrichtigungs-Key
      text: Der Key {key} konnte nicht aus der Benachrichtigungs-Registry geladen werden.
      schweregrad: warnung
      zielgruppe: david
      kanaele: [persistent]
      tag: benachrichtigung_unbekannter_key
- action: notification_registry.resolve
  data:
    key: "{{ key_norm }}"
    payload: "{{ payload_norm }}"
  response_variable: registry_response
  continue_on_error: true
- variables:
    meldung_config: "{{ registry_response if registry_response is defined and registry_response is mapping else fallback_config }}"
```

Die bestehenden Kanalzweige bleiben unverändert. Script zurücklesen und belegen, dass kein großes eingebettetes Registry-Objekt mehr vorhanden ist.

- [ ] **Step 6: Karte registrieren und Dashboard aktualisieren**

Karten-JavaScript als `/local/notification-registry-card.js` oder als getestete Inline-Ressource registrieren. Dashboard frisch lesen; in View `kanaele-helfer` eine volle Breite einnehmende `{type: "custom:notification-registry-card"}`-Karte unter der Helfer-Überschrift ergänzen. Mit Config-Hash schreiben und zurücklesen.

- [ ] **Step 7: Sichere Live-Abnahme ausführen**

Über die UI einen unreferenzierten Testeintrag anlegen, bearbeiten, duplizieren und löschen. Referenzblockade und Revisionskonflikt prüfen. Danach eine Testmeldung ausschließlich persistent senden (`mobil` und beide Durchsagekanäle ausgeschlossen), die Meldung wieder entfernen und den unbekannten-Key-Fallback ebenfalls ausschließlich persistent prüfen.

- [ ] **Step 8: Finale Verifikation und Commit**

Config-Check, Reparaturen, Registry-Readback, Script-Readback, Dashboard-Readback und Desktop-/Mobilrender frisch prüfen. Lokal erneut `ruff check`, `pytest -v` und `npm test -- --run` ausführen. Erst danach Abschluss melden.

```bash
git status --short
git log --oneline --max-count=8
```

Expected: nur bekannte Benutzeränderungen außerhalb der Feature-Commits; alle Feature-Commits vorhanden und alle Prüfungen grün.
