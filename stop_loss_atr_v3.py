"""Stop-Loss via ATR - Version 3 (zustandslos, fuer die taegliche Routine).

Logik je Position (Faktor F aus config.json, Standard 3,5):
  1. Hoch-Stop   = Anker (126-Tage-Hoch) - F * ATR
     - liegt der Hoch-Stop unter dem Kurs -> Kandidat = Hoch-Stop        (Modus "Trailing")
     - sonst (waere sofort ausgeloest)    -> Kandidat = Kurs - F * ATR   (Modus "Neustart")
  2. Break-even: liegt der Kaufkurs ueber dem Kandidaten und mindestens 1 ATR unter dem Kurs,
     wird der Kaufkurs zur Untergrenze                                    (Modus "Break-even")
  3. Nur nach oben: existiert bei Scalable schon ein Verkaufs-Stop (bestand.csv), wird der
     Stop nur angehoben, nie gesenkt                                      (Aktion "ANHEBEN")

Der Stand wird NICHT in einer eigenen Datei gefuehrt. Quelle der Wahrheit sind die offenen
Verkaufs-Orders bei Scalable (bestand.csv, erzeugt von prepare_data.py).

Aufruf:
  python stop_loss_atr_v3.py [--input daten/ki-profitoere.csv] [--bestand daten/bestand.csv]
                             [--out daten/stops_ergebnis.csv] [--config config.json]

Das Skript setzt und aendert KEINE Orders. Es berechnet nur Vorschlaege.
"""
import argparse
import json
import os
import sys
import time

import pandas as pd
import requests

HEADERS = {"User-Agent": "Mozilla/5.0"}

DEFAULT_CFG = {
    "atr_faktor": 3.5,
    "atr_periode": 14,
    "anker_tage": 126,
    "limit_abschlag_atr": 0.5,
    "be_min_atr": 1.0,
    "hoch_stop_min_abstand_atr": 0.0,
    "warnung_nahe_am_kurs_prozent": 2.0,
}

# Feste Ticker-Overrides (EUR-Listings, XETRA bevorzugt, Fallbacks)
OVERRIDES = {
    "NL0010273215": ["ASME.DE", "ASML.DE", "ASML.AS"],
    "US8740391003": ["TSFA.DE", "TSFA.F"],
    "IE00BK5BCD43": ["XMLD.DE", "IE00BK5BCD43.SG"],
    "IE00BDVPNG13": ["WTAI.MI", "WTAI.PA"],  # kein XETRA-Listing bei Yahoo; Mailand/Paris in EUR
}


def num(x):
    """Zahl aus Text mit Komma oder Punkt; NaN wenn leer/ungueltig."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return float("nan")
    return pd.to_numeric(str(x).replace(",", "."), errors="coerce")


def load_cfg(path):
    cfg = dict(DEFAULT_CFG)
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg.update({k: v for k, v in json.load(f).items() if k in DEFAULT_CFG})
    return cfg


def yahoo_search(q):
    r = requests.get("https://query2.finance.yahoo.com/v1/finance/search",
                     params={"q": q, "quotesCount": 15}, headers=HEADERS, timeout=15)
    return [x["symbol"] for x in r.json().get("quotes", []) if "symbol" in x]


def get_history(symbol):
    r = requests.get(f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}",
                     params={"range": "6mo", "interval": "1d"}, headers=HEADERS, timeout=15)
    j = r.json()["chart"]
    if j.get("error") or not j.get("result"):
        raise ValueError("keine Kursdaten")
    res = j["result"][0]
    q = res["indicators"]["quote"][0]
    if "high" not in q:
        raise ValueError("keine Kursdaten")
    df = pd.DataFrame({"High": q["high"], "Low": q["low"], "Close": q["close"]}).dropna()
    return df, res["meta"].get("currency", "?")


def resolve(isin, name, min_len):
    candidates = list(OVERRIDES.get(isin, []))
    if not candidates:
        for q in (isin, name):
            syms = yahoo_search(q)
            candidates += [s for s in syms if s.upper().endswith(".DE")]
            candidates += [s.split(".")[0] + ".DE" for s in syms]
    seen, uniq = set(), []
    for s in candidates:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    for s in uniq[:8]:
        try:
            h, cur = get_history(s)
            if len(h) >= min_len:
                return s, h, cur
        except Exception:
            continue
        time.sleep(0.2)
    raise ValueError("kein handelbares Listing gefunden")


def atr(df, period):
    pc = df["Close"].shift(1)
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - pc).abs(), (df["Low"] - pc).abs()], axis=1).max(axis=1)
    return float(tr.ewm(alpha=1 / period, adjust=False).mean().iloc[-1])


def calc_candidate(kurs, anchor, a, kaufkurs, cfg):
    """Kandidat fuer den Stop (noch ohne 'nur nach oben')."""
    f = cfg["atr_faktor"]
    hoch_stop = anchor - f * a
    if kurs - hoch_stop > cfg["hoch_stop_min_abstand_atr"] * a and hoch_stop < kurs:
        kandidat, modus = hoch_stop, "Trailing"
    else:
        kandidat, modus = kurs - f * a, "Neustart"
    if not pd.isna(kaufkurs) and kaufkurs <= kurs - cfg["be_min_atr"] * a and kaufkurs > kandidat:
        kandidat, modus = float(kaufkurs), "Break-even"
    return kandidat, modus, hoch_stop


def load_bestand(path):
    """Offene Verkaufs-Stops: ISIN -> dict(stop, limit, menge, ids, anzahl)."""
    if not path or not os.path.exists(path):
        return {}
    b = pd.read_csv(path, sep=";", dtype=str)
    out = {}
    for isin, g in b.groupby("ISIN"):
        stops = g["Stop"].map(num)
        limits = g["Limit"].map(num) if "Limit" in g else pd.Series([float("nan")] * len(g))
        mengen = g["Menge"].map(num) if "Menge" in g else pd.Series([float("nan")] * len(g))
        i = stops.idxmax()
        out[isin] = {
            "stop": float(stops.loc[i]),
            "limit": float(limits.loc[i]) if not pd.isna(limits.loc[i]) else float("nan"),
            "menge": float(mengen.sum()),
            "ids": ",".join(g["OrderId"].astype(str)) if "OrderId" in g else "",
            "anzahl": len(g),
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="daten/ki-profitoere.csv")
    ap.add_argument("--bestand", default="daten/bestand.csv")
    ap.add_argument("--out", default="daten/stops_ergebnis.csv")
    ap.add_argument("--config", default="config.json")
    args = ap.parse_args()

    cfg = load_cfg(args.config)
    f, period = cfg["atr_faktor"], cfg["atr_periode"]
    bestand = load_bestand(args.bestand)
    print(f"Faktor {f} | offene Verkaufs-Stops bei Scalable: {len(bestand)}")

    df_in = pd.read_csv(args.input, sep=";")
    kk_col = next((c for c in df_in.columns if "kauf" in c.lower()), None)
    bs_col = next((c for c in df_in.columns if "bestand" in c.lower()), None)
    df_in[kk_col] = df_in[kk_col].map(num)
    if bs_col:
        df_in[bs_col] = df_in[bs_col].map(num)

    cols = ["Symbol", "Currency", "Kurs", "Anker", "ATR", "Hoch_Stop", "Kandidat", "Stop", "Limit_info",
            "Modus", "Aktion", "Alt_Stop", "Alt_Menge", "Alt_OrderId", "Stop_vs_Kurs_%", "Hinweis"]
    rows = []
    for _, rec in df_in.iterrows():
        isin, name = rec["ISIN"], rec["Name"]
        kaufkurs = rec[kk_col]
        bestand_stueck = rec[bs_col] if bs_col else float("nan")
        row = dict.fromkeys(cols)
        try:
            sym, h, cur = resolve(isin, name, period + 1)
            a = atr(h, period)
            kurs = float(h["Close"].iloc[-1])
            anchor = float(h["High"].tail(cfg["anker_tage"]).max())
            kandidat, modus, hoch_stop = calc_candidate(kurs, anchor, a, kaufkurs, cfg)

            stop, hinweise = kandidat, []
            alt = bestand.get(isin)
            if alt is None:
                aktion = "NEU"
            else:
                row.update({"Alt_Stop": round(alt["stop"], 2), "Alt_Menge": round(alt["menge"], 6),
                            "Alt_OrderId": alt["ids"]})
                if alt["stop"] >= kandidat:
                    stop, aktion = alt["stop"], "UNVERAENDERT"
                    modus = modus + " (alter Stop gehalten)"
                else:
                    aktion = "ANHEBEN"
                if kurs <= alt["stop"]:
                    aktion = "PRUEFEN"
                    hinweise.append("Kurs liegt auf/unter dem bestehenden Stop")
                if alt["anzahl"] > 1:
                    hinweise.append(f"{alt['anzahl']} Stop-Orders vorhanden")
                if not pd.isna(alt["limit"]):
                    hinweise.append("bestehende Order ist Stop-Limit (MCP kann nur Stop-Market)")
                if not pd.isna(bestand_stueck) and alt["menge"] < bestand_stueck * 0.99:
                    hinweise.append(f"Order deckt {alt['menge']:g} von {bestand_stueck:g} Stueck")
            limit_info = stop - cfg["limit_abschlag_atr"] * a
            abstand = (stop - kurs) / kurs * 100
            if abstand > -cfg["warnung_nahe_am_kurs_prozent"]:
                hinweise.append(f"Stop nur {abs(abstand):.1f} % unter Kurs")
            if pd.isna(kaufkurs):
                hinweise.append("Kaufkurs fehlt")
            row.update({"Symbol": sym, "Currency": cur, "Kurs": round(kurs, 2), "Anker": round(anchor, 2),
                        "ATR": round(a, 2), "Hoch_Stop": round(hoch_stop, 2), "Kandidat": round(kandidat, 2),
                        "Stop": round(stop, 2), "Limit_info": round(limit_info, 2), "Modus": modus,
                        "Aktion": aktion, "Stop_vs_Kurs_%": round(abstand, 1), "Hinweis": " | ".join(hinweise)})
        except Exception as e:
            print(f"{isin} ({name}): FEHLER - {e}")
            row.update({"Aktion": "FEHLER", "Hinweis": str(e)})
            alt = bestand.get(isin)
            if alt:
                row.update({"Alt_Stop": round(alt["stop"], 2), "Alt_Menge": round(alt["menge"], 6),
                            "Alt_OrderId": alt["ids"]})
        rows.append(row)
        time.sleep(0.3)

    out = pd.concat([df_in.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    out.to_csv(args.out, sep=";", index=False)
    show = ["Name", "Kurs", "Stop", "Stop_vs_Kurs_%", "Modus", "Aktion", "Alt_Stop", "Hinweis"]
    print(out[show].to_string(index=False))
    print("\nAktionen:", out["Aktion"].value_counts().to_dict())
    print(f"Geschrieben: {args.out}")
    if (out["Aktion"] == "FEHLER").sum() > len(out) / 2:
        sys.exit(2)


if __name__ == "__main__":
    main()
