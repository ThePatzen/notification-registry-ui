# Notification Registry für Home Assistant

Lokale Custom Integration für eine versionierte Benachrichtigungs-Registry mit
der Lovelace-Karte `custom:notification-registry-card`. Die Integration und
Karte werden zunächst als gemeinsam versionierte lokale Komponenten ausgeliefert.

## Manuelle Installation

1. Den Ordner `custom_components/notification_registry` in das Verzeichnis
   `custom_components/notification_registry` deiner Home-Assistant-
   Konfiguration kopieren.
2. `www/notification-registry-card.js` in das `www`-Verzeichnis derselben
   Konfiguration kopieren.
3. Home Assistant neu starten.
4. Unter **Einstellungen → Geräte & Dienste** die Integration
   **Benachrichtigungs-Registry** hinzufügen. Es gibt genau einen Config Entry.

## Lovelace-Karte

Unter **Einstellungen → Dashboards → Ressourcen** die Ressource
`/local/notification-registry-card.js` als JavaScript-Modul eintragen. Danach
die Karte im Dashboard konfigurieren:

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
