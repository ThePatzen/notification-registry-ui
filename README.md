# Notification Registry für Home Assistant

Custom Integration für eine versionierte Benachrichtigungs-Registry mit der
Lovelace-Karte `custom:notification-registry-card`. Integration und Karte werden
im Repository gemeinsam versioniert und über HACS ausgeliefert.

## Installation über HACS

1. In HACS unter **Integrationen → Benutzerdefinierte Repositories**
   `ThePatzen/notification-registry-ui` als Repository vom Typ **Integration**
   hinzufügen.
2. **Notification Registry** installieren und Home Assistant neu starten.
3. Unter **Einstellungen → Geräte & Dienste** die Integration
   **Benachrichtigungs-Registry** hinzufügen. Es gibt genau einen Config Entry.
4. Bei einem Lovelace-Dashboard im Storage-Modus wird die Kartenressource beim
   Setup automatisch als Modul registriert.

Die JavaScript-Karte liegt im HACS-Paket unter
`custom_components/notification_registry/frontend/notification-registry-card.js`.
Sie wird über den HA-Pfad
`/notification_registry/notification-registry-card.js?v=0.1.0` ausgeliefert;
ein separates `www`-Paket ist nicht erforderlich.

## Lovelace-Karte in YAML-Modus

Bei Lovelace im YAML-Modus die Ressource manuell als JavaScript-Modul in
`ui-lovelace.yaml` eintragen:

```yaml
resources:
  - url: /notification_registry/notification-registry-card.js?v=0.1.0
    type: module
```

Danach die Karte im Dashboard konfigurieren:

```yaml
type: custom:notification-registry-card
```

Die Karte benötigt einen angemeldeten Administrator, weil sie vollständige
Meldungstexte über die adminbeschränkte WebSocket-API liest.

## Migration, Backup und Rückweg

Beim ersten Einrichten importiert die Integration die mitgelieferte Registry
einmalig und speichert sie über Home Assistants `Store`. Vor einer produktiven
Migration ein Home-Assistant-Backup (einschließlich YAML und `.storage`) sowie
eine Edit-Sicherung von `script.benachrichtigung_senden` erstellen. Nach dem
Import die Anzahl, Keys und Feldwerte über die Registry-Karte gegen die Quelle
prüfen.

Der sichere Rückweg ist: Config Entry deaktivieren oder entfernen, die
gesicherte Script-Konfiguration wiederherstellen, die kopierten Dateien sowie
die Dashboard-Ressource entfernen und den Home-Assistant-Konfigurationscheck
erneut ausführen. Dieses Paket ändert bestehende Automationen nicht automatisch.

## Dispatcher-Schnittstelle

`script.benachrichtigung_senden` behält seine öffentliche Schnittstelle:

```yaml
action: script.benachrichtigung_senden
data:
  key: technikraum::wasseralarm
  payload:
    geraet: Technikraum
```

`key` ist erforderlich, `payload` ist optional und ein Objekt. Die Integration
stellt die Action `notification_registry.resolve` bereit. Ist sie nicht
verfügbar oder unbekannt, verwendet der Dispatcher seine persistente
Warnungs-Fallback-Konfiguration.

## Entwicklung und Prüfung

Die lokale Prüfung ist reproduzierbar und nutzt für Home Assistant 2026.8.0
den zugehörigen Testadapter `pytest-homeassistant-custom-component==0.13.354`
mit Python 3.14 und `pytest==9.0.3`. Aus dem Repository-Stamm:

```text
ruff check custom_components tests
pytest -v
npm ci
npm test -- --run
```

Die Tests prüfen das Paket ohne Änderungen an einer laufenden Home-Assistant-
Instanz. Ein Live-Preflight (Config-Check, Backup, Import-Readback und
Desktop-/Mobilprüfung) bleibt vor einer produktiven Installation erforderlich.
