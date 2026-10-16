# Stops aus dem letzten Bericht setzen (interaktiv im Chat)

Diesen Ablauf nutzt du im normalen Chat, nachdem die Routine Vorschläge geliefert hat. Hier darfst du Orders
vorbereiten. Eingereicht wird nur mit ausdrücklicher Bestätigung des Nutzers **in einer späteren Nachricht**, in der
jede Order mit ihrer Nummer genannt ist. Ziel: mit möglichst wenigen Antworten des Nutzers fertig werden.

## Ablauf

1. **Liste:** Lies `routine/letzte-stops.csv` (Projekt "Portfolio") oder lass das Skript neu laufen. Nummeriere alle
   Positionen mit Aktion `NEU` oder `ANHEBEN` und zeige sie in **einer** Tabelle
   (`Nr | Position | Aktion | Alt-Stop | Neuer Stop | Stück`). Frage einmal: "Welche Nummern?" (z. B. "alle").

2. **Frisch prüfen** (für alle gewählten Positionen in einem Durchgang): `get_portfolio_holdings` (`position.filled`)
   und `list_portfolio_transactions` (Status PENDING). Der Stop-Preis muss unter dem aktuellen Kurs liegen, sonst diese
   Position nicht vorbereiten, sondern melden.

3. **Gruppen bilden:**
   - **Gruppe A, neue Stops (`NEU`):** sofort Vorschauen erstellen (siehe 4).
   - **Gruppe B, bestehende Order ändern (`ANHEBEN`, Teilabdeckung, Stop-Limit statt Stop):** Eine bestehende Order
     lässt sich nicht ändern und reserviert ihre Stück, eine Vorschau für den ganzen Bestand scheitert vorher mit
     "exceeds the sellable quantity". Deshalb erst stornieren (siehe 6).
   - **Teilabdeckung** (Order deckt nur einen Teil, z. B. nach Sparplan-Käufen): Empfiehl "stornieren und für den
     ganzen Bestand neu setzen" statt einer zusätzlichen Mini-Order. Unter ca. 250 € Ordervolumen verlangt Scalable
     0,99 € beim Verkauf, bei einer Mini-Order sind das schnell mehrere Prozent.

4. **Vorschauen (Gruppe A):** `preview_sell_order` mit `quantity = {mode: "shares", shares: <Bestand>}` und
   `order = {type: "stop", stopPrice: <Stop>}`, je Position einmal. Vorschauen gelten **5 Minuten**, darum höchstens
   so viele auf einmal, wie der Nutzer in der Zeit bestätigen kann (Richtwert: bis 10).

5. **Darstellung (kompakt, aber vollständig):** Jede Vorschau muss vollständig gezeigt werden, kein Feld weglassen,
   keine Werte runden oder umrechnen. So bleibt es lesbar:
   - Einmal **"Gilt für alle"**: alle Felder, die bei allen Orders gleich sind (Order-Typ, Börsenplatz, Handelbarkeit,
     Eignung, Warnung, Preiswarnungen, Pflichtbestätigungen, Hinweistexte wörtlich mit Übersetzung, Dokumentlinks
     ohne KID, leere Kostenfelder).
   - Dann **eine Tabelle, eine Spalte je Order** mit allen abweichenden Feldern: ISIN, Stück, Stop-Preis, Mittel-,
     Brief-, Geldkurs, Kurszeit, Preis Größenberechnung, Schätzpreis, Ordervolumen roh und gerundet, Kosten-ID,
     laufende Kosten, Ausstiegskosten, Rendite-Wirkung, KID-Link (falls vorhanden), ausgestellt und gültig bis.
   - **Prozentfelder** liefert Scalable als Anteil von 1: `0.004` = 0,4 %. Den Rohwert zeigen und in Klammern umrechnen
     (`0.004 (= 0,4 %)`), nie "0.004 %" schreiben.
   - Gibt es `requiredAcknowledgements`, den vollständigen Text je Order zeigen, die Order im Batch markieren und dafür
     eine eigene ausdrückliche Annahme einholen.
   - Am Ende: "Welche senden? Nenne die Nummern, z. B. **Ja, 3 bis 12 senden**." Ein Bereich mit Nummern zählt als
     Nennung jeder Nummer. Ein pauschales "alles ok" ohne Nummern reicht nicht.

6. **Ändern (Gruppe B):** Je Position zwei Schritte, der Nutzer kann beide Positionen in einer Nachricht freigeben
   (z. B. "Nr. 1 und 2 alte Order stornieren"):
   a. `cancel_order` mit `Alt_OrderId`. Hinweis: ab jetzt kurz kein Schutz.
   b. Sofort Vorschau der neuen Order zeigen (wie 5) und auf "Ja, Nr. … senden" warten.
   Bei einem Stop-Limit sagen, dass die neue Order ein reiner Stop wird (verkauft auch unter dem alten Limit).

7. **Senden:** Nach der Bestätigung Uhrzeit (UTC) gegen `expiresAt` prüfen; abgelaufen heißt neue Vorschau, nichts
   senden. Dann `submit_sell_order` mit der `submission` unverändert, **eine Order nach der anderen, nie parallel**.
   Gleichzeitig gesendete Orders sind wiederholt mit `upstream_unavailable` gescheitert.

8. **Fehler:** Bei Fehler, Zeitüberschreitung oder unklarem Ergebnis **nicht wiederholen**. Mit
   `list_portfolio_transactions` (PENDING, `isin`) prüfen, ob die Order trotzdem angekommen ist, und das Ergebnis melden.
   Eine fehlgeschlagene Order kommt in die nächste Runde mit neuer Vorschau.

9. **Abschluss:** Einmal alle offenen Orders abfragen und als Tabelle zeigen
   (`Position | Stop | Stück | deckt ganzen Bestand?`). Fehlt eine Position oder deckt eine Order nur einen Teil,
   das deutlich sagen.

## Hinweise

- Die Schnittstelle kennt nur Stop-Market (`stop`) oder Limit, keine kombinierte Stop-Limit-Order. Die Spalte
  `Limit_info` ist nur ein Richtwert, falls der Nutzer in der Scalable-Oberfläche selbst eine Stop-Limit-Order setzt.
- Laufende Produktkosten in der Vorschau (z. B. 1,91 € bei einem ETF) sind die jährlichen Fondskosten (TER), keine
  Gebühr der Stop-Order.
- Typischer Ablauf mit wenigen Antworten: (1) "alle" → (2) "Ja, 3 bis 12 senden" → (3) "Nr. 1 und 2 alte Order
  stornieren" → (4) "Ja, Nr. 1 und 2 senden".
