"""Rueckrechnung der ATR-Stop-Logik (v3) fuer mehrere Faktoren und Mindestabstaende.

Je Position und Variante wird taeglich wie in stop_loss_atr_v3.calc_candidate ein Stop berechnet
(Trailing / Neustart) und nur nach oben nachgezogen. Break-even ist abgeschaltet, weil der
heutige Kaufkurs fuer vergangene Zeitraeume keine Bedeutung hat.

Ausgeloest wird, wenn das Tagestief am Folgetag den Stop erreicht (wie bei Scalable).
Verkaufspreis = min(Eroeffnung, Stop). Danach 20 Handelstage Pause, dann Neueinstieg zum
Schlusskurs. Bewertet wird
  - jedes Ausloesen: Kurs 20 / 60 Handelstage spaeter im Vergleich zum Verkaufspreis
      hoeher -> Verkauf hat Gewinn gekostet, tiefer -> Verkauf hat Verlust gespart
  - die ganze Strecke: Ergebnis mit Stops (Pause ohne Zins) gegen Kaufen und Halten

Aufruf: python backtest_stops.py [--ergebnis daten/stops_ergebnis.csv] [--faktoren 3,3.5,4,4.5,5]
                                 [--abstaende 0,1] [--pause 20] [--range 5y]
Setzt keine Orders.
"""
import argparse
import time

import pandas as pd
import requests

from stop_loss_atr_v3 import HEADERS, calc_candidate, load_cfg


def history(symbol, rng):
    r = requests.get(f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}",
                     params={"range": rng, "interval": "1d"}, headers=HEADERS, timeout=20)
    res = r.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    idx = pd.to_datetime(res["timestamp"], unit="s").normalize()
    return pd.DataFrame({"Open": q["open"], "High": q["high"], "Low": q["low"], "Close": q["close"]},
                        index=idx).dropna()


def simulate(df, cfg, pause, schluss=False):
    pc = df["Close"].shift(1)
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - pc).abs(), (df["Low"] - pc).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / cfg["atr_periode"], adjust=False).mean().values
    anchor = df["High"].rolling(cfg["anker_tage"], min_periods=cfg["anker_tage"]).max().values
    o, lo, c = df["Open"].values, df["Low"].values, df["Close"].values
    start = cfg["anker_tage"]
    events, stop, wert, warten = [], None, 1.0, 0
    t = start
    while t < len(df) - 1:
        if warten:
            warten -= 1
            t += 1
            continue
        kand, _, _ = calc_candidate(c[t], anchor[t], atr[t], float("nan"), cfg)
        stop = kand if stop is None else max(stop, kand)
        if schluss and c[t + 1] <= stop and t + 2 < len(df):
            # Schlusskurs-Stop: Verkauf zur Eroeffnung des naechsten Tages
            exit_px = o[t + 2]
            wert *= exit_px / c[t]
            t += 1
        elif not schluss and lo[t + 1] <= stop:
            exit_px = min(o[t + 1], stop)
            wert *= exit_px / c[t]
        else:
            exit_px = None
        if exit_px is not None:
            ev = {"Datum": df.index[t + 1].date(), "Verkauf": round(exit_px, 4),
                  "Abstand_%": (stop / c[t] - 1) * 100}
            for n in (20, 60):
                j = t + 1 + n
                ev[f"r{n}"] = (c[j] / exit_px - 1) * 100 if j < len(df) else float("nan")
            events.append(ev)
            stop, warten = None, pause  # Neueinstieg zum Schlusskurs nach der Pause
        else:
            wert *= c[t + 1] / c[t]
        t += 1
    halten = c[-1] / c[start]
    return events, (len(df) - 1 - start) / 252, (wert - 1) * 100, (halten - 1) * 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ergebnis", default="daten/stops_ergebnis.csv")
    ap.add_argument("--faktoren", default="3,3.5,4,4.5,5")
    ap.add_argument("--abstaende", default="0,1")
    ap.add_argument("--pause", type=int, default=20)
    ap.add_argument("--range", default="5y")
    ap.add_argument("--schluss", action="store_true", help="nur Schlusskurse loesen aus")
    ap.add_argument("--out", default="daten/backtest_ereignisse.csv")
    args = ap.parse_args()
    base = load_cfg("config.json")
    faktoren = [float(x) for x in args.faktoren.split(",")]
    abstaende = [float(x) for x in args.abstaende.split(",")]

    pos = pd.read_csv(args.ergebnis, sep=";", dtype=str)
    alle, strecke = [], []
    for _, p in pos.iterrows():
        if not isinstance(p.get("Symbol"), str):
            print(f"{p['Name']}: kein Symbol, uebersprungen")
            continue
        try:
            df = history(p["Symbol"], args.range)
        except Exception as e:
            print(f"{p['Name']}: FEHLER {e}")
            continue
        etf = "(Acc)" in p["Name"] or "(Dist)" in p["Name"]
        for f in faktoren:
            for m in abstaende:
                cfg = dict(base, atr_faktor=f, hoch_stop_min_abstand_atr=m)
                ev, jahre, mit, halten = simulate(df, cfg, args.pause, args.schluss)
                for e in ev:
                    e.update({"Name": p["Name"], "ETF": etf, "Faktor": f, "Mindestabstand": m})
                alle += ev
                strecke.append({"Name": p["Name"], "ETF": etf, "Faktor": f, "Mindestabstand": m,
                                "Jahre": jahre, "Ausloesungen": len(ev), "mit_Stops_%": mit,
                                "Halten_%": halten})
        print(f"{p['Name']}: {p['Symbol']}, {jahre:.1f} Jahre ab {df.index[base['anker_tage']].date()}")
        time.sleep(0.3)

    ev, st = pd.DataFrame(alle), pd.DataFrame(strecke)
    ev.to_csv(args.out, sep=";", index=False)
    st.to_csv(args.out.replace(".csv", "_strecke.csv"), sep=";", index=False)
    pd.set_option("display.width", 220)

    def per_event(g):
        return pd.Series({
            "Ausloesungen": len(g),
            "gekostet": (g["r60"] > 0).sum(),
            "gespart": (g["r60"] <= 0).sum(),
            "r60_Median_%": g["r60"].median(),
            "gespart_Mittel_%": g.loc[g["r60"] <= 0, "r60"].mean(),
        })

    def per_strecke(g):
        return pd.Series({
            "je_Pos_Jahr": (g["Ausloesungen"] / g["Jahre"]).mean(),
            "mit_Stops_Median_%": g["mit_Stops_%"].median(),
            "Halten_Median_%": g["Halten_%"].median(),
            "Stops_besser": (g["mit_Stops_%"] > g["Halten_%"]).sum(),
            "Positionen": len(g),
        })

    keys = ["ETF", "Mindestabstand", "Faktor"]
    print("\n== Je Ausloesen (Kurs 60 Handelstage spaeter) ==")
    print(ev.groupby(keys).apply(per_event).round(1).to_string())
    print("\n== Ganze Strecke: mit Stops gegen Halten ==")
    print(st.groupby(keys).apply(per_strecke).round(1).to_string())
    print(f"\nGeschrieben: {args.out}")


if __name__ == "__main__":
    main()
