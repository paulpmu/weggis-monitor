# Weggis Monitor – Zingelistrasse

Zeichnet den Status von https://weggis.info.geoprevent.com/ (Ampelzustand und
Gefahrenstufe) automatisch im Hintergrund auf und zeigt Verlauf und Auswertung
als Web-App – optimiert für iPhone und iPad (Safari).

## So funktioniert es

```
GitHub Actions (alle 5 Min.)   ──►  Zweig "data": status.json  ──►  Web-App (GitHub Pages)
   fragt die Webseite ab              Verlauf aller Zustände         liest status.json
```

- `collector/collect.py` – liest die Webseite und führt `status.json` nach
  (nur Python-Standardbibliothek).
- `.github/workflows/collect.yml` – jeder Lauf fragt ca. 55 Minuten lang alle
  5 Minuten ab und startet am Ende selbst den nächsten Lauf (ein stündlicher
  Zeitplan dient als Reserve). Die Daten landen im Zweig `data`.
- `docs/` – die Web-App (eine HTML-Datei, keine externen Abhängigkeiten).
  Auf GitHub Pages findet sie die Daten automatisch.

## Einrichtung (einmalig)

1. Repository auf GitHub anlegen (öffentlich) und diesen Ordner hochladen.
2. **Settings → Pages**: Source «Deploy from a branch», Branch `main`, Ordner `/docs`.
3. **Actions**: Workflow «Status abfragen» einmal manuell starten
   («Run workflow»); danach läuft er automatisch.
4. Web-App öffnen: `https://<benutzername>.github.io/<repository>/`

## Auf iPhone / iPad installieren

In Safari die Adresse öffnen → Teilen-Symbol → **«Zum Home-Bildschirm»**.
Die App startet dann im Vollbild mit eigenem Symbol.

## Dashboard

- Aktueller Ampelzustand und Gefahrenstufe mit Dauer
- Zeitraum: 24 Std, 7/30/90 Tage, 1 Jahr, alles
- Kennzahlen: Wechsel, Sperrungen, Anteil Zeit gesperrt, längste Sperrung,
  höchste und durchschnittliche Gefahrenstufe
- Zeitverlauf (Abschnitt antippen für Details), Zeitanteile, Liste der Statuswechsel
- Warnhinweis, falls die letzte erfolgreiche Abfrage über 75 Minuten zurückliegt

## Gut zu wissen

- Abfrage anhalten: GitHub → Actions → «Status abfragen» → «…» → «Disable workflow».
  Wieder starten: «Enable workflow», dann «Run workflow».
- Zwischen zwei Läufen entsteht jeweils eine Lücke von ca. 1–2 Minuten.
- Der Beginn eines Zustands wird aus der «Seit …»-Angabe der Webseite übernommen.
- Ändert Geoprevent den Aufbau der Webseite, erscheinen Fehler unter
  «Datenerfassung» und das Programm muss angepasst werden.
- Die Rohdaten liegen in `status.json` im Zweig `data` (JSON).
