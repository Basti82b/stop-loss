# Stops aus dem letzten Bericht setzen (interaktiv im Chat)

Diesen Ablauf nutzt du im normalen Chat, nachdem die Routine Vorschläge geliefert hat. Hier darfst du Orders
vorbereiten. Eingereicht wird nur mit ausdrücklicher Bestätigung des Nutzers, **für jede Order einzeln und in einer
späteren Nachricht**.

## Ablauf

1. Lies `routine/letzte-stops.csv` (Projekt "Portfolio") oder lass das Skript neu laufen. Zeige die Positionen mit
   Aktion `NEU` und `ANHEBEN` kurz in einer Tabelle und frage, welche gesetzt werden sollen.
2. Prüfe je gewählter Position frisch: aktueller Kurs (`get_security_quote`), Bestand (`get_portfolio_holdings`,
   `position.filled`) und offene Orders (`list_portfolio_transactions`, Status PENDING).
   Der Stop-Preis muss unter dem aktuellen Kurs liegen. Sonst nicht senden, sondern melden.
3. **Neue Order (`NEU`):** `preview_sell_order` mit `quantity = {mode: "shares", shares: <Bestand>}` und
   `order = {type: "stop", stopPrice: <Stop>}`. Stelle die komplette `userReview` unverändert dar, nenne alle
   Pflichthinweise und frage nach Bestätigung für genau diese Order.
4. **Anheben (`ANHEBEN`):** Zeige zuerst die Vorschau der neuen Order. Eine bestehende Stop-Order lässt sich nicht
   ändern, sie muss storniert und neu gesetzt werden. Dazwischen besteht kurz kein Schutz. Weise darauf hin. Frage
   getrennt nach (a) Stornierung der alten Order (`cancel_order` mit `Alt_OrderId`) und (b) Einreichung der neuen Order.
5. `submission` aus der Vorschau unverändert an `submit_sell_order` übergeben, erst nach der Bestätigung. Nie wiederholen
   oder automatisch erneut versuchen. Bei Zeitüberschreitung oder unklarem Ergebnis: Ergebnis melden, nichts wiederholen.
6. Nach jeder Order: kurz sagen, was passiert ist. Danach beim nächsten Lauf der Routine erscheint der neue Stand
   automatisch als bestehender Stop.

## Hinweise

- Die Schnittstelle kennt nur Stop-Market (`stop`) oder Limit, keine kombinierte Stop-Limit-Order. Die Spalte
  `Limit_info` ist nur ein Richtwert, falls du in der Scalable-Oberfläche selbst eine Stop-Limit-Order setzen willst.
- Deckt eine bestehende Order nur einen Teil des Bestands (z. B. wegen Sparplan-Käufen), steht das im `Hinweis`.
  Eine Mengenanpassung läuft wie ein Anheben (stornieren und neu setzen).
