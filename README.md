# Serien-E-Mail Versand (Serienmail)

Serien-E-Mails per SMTP versenden – mit PyQt5-GUI, individuellen Anhängen pro Empfänger, Platzhaltern und BCC-Option.

## Funktionen

- SMTP-Versand (STARTTLS, Port konfigurierbar)
- Empfängertabelle mit Name, Anrede, E-Mail und mehreren Anhängen pro Empfänger
- Platzhalter im E-Mail-Text: `{Name}` und `{Anrede}` (wird zu „Sehr geehrter Herr/Frau <Name>")
- Optionale Kopie (BCC) an den Absender
- Einstellungen (`einstellungen.json`) und Empfängerlisten (`empfaenger.json`) speichern/laden
- Korrekte MIME-Typen für Anhänge und RFC-2231-kodierte Dateinamen (umlautsicher)
- Spaltenbreiten der Empfängertabelle manuell anpassbar; beim Fenstervergrößern wächst nur die Spalte „Anhang-Pfad(e)"
- E-Mail-Text und Betreff als Entwurf speichern und wieder laden (`entwurf.json`, Speicherort frei wählbar)

## Voraussetzungen

- Python 3.8+
- PyQt5

```bash
python -m pip install PyQt5
```

## Starten (ohne Kompilieren)

```bash
python Serienmail.py
```

Unter Windows genügt ein Doppelklick auf `start_serienmail.bat`.

## EXE bauen (optional, nur zur Verteilung)

Nur nötig, wenn das Programm an Personen ohne Python-Installation weitergegeben werden soll:

```bash
python -m pip install pyinstaller
pyinstaller Serienmail.spec
```

Die fertige EXE liegt danach unter `dist/Serienmail`.

## Hinweise

- Das SMTP-Passwort wird Klartext in `einstellungen.json` gespeichert – Datei nicht weitergeben.
- Viele Provider verlangen ein App-Passwort statt des Kontopassworts.
