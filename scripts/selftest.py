"""
selftest.py — Verifica offline della pipeline su dati sintetici.

Testa solo src/calculations.py: niente rete, niente Streamlit.
I check chiave sono gli invarianti della metodologia:
    - le quote sommano a 1 (il "sistema chiuso" che rende vero il postulato)
    - nessun look-ahead: le metriche al giorno t non cambiano se si tronca
      la storia a t (guardia contro futuri refactor con normalizzazioni
      full-sample o rolling centrati)
    - la pressione firmata resta in [-1, +1]

Uso:
    python scripts/selftest.py            # test offline
    python scripts/selftest.py --live     # + smoke test EODHD con chiave demo (VTI.US)

Exit code 0 = tutti i check passati.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import numpy as np
import pandas as pd

from src.calculations import (
    dv_shares, group_dollar_volume, attention_z,
    signed_pressure, rotation, is_oos_cutoff,
)
from src.event_study import pooled_event_study, bh_fdr

# Su Windows con stdout rediretto (subprocess, CI, redirect su file) la console
# cp1252 non codifica i caratteri non-ASCII e la print farebbe exit 1 anche con
# tutti i check PASS.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SMOOTH, Z_WIN, ROT_WIN = 21, 252, 21


def make_synthetic():
    """5 ticker sintetici in 2 gruppi, ~6 anni di barre giornaliere, seed fisso."""
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2015-01-02", "2020-12-31")
    n = len(dates)
    data = {}
    for i, t in enumerate(["AAA", "BBB", "CCC", "DDD", "EEE"]):
        ret = rng.normal(0.0003, 0.012, n)
        close = 100.0 * (1 + i) * np.exp(np.cumsum(ret))
        spread = np.abs(rng.normal(0.005, 0.003, n))
        high = close * (1 + spread)
        low = close * (1 - spread)
        volume = np.exp(rng.normal(14 + i * 0.5, 0.4, n))
        data[t] = pd.DataFrame({
            "open": close * (1 + rng.normal(0, 0.002, n)),
            "high": high, "low": low, "close": close,
            "adjusted_close": close, "volume": volume,
        }, index=dates)
    groups = {"Gruppo A": ["AAA", "BBB", "CCC"], "Gruppo B": ["DDD", "EEE"]}
    return data, groups


def make_accrual_synthetic():
    """
    Serie cash-like flow-neutral (stile BIL): NAV che matura ~+1.7bp/giorno,
    stacco mensile ~35bp, prezzi quantizzati al centesimo, volume indipendente
    dal segno. Per costruzione NON contiene informazione di accumulo o
    distribuzione: una pressione firmata onesta deve restare vicina a zero.
    """
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2021-01-04", "2024-12-31")
    n = len(dates)
    daily = 1.7e-4 + rng.normal(0.0, 3e-5, n)
    tr = 91.5 * np.cumprod(1.0 + daily)
    months = dates.month
    is_last_bd = np.append(months[:-1] != months[1:], True)
    close = tr.copy()
    cum_div = 0.0
    for i in range(n):
        if is_last_bd[i]:
            cum_div += tr[i] * 0.0035
        close[i] = tr[i] - cum_div
    close = np.round(close, 2)
    df = pd.DataFrame({
        "open": close, "high": close + 0.01, "low": close - 0.01,
        "close": close, "adjusted_close": tr,
        "volume": np.exp(rng.normal(13.0, 0.4, n)),
    }, index=dates)
    return {"CSH": df}, {"Cash": ["CSH"]}


def run_pipeline(data, groups):
    """Pipeline completa identica a quella dell'app."""
    gdv = group_dollar_volume(data, groups)
    shares = dv_shares(gdv, SMOOTH)
    z = attention_z(shares, Z_WIN)
    press = signed_pressure(data, groups, SMOOTH)
    rot = rotation(shares, ROT_WIN)
    return gdv, shares, z, press, rot


def main():
    data, groups = make_synthetic()
    gdv, shares, z, press, rot = run_pipeline(data, groups)
    checks = []

    # --- 1. Le quote sommano a 1 (sistema chiuso) ---
    sums = shares.dropna().sum(axis=1)
    checks.append(("quote sommano a 1", np.allclose(sums, 1.0, atol=1e-12)))

    # --- 2. Quote in [0, 1] ---
    sh = shares.dropna()
    checks.append(("quote in [0,1]", bool((sh.values >= 0).all() and (sh.values <= 1).all())))

    # --- 3. Nessun look-ahead: troncare la storia non cambia il passato ---
    ok_causal = True
    full_dates = shares.dropna(how="all").index
    for k in [400, 800, 1200]:
        t_cut = full_dates[k]
        data_trunc = {t: df.loc[:t_cut] for t, df in data.items()}
        _, sh_t, z_t, pr_t, rot_t = run_pipeline(data_trunc, groups)
        for full_df, trunc_df, name in [(shares, sh_t, "shares"), (z, z_t, "z"),
                                        (press, pr_t, "pressure"), (rot, rot_t, "rotation")]:
            a = full_df.loc[t_cut].values.astype(float)
            b = trunc_df.loc[t_cut].values.astype(float)
            same = np.allclose(a, b, atol=1e-9, equal_nan=True)
            if not same:
                ok_causal = False
                print(f"    look-ahead in {name} a {t_cut.date()}: full={a} trunc={b}")
    checks.append(("nessun look-ahead (shares/z/pressione/rotazione)", ok_causal))

    # --- 4. Pressione firmata in [-1, +1] ---
    pv = press.dropna().values
    checks.append(("pressione in [-1,+1]", bool((pv >= -1 - 1e-9).all() and (pv <= 1 + 1e-9).all())))

    # --- 5. Rotazione coerente con la definizione ---
    manual = (shares - shares.shift(ROT_WIN)) * 100.0
    checks.append(("rotazione = delta quota * 100", bool(rot.equals(manual))))

    # --- 6. Cutoff IS/OOS al 70% della storia ---
    cut = is_oos_cutoff(shares.index, 0.70)
    frac = (shares.index <= cut).mean()
    checks.append(("cutoff IS/OOS ~70%", bool(abs(frac - 0.70) < 0.01)))

    # --- 7. Niente pinning da accrual: su una serie cash-like flow-neutral
    #        la pressione deve restare vicina a zero (col segno del rendimento
    #        GREZZO risulterebbe inchiodata a ~+0.9) ---
    acc_data, acc_groups = make_accrual_synthetic()
    acc_press = signed_pressure(acc_data, acc_groups, SMOOTH, "adj", "sign").dropna()
    acc_mean = float(acc_press.mean().iloc[0]) if len(acc_press) else 0.0
    ok_acc = len(acc_press) > 100 and abs(acc_mean) < 0.25
    if not ok_acc:
        print(f"    pressione media su serie accrual-only: {acc_mean:+.3f} (atteso ~0)")
    checks.append(("pressione non inchiodata dall'accrual (cash-like ~0)", ok_acc))

    # --- 8. Modalita' 'range' bounded anche con barre sporche
    #        (close fuori da [low, high], presenti nei feed EOD reali) ---
    dirty_data = {t: df.copy() for t, df in data.items()}
    df_d = dirty_data["AAA"]
    i0 = 100
    df_d.iloc[i0, df_d.columns.get_loc("close")] = df_d["high"].iloc[i0] + 5.0
    df_d.iloc[i0, df_d.columns.get_loc("volume")] = df_d["volume"].iloc[i0] * 50.0
    press_rng = signed_pressure(dirty_data, groups, SMOOTH, "raw", "range").dropna()
    prv = press_rng.values
    checks.append(("pressione 'range' in [-1,+1] con barre sporche",
                   bool((prv >= -1 - 1e-9).all() and (prv <= 1 + 1e-9).all())))

    # --- 9. Motore event study: rileva un effetto piantato, one-sided corretto ---
    rng2 = np.random.default_rng(11)
    dates2 = pd.bdate_range("2015-01-01", periods=1500)
    outcome = pd.Series(rng2.normal(0.0, 1.0, 1500), index=dates2)
    vol_s = pd.Series(rng2.uniform(0.1, 0.4, 1500), index=dates2)
    evt_dates = list(dates2[rng2.choice(np.arange(100, 1400), size=30, replace=False)])
    outcome.loc[evt_dates] += 1.5
    events = [("X", d) for d in evt_dates]
    r_pos = pooled_event_study(events, {"X": outcome}, vol_s, +1, B=1000, seed=1)
    r_neg = pooled_event_study(events, {"X": outcome}, vol_s, -1, B=1000, seed=1)
    checks.append(("event study rileva effetto piantato (one-sided)",
                   bool(r_pos["p"] < 0.01 and r_neg["p"] > 0.5)))

    # --- 10. Event study deterministico a parità di seed ---
    r_rep = pooled_event_study(events, {"X": outcome}, vol_s, +1, B=1000, seed=1)
    checks.append(("event study deterministico (stesso seed, stesso p)",
                   bool(r_rep["p"] == r_pos["p"] and r_rep["effect"] == r_pos["effect"])))

    # --- 11. BH-FDR sano: q >= p, q <= 1 ---
    pv = [0.01, 0.04, 0.03, 0.20]
    qv = bh_fdr(pv)
    checks.append(("BH-FDR: q >= p e q <= 1",
                   bool(all(qq >= pp for qq, pp in zip(qv, pv)) and max(qv) <= 1.0)))

    # --- Report ---
    all_ok = True
    for name, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        all_ok &= ok

    # --- Smoke test live opzionale (chiave demo EODHD, solo VTI.US) ---
    if "--live" in sys.argv:
        import requests
        url = ("https://eodhd.com/api/eod/VTI.US"
               "?from=2024-01-01&period=d&api_token=demo&fmt=json")
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            df = pd.DataFrame(resp.json())
            needed = {"date", "close", "adjusted_close", "volume", "high", "low"}
            ok_live = needed.issubset(df.columns) and len(df) > 50
            print(f"[{'PASS' if ok_live else 'FAIL'}] fetch live EODHD (demo, VTI.US): "
                  f"{len(df)} barre, colonne {sorted(df.columns)}")
            all_ok &= ok_live
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] fetch live EODHD: {exc}")
            all_ok = False

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
