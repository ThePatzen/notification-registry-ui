# Notification Registry für Home Assistant

Lokale HACS-kompatible Custom Integration für eine versionierte
Benachrichtigungs-Registry mit der Lovelace-Karte
`custom:notification-registry-card`.

## Installation

Dieses Repository wird nicht automatisch veröffentlicht. Für eine lokale
Installation in HACS:

1. HACS öffnen und **Benutzerdefiniertes Repository** wählen.
2. Den lokalen Git-Remote als Repository mit Typ **Integration** hinzufügen.
3. **Notification Registry** installieren und Home Assistant neu starten.
4. Unter **Einstellungen → Geräte & Dienste** die Integration
   **Benachrichtigungs-Registry** hinzufügen. Es gibt genau einen Config Entry.

Alternativ können die Verzeichnisse `custom_components/notification_registry`
und `www/notification-registry-card.js` in die gleichnamigen Verzeichnisse der
Home-Assistant-Konfiguration kopiert werden. Danach ist ebenfalls ein Neustart
erforderlich.

## Lovelace-Karte

Unter **Einstellungen → Dashboards → Ressourcen** die Ressource
`/local/notification-registry-card.js` als JavaScript-Modul eintragen. Danach
die Karte im Dashboard konfigurieren:

```yaml
type: custom:notification-registry-card
```

Die Karte benötigt einen angemeldeten Administrator, weil sie vollständige
Meldungstexte über die adminbeschränkte WebSocket-API liest.

## Migration und Backup

Beim ersten Einrichten importiert die Integration die mitgelieferte Registry
einmalig und speichert sie über Home Assistants `Store`. Vor einer produktiven
Migration ein Home-Assistant-Backup (einschließlich YAML und `.storage`) sowie
eine Edit-Sicherung von `script.benachrichtigung_senden` erstellen. Nach dem
Import die Anzahl, Keys und Feldwerte über die Registry-Karte gegen die Quelle
prüfen.

Der sichere Rückweg ist: Config Entry deaktivieren oder entfernen, die
gesicherte Script-Konfiguration wiederherstellen, Dashboard-Ressource und Karte
entfernen und den Home-Assistant-Konfigurationscheck erneut ausführen. Dieses
Paket ändert bestehende Automationen nicht automatisch.

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

Die lokale Prüfung ist bewusst reproduzierbar und nutzt für Home Assistant
2026.8.0 exakt den zugehörigen Testadapter
`pytest-homeassistant-custom-component==0.13.354` mit Python 3.14 und
`pytest==9.0.3`. Aus dem Repository-Stamm:

```text
ruff check custom_components tests
pytest -v
npm test -- --run
```

Die Tests prüfen das Paket ohne Änderungen an einer laufenden Home-Assistant-
Instanz. Ein Live-Preflight (Config-Check, Backup, Import-Readback und
Desktop-/Mobilprüfung) bleibt vor einer produktiven Installation erforderlich.
