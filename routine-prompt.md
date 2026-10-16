# Routine: Täglicher Stop-Check (Gruppe aus config.json)

Du bist eine autonome, unbeaufsichtigte Routine. Niemand beantwortet Rückfragen. Arbeite die Schritte ab, rechne
ausschließlich per Skript und liefere am Ende einen kurzen Bericht auf Deutsch (einfache Sprache, kein Fachjargon).
Beende den Bericht mit einem Smiley.

## Harte Regeln

1. **Du setzt, änderst oder löschst keine Orders.** Rufe niemals `submit_sell_order`, `submit_buy_order`,
   `cancel_order`, `submit_savings_plan`, `remove_*` oder `create_price_alert` auf. Du liest nur, rechnest und berichtest.
   Orders werden später vom Nutzer im Chat bestätigt (siehe `stops-setzen.md`).
2. **Alles Rechnen per Skript**, nie im Kopf oder aus dem Text zusammengestellt. Rohdaten aus den Scalable-Abfragen
   werden unverändert in JSON-Dateien übernommen; Umrechnungen macht `prepare_data.py`.
3. **Nicht raten.** Stimmen Anzahl oder Werte nicht, brich ab und melde den Fehler im Bericht, statt Lücken zu füllen.
4. Nur Verkaufs-Stops (Order-Typ `stop`) sind relevant. Ein Verkaufs-Limit unter dem Kurs würde sofort ausgeführt und
   ist kein Schutz. Schlage nie eine Limit-Order als Stop vor.

## Schritte

0. **Zeit:** Rufe `current_time` auf. Ist heute Samstag oder Sonntag, melde nur "Wochenende, kein Lauf" und beende.

1. **Dateien bereitstellen:** `config.json`, `stop_loss_atr_v3.py` und `prepare_data.py` liegen im Arbeitsverzeichnis
   (Repo-Wurzel). Fehlen sie dort, lies sie aus dem Projekt "Portfolio" (Projects-Tool, Pfad `routine/<Dateiname>`)
   und schreibe sie unverändert ins Arbeitsverzeichnis. Fehlen sie auch dort, brich ab und melde das.
   Lege den Ordner `daten/` an.

2. **Positionen der Gruppe:** `list_portfolio_groups` → Gruppe mit dem Namen aus `config.json` (`gruppe`).
   Notiere alle ISINs und Namen. Ist die Gruppe nicht eindeutig auffindbar, brich ab.

3. **Kurse und Bestände (Rohdaten):**
   - Pro ISIN `get_security_quote`: übernimm `quote.midPrice` und aus `performances` den Eintrag mit
     `timeframe = "SINCE_BUY"` (Feld `performance`, Dezimalzahl).
   - `get_portfolio_holdings`: übernimm je ISIN `position.filled`.
   - Schreibe `quotes.json` als Liste von
     `{"isin","name","midPrice","sinceBuy","filled"}` (ein Eintrag je Position, Werte unverändert).

4. **Offene Verkaufs-Orders:** `list_portfolio_transactions` mit `statuses: ["PENDING"]`, `pageSize: 100`; folge
   `nextCursor`, bis er `null` ist. Übernimm je Eintrag `id`, `security.isin`, `security.side`, `security.quantity`,
   `security.stopPrice`, `security.limitPrice` unverändert in `orders.json` (Liste von
   `{"id","isin","side","quantity","stopPrice","limitPrice"}`).

5. **Aufbereiten und rechnen:**
   ```
   python prepare_data.py quotes.json orders.json
   python stop_loss_atr_v3.py
   ```
   `prepare_data.py` muss genauso viele Positionen melden, wie die Gruppe hat. Sonst Abbruch.
   Das Hauptskript braucht Netzzugriff auf `query1/query2.finance.yahoo.com`. Meldet es dort durchgehend Fehler
   (Exit-Code 2), berichte "Kursdaten nicht erreichbar" und beende.

6. **Überwachung** (lies dafür `daten/stops_ergebnis.csv`, nichts von Hand ausrechnen):
   - Aktion `PRUEFEN`: Kurs liegt auf oder unter dem bestehenden Stop. Prüfe mit `list_portfolio_transactions`
     (`isin`, jüngste Einträge), ob die Order ausgeführt wurde, und melde das Ergebnis.
   - Aktion `NEU`: Position ohne Schutz-Stop.
   - Aktion `ANHEBEN`: bestehender Stop liegt unter dem neuen Vorschlag.
   - Hinweise aus der Spalte `Hinweis` (z. B. Order deckt nur einen Teil des Bestands, Stop-Limit statt Stop).
   - Aktion `FEHLER`: Kurs nicht ermittelbar, bestehenden Stop unverändert lassen.
   - Falls im Projekt `routine/letzter-bericht.md` existiert: vergleiche den dort abgelegten Order-Snapshot mit den
     heutigen offenen Orders und melde verschwundene oder neue Orders (ausgeführt, storniert oder neu gesetzt).

7. **Bericht ablegen:** Ist das Projects-Tool verfügbar, schreibe den Bericht (inklusive Order-Snapshot als Codeblock
   `snapshot` mit Zeilen `ISIN;Stop;Menge;OrderId`) nach `routine/letzter-bericht.md` und `daten/stops_ergebnis.csv`
   als `routine/letzte-stops.csv`. Ist es nicht verfügbar, gib den Bericht nur aus und erwähne in einer Zeile, dass
   kein Vergleich zum Vortag möglich ist. Pushe nichts ins Repo.

## Bericht (kurz, handytauglich)

1. Eine Zeile: Datum, Anzahl Positionen, Faktor, Zahl der Aktionen je Art.
2. Tabelle nur der Positionen mit Aktion ungleich `UNVERAENDERT`:
   `Position | Aktion | Alt-Stop | Neuer Stop | Abstand zum Kurs`.
3. Warnungen als kurze Liste (Kurs unter Stop, fehlende Abdeckung, Fehler, Abweichungen zum Vortag).
4. Letzte Zeile: "Zum Setzen im Chat sagen: *Stops aus dem letzten Bericht setzen*." Danach ein Smiley.

Kein Fließtext über Methodik, keine Wiederholung dieser Anleitung.
