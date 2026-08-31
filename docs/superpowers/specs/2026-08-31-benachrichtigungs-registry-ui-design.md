# Benachrichtigungs-Registry mit UI – Design

## Ziel

Die derzeit in `script.benachrichtigung_senden` eingebettete Registry wird in eine lokale Home-Assistant-Integration ausgelagert. Eine eigene Lovelace-Karte stellt die Einträge als durchsuchbare Tabelle dar und erlaubt Anlegen, Bearbeiten, Duplizieren, Umbenennen und Löschen. Bestehende Automationen behalten ihre öffentliche Schnittstelle aus `key` und optionalem `payload`.

## Umfang

Zum Umfang gehören:

- lokale Integration `notification_registry`
- versionierte, dauerhafte Speicherung über Home Assistants `Store`
- vollständige CRUD- und Umbenennungs-API mit Validierung und Konflikterkennung
- eigene responsive Lovelace-Tabellenkarte
- einmalige Migration der bestehenden Script-Registry
- Umstellung von `script.benachrichtigung_senden` auf die Registry-API
- Einbindung in die Ansicht „Kanäle & Helfer“ des Dashboards `benachrichtigungen-dashboard`
- automatisierte Tests und sichere Live-Verifikation

Nicht zum Umfang gehören neue Empfänger, neue Zustellkanäle, Änderungen an den auslösenden Automationen oder ein allgemeiner Benachrichtigungs-Designer.

## Architektur

### Integration

Die lokale Integration `notification_registry` ist die alleinige Quelle für Benachrichtigungskonfigurationen. Sie wird als normale Home-Assistant-Config-Entry-Integration umgesetzt und speichert ihre Daten über `homeassistant.helpers.storage.Store`. Direkte Änderungen an `.storage` sind ausgeschlossen.

Die Integration registriert WebSocket-Befehle für die Tabellenkarte:

- Liste und Detail lesen
- Eintrag anlegen
- Eintrag bearbeiten
- Eintrag duplizieren
- Eintrag umbenennen
- Eintrag löschen
- Referenzen eines Keys prüfen

Für den Dispatcher registriert sie eine Action `notification_registry.resolve`. Diese nimmt `key` und optional `payload` entgegen und liefert die validierte, mit Platzhaltern aufgelöste Meldung als Action-Response zurück. Dadurch muss die vollständige Registry nicht als Entity-Attribut veröffentlicht oder vom Recorder gespeichert werden.

Eine Diagnoseentität zeigt nur Betriebsstatus, Anzahl der Einträge, Datenrevision und Zeitpunkt der letzten Änderung. Sie enthält keine vollständigen Meldungstexte.

### Dispatcher

`script.benachrichtigung_senden` behält die Felder:

- erforderlich: `key`
- optional: `payload`

Das Script ruft zuerst `notification_registry.resolve` mit einer Response-Variable auf. Die Antwort enthält Titel, Text, Schweregrad, Zielgruppe, Kanäle und Tag. Die vorhandene Zustelllogik für Mobilgeräte, persistente Meldungen und Durchsagen bleibt im Script.

Ist die Integration nicht verfügbar, liefert keine gültige Antwort oder kennt den Key nicht, verwendet das Script eine lokale minimale Fallback-Konfiguration. Sie erzeugt eine persistente Warnung für David mit dem Tag `benachrichtigung_unbekannter_key`. Ein Fehler darf nicht still verschwinden.

Bestehende Automation-Aufrufe werden nicht verändert.

### Lovelace-Karte

Eine eigene Karte `notification-registry-card` kommuniziert ausschließlich über die WebSocket-API der Integration. Sie wird als Dashboard-Ressource registriert und in „Kanäle & Helfer“ eingebunden.

Die Desktopansicht verwendet eine Tabelle mit diesen Spalten:

- Key
- Titel
- Schweregrad
- Zielgruppe
- Kanäle
- Tag
- Aktionen

Die Werkzeugleiste bietet Volltextsuche, Schweregradfilter und „Neue Meldung“. Zeilenaktionen sind Bearbeiten, Duplizieren, Umbenennen und Löschen. Auf kleinen Displays werden dieselben Daten und Aktionen als kompakte Eintragskarten dargestellt; es gibt keine funktionale Einschränkung gegenüber der Desktopansicht.

Der Bearbeitungsdialog verwendet native Eingabefelder, Auswahlfelder für Schweregrad und Zielgruppe sowie Mehrfachauswahl für Kanäle. Speichern lädt anschließend die vom Server bestätigte Version. Validierungs- und Konfliktfehler erscheinen am betroffenen Feld beziehungsweise als verständliche Meldung im Dialog.

## Datenmodell

Jeder Eintrag besitzt:

```text
key: string
titel: string
text: string
schweregrad: info | hinweis | warnung | kritisch
zielgruppe: alle | david | isabella | anwesende
kanaele: eindeutige Liste aus mobil | persistent | durchsage | durchsage_alle
tag: string, optional
revision: positive Ganzzahl
created_at: UTC-Zeitstempel
updated_at: UTC-Zeitstempel
```

Der Key ist die fachliche ID und muss dem Muster `bereich::name` entsprechen. Beim normalen Bearbeiten ist er unveränderlich. Die separate Umbenennungsaktion prüft zuerst Referenzen, legt den neuen Key atomar an und entfernt den alten Key nur innerhalb derselben erfolgreichen Speichertransaktion.

## Validierung und Schutzregeln

- Keys sind eindeutig, normalisiert und entsprechen `^[a-z0-9_]+::[a-z0-9_]+$`.
- Titel und Text dürfen nach dem Trimmen nicht leer sein.
- Schweregrad, Zielgruppe und Kanäle akzeptieren ausschließlich definierte Werte.
- Die Kanalliste enthält keine Duplikate und mindestens einen Kanal.
- Tag ist optional und wird getrimmt.
- Platzhalter verwenden ausschließlich `{name}` mit `name` aus Buchstaben, Ziffern und Unterstrich.
- Nicht geschlossene oder syntaktisch ungültige Platzhalter blockieren das Speichern.
- Beim Auflösen bleiben fehlende Payload-Platzhalter sichtbar und werden zusätzlich als Warnung in der Response gemeldet; sie werden nicht still durch Leertext ersetzt.
- Bearbeiten, Umbenennen und Löschen verlangen die zuletzt gelesene Eintragsrevision. Eine abweichende Revision ergibt einen Konflikt statt eines Überschreibens.
- Löschen ist blockiert, solange Automationen oder Skripte den Key referenzieren.
- Umbenennen zeigt alle gefundenen Referenzen und verlangt eine ausdrückliche Bestätigung. Die Integration ändert fremde Automationen nicht automatisch.
- Kritische Einträge können nicht ohne `mobil` und `persistent` gespeichert werden. Dadurch bleiben die bestehenden Sicherheitsregeln erhalten.

## Speicherung und Migration

Das Speicherformat besitzt eine eigene Schema-Version. Änderungen werden vollständig validiert, in einer neuen In-Memory-Struktur aufgebaut und anschließend atomar über `Store.async_save` geschrieben. Die globale Datenrevision steigt bei jeder erfolgreichen Mutation.

Bei der ersten Einrichtung wird die bestehende Registry einmalig aus einer mitgelieferten, aus dem aktuellen Script erzeugten Importdatei geladen. Vor dem Import wird die Script-Konfiguration über die HA-Config-API gesichert. Der Import gilt nur als erfolgreich, wenn Anzahl, Keys und alle Feldwerte der Quelle entsprechen. Danach wird der Importmarker gespeichert und die Migration nicht erneut ausgeführt.

Nach erfolgreicher Migration und Readback wird die große eingebettete Registry aus dem Dispatcher entfernt. Ab diesem Zeitpunkt ist nur die Integration maßgeblich.

## Datenfluss

### Zustellung

1. Eine Automation ruft `script.benachrichtigung_senden` mit `key` und optionalem `payload` auf.
2. Das Script ruft `notification_registry.resolve` auf.
3. Die Integration liest den Eintrag, validiert das Payload-Objekt und ersetzt bekannte Platzhalter in Titel, Text und Tag.
4. Die Integration liefert die aufgelöste Konfiguration und eventuelle Platzhalterwarnungen zurück.
5. Das Script normalisiert die Zielgruppe und stellt über die vorhandenen unabhängigen Kanalzweige zu.
6. Ein Kanalausfall verhindert die übrigen Kanäle weiterhin nicht.

### UI-Änderung

1. Die Karte liest Liste und globale Datenrevision.
2. Der Benutzer öffnet einen Eintrag und erhält dessen Revision.
3. Die Karte sendet Mutation plus erwartete Revision.
4. Die Integration validiert, prüft Referenzen und Revision und speichert atomar.
5. Die Karte ersetzt ihren lokalen Stand ausschließlich durch die bestätigte Serverantwort.

## Fehlerbehandlung

- Schema- und Feldfehler verändern den Speicher nicht.
- Revisionskonflikte liefern den aktuellen Servereintrag, damit der Benutzer neu laden und vergleichen kann.
- Speicherfehler werden protokolliert, an die Karte gemeldet und verändern weder In-Memory-Daten noch Diagnoseentität.
- Eine unbekannte WebSocket-Operation oder ein unbekannter Key liefert einen typisierten Fehler.
- Ist die Registry beim Dispatcher-Aufruf nicht verfügbar, greift die persistente Fallback-Warnung.
- Ein fehlerhafter Eintrag darf nie teilweise gespeichert werden.
- Vor Migration und Dispatcher-Änderung werden Edit-Sicherungen angelegt; die Rückkehr besteht aus Wiederherstellen des alten Scripts und Entfernen beziehungsweise Deaktivieren der neuen Config Entry.

## Sicherheit

Schreibende WebSocket-Befehle verlangen einen authentifizierten Administrator. Lesender Zugriff auf die vollständigen Meldungstexte ist ebenfalls auf Administratoren beschränkt, passend zum bestehenden adminbeschränkten Dashboard. Action-Responses enthalten keine Zugangsdaten. Freier JavaScript- oder Template-Code ist in Registry-Feldern nicht zulässig.

## Tests und Abnahme

### Automatisierte Tests

- Laden eines leeren und eines bestehenden Stores
- Schema-Migration und Import-Idempotenz
- Anlegen, Lesen, Bearbeiten, Duplizieren und Löschen
- Key-Eindeutigkeit und Key-Format
- alle Enum- und Kanalregeln
- kritische Sicherheitsregeln
- gültige, fehlende und fehlerhafte Platzhalter
- atomare Speicherung bei Fehlern
- Revisionskonflikte
- Referenzschutz für Löschen und Umbenennen
- `resolve` mit und ohne Payload
- Dispatcher-Fallback bei unbekanntem Key und nicht verfügbarer Integration
- Rechteprüfung der WebSocket-Befehle
- Tabellenfilter, Formvalidierung und responsive Kartenansicht

### Live-Abnahme

1. Vor Änderungen ist die HA-Konfiguration gültig und eine Edit-Sicherung des Dispatchers vorhanden.
2. Der Erstimport enthält exakt alle bisherigen Keys und Feldwerte.
3. Anlegen, Bearbeiten, Duplizieren und Löschen eines unreferenzierten Testeintrags funktionieren über die UI.
4. Ein referenzierter Key kann weder gelöscht noch ohne Bestätigung umbenannt werden.
5. Ein absichtlich erzeugter Revisionskonflikt überschreibt keine Daten.
6. Das Dashboard funktioniert auf Desktop- und Mobilbreite.
7. Eine harmlose Testmeldung wird ausschließlich persistent gesendet; Mobilgeräte und Durchsage bleiben deaktiviert.
8. Der unbekannte-Key-Fallback erzeugt die erwartete persistente Warnung.
9. Alle bestehenden Automationen referenzieren weiterhin nur `script.benachrichtigung_senden` mit `key` und optionalem `payload`.
10. Der abschließende Home-Assistant-Konfigurationscheck ist gültig und erzeugt keine neue Repair-Meldung.

## Auslieferung

Integration und Karte werden zunächst als lokale, gemeinsam versionierte Komponenten entwickelt. Die Karte wird als Dashboard-Ressource registriert; die Integration wird über Home Assistants normalen Custom-Component-Ladepfad installiert. Ein Home-Assistant-Neustart erfolgt erst nach erfolgreichem Testlauf und gültigem Konfigurationscheck und wird vorab angekündigt.
