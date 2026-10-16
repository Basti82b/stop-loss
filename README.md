# Routine: täglicher Stop-Check für die Gruppe "KI-Profitöre"

Eine geplante Aufgabe (Claude-Code-Routine) rechnet jeden Werktag die ATR-Stops neu, vergleicht sie mit den
offenen Stop-Orders bei Scalable und schickt einen kurzen Bericht. **Sie setzt keine Orders.** Gesetzt wird im Chat
nach deiner Bestätigung (`stops-setzen.md`).

## Dateien

| Datei | Zweck |
|---|---|
| `config.json` | Gruppe, ATR-Faktor (3,5), ATR-Periode, Anker-Fenster, Limit-Abschlag |
| `stop_loss_atr_v3.py` | Rechenlogik (Hoch-Stop oder Neustart, Break-even, nur nach oben) |
| `prepare_data.py` | wandelt Scalable-Rohdaten (JSON) in die CSV-Eingaben um |
| `routine-prompt.md` | Anweisung für die geplante Aufgabe |
| `stops-setzen.md` | Ablauf zum Setzen der Stops im Chat (mit Bestätigung je Order) |

Das Original `Stop-Loss via ATR berechnen` bleibt unverändert im Projekt.

## Logik in Kürze

1. Hoch-Stop = 126-Tage-Hoch minus 3,5 × ATR. Liegt er unter dem Kurs, gilt er (Modus "Trailing"). Sonst wäre er
   sofort ausgelöst, und der Stop startet neu bei Kurs minus 3,5 × ATR (Modus "Neustart").
2. Break-even: Liegt der Kaufkurs über dem Ergebnis und mindestens 1 ATR unter dem Kurs, ist der Kaufkurs die Untergrenze.
3. Nur nach oben: Quelle der Wahrheit sind die offenen Verkaufs-Stops bei Scalable. Ein bestehender Stop wird nie
   gesenkt. Es gibt keine eigene Stand-Datei, die zwischen Läufen erhalten bleiben müsste.

Aktionen im Ergebnis: `NEU`, `ANHEBEN`, `UNVERAENDERT`, `PRUEFEN` (Kurs auf oder unter bestehendem Stop), `FEHLER`.

## Einrichtung der geplanten Aufgabe

- **Zeitplan:** Montag bis Freitag, 22:30 Uhr (Europe/Berlin), nach US-Börsenschluss.
- **Prompt:** Inhalt von `routine-prompt.md`.
- **Verbindungen:** Scalable Capital (Lesen reicht), Projects-Tool für `routine/…`.
- **Netzwerk:** Zugriff auf `query1.finance.yahoo.com` und `query2.finance.yahoo.com` freigeben.
- **Dateien:** Empfohlen im Wurzelverzeichnis eines privaten GitHub-Repos, das an die Routine angehängt wird (dort
  kann sie die Dateien sicher klonen). Zusätzlich liegen sie im Projekt "Portfolio" unter `routine/`.
- **Erster Lauf:** Probelauf von Hand starten und prüfen, ob die Dateien gefunden werden und der Bericht stimmt.

## Wichtige Grenzen

- **Kein Limit als Stop.** Eine Verkaufs-Limit-Order unter dem Kurs wird sofort ausgeführt und schützt nicht.
  Die Routine arbeitet deshalb mit Verkaufs-Stops (Typ `stop`, nach Auslösung Verkauf zum Marktpreis). Der Wert
  `Limit_info` (Stop minus 0,5 × ATR) ist nur ein Richtwert für eine Stop-Limit-Order in der Scalable-Oberfläche.
- **Keine automatische Orderabgabe.** Die Schnittstelle verlangt für jede Order eine ausdrückliche Bestätigung
  in einer späteren Nachricht. Das geht in einer unbeaufsichtigten Routine nicht und entspricht deiner Vorgabe,
  vor Orders immer zu bestätigen.
- **Stop-Limit nicht abbildbar.** Die Schnittstelle kennt nur Stop-Market oder Limit. Die bestehende Super-Micro-Order
  (Stop 20,10 €, Limit 20 €) ist eine Stop-Limit-Order. Ein Ersatz wäre ein reiner Stop.
- **Anheben = stornieren und neu setzen.** Dazwischen besteht kurz kein Schutz.
- **Sparplan:** Wächst der Bestand durch Sparplan-Käufe, deckt eine ältere Order nur einen Teil ab. Der Bericht weist darauf hin.
- **Hoch-Stop wirkt selten:** Bei Positionen, die schon weit unter ihrem Hoch stehen, greift der Neustart (Stand 16.10.: bei allen).
- **Rechenwerte, keine Anlageberatung.** Aktien im Minus erhalten ebenfalls einen Stop. Das widerspricht ggf. deinem
  Grundsatz, im Minus nachzukaufen. Du entscheidest beim Setzen.

## Test (manuell)

```
python prepare_data.py quotes.json orders.json
python stop_loss_atr_v3.py
```

Ergebnis steht in `daten/stops_ergebnis.csv`.
