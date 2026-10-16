"""Bereitet die Rohdaten aus den Scalable-MCP-Abfragen fuer das Stop-Skript auf.

Aufruf:
  python prepare_data.py quotes.json orders.json [--out-dir daten]

quotes.json  Liste mit einem Eintrag je Position der Gruppe:
  {"isin": "...", "name": "...", "midPrice": 123.4, "sinceBuy": 0.5095, "filled": 8.087453}
    midPrice  = quote.midPrice aus get_security_quote
    sinceBuy  = performance des Zeitraums SINCE_BUY aus get_security_quote (Dezimalzahl, 0.5095 = +50,95 %)
    filled    = position.filled aus get_portfolio_holdings

orders.json  Liste der offenen Orders (Rohwerte aus list_portfolio_transactions, Status PENDING):
  {"id": "...", "isin": "...", "side": "SELL", "quantity": "7.95", "stopPrice": "92.3", "limitPrice": null}

Erzeugt:
  <out-dir>/ki-profitoere.csv   ISIN;Name;Kaufkurs;Bestand
  <out-dir>/bestand.csv         ISIN;Stop;Limit;Menge;OrderId   (nur Verkaufs-Orders mit Stop-Preis)

Der Kaufkurs wird als  midPrice / (1 + sinceBuy)  abgeleitet. Das ist ein Naeherungswert
(z. B. bei Super Micro Computer, wo die Position verkauft und neu aufgebaut wurde).
"""
import argparse
import json
import os
import sys


def num(x):
    if x is None or x == "":
        return None
    return float(str(x).replace(",", "."))


def fail(msg):
    print(f"FEHLER: {msg}")
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("quotes")
    ap.add_argument("orders")
    ap.add_argument("--out-dir", default="daten")
    args = ap.parse_args()

    with open(args.quotes, encoding="utf-8") as f:
        quotes = json.load(f)
    with open(args.orders, encoding="utf-8") as f:
        orders = json.load(f)

    if not isinstance(quotes, list) or not quotes:
        fail("quotes.json ist leer oder keine Liste")

    seen, positionen = set(), []
    for q in quotes:
        for k in ("isin", "name", "midPrice", "sinceBuy", "filled"):
            if k not in q or q[k] is None:
                fail(f"quotes.json: Feld '{k}' fehlt bei {q.get('isin', q)}")
        isin = q["isin"]
        if isin in seen:
            fail(f"quotes.json: ISIN doppelt: {isin}")
        seen.add(isin)
        mid, sb, filled = num(q["midPrice"]), num(q["sinceBuy"]), num(q["filled"])
        if mid is None or mid <= 0:
            fail(f"ungueltiger Kurs bei {isin}")
        if sb is None or sb <= -1:
            fail(f"ungueltige Performance seit Kauf bei {isin} (muss > -1 sein, Dezimalzahl)")
        kaufkurs = mid / (1 + sb)
        positionen.append((isin, q["name"], kaufkurs, filled))

    bestand, ignoriert = [], []
    for o in orders:
        side = str(o.get("side", "")).upper()
        stop, limit = num(o.get("stopPrice")), num(o.get("limitPrice"))
        if side != "SELL":
            continue
        if stop is None:
            ignoriert.append(f"{o.get('isin')} (Verkaufs-Limit ohne Stop, kein Schutz-Stop)")
            continue
        bestand.append((o["isin"], stop, limit, num(o.get("quantity")), o.get("id", "")))

    os.makedirs(args.out_dir, exist_ok=True)
    p1 = os.path.join(args.out_dir, "ki-profitoere.csv")
    with open(p1, "w", encoding="utf-8") as f:
        f.write("ISIN;Name;Kaufkurs;Bestand\n")
        for isin, name, kk, filled in positionen:
            f.write(f"{isin};{name};{str(round(kk, 4)).replace('.', ',')};{str(filled).replace('.', ',')}\n")
    p2 = os.path.join(args.out_dir, "bestand.csv")
    with open(p2, "w", encoding="utf-8") as f:
        f.write("ISIN;Stop;Limit;Menge;OrderId\n")
        for isin, stop, limit, menge, oid in bestand:
            f.write(f"{isin};{stop};{'' if limit is None else limit};{'' if menge is None else menge};{oid}\n")

    gruppe = {p[0] for p in positionen}
    fremd = [b[0] for b in bestand if b[0] not in gruppe]
    print(f"Positionen: {len(positionen)} -> {p1}")
    print(f"Offene Verkaufs-Stops: {len(bestand)} -> {p2}")
    if fremd:
        print(f"Hinweis: Stops ausserhalb der Gruppe (werden ignoriert): {', '.join(fremd)}")
    if ignoriert:
        print("Hinweis: ignorierte Verkaufs-Orders: " + "; ".join(ignoriert))


if __name__ == "__main__":
    main()
