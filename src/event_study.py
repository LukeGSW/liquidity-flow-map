"""
event_study.py — Motore dell'event study di fase 2 (protocollo pre-registrato).

Funzioni pure (niente Streamlit): eventi da incroci di soglia dello z,
rendimenti forward, null appaiato per terzile di volatilità con bootstrap,
correzione BH-FDR. Le regole del protocollo (soglie, orizzonti, direzioni
attese) vivono in src/hypotheses.py e research/HYPOTHESES.md: qui c'è solo
la meccanica statistica.

Tutto causale e deterministico (seed fisso): stesso input -> stesso output.
"""

import numpy as np
import pandas as pd

B_DEFAULT = 5000
SEED_DEFAULT = 42
EXCL_RADIUS = 10     # giorni esclusi attorno a ogni evento nel pool dei controlli
MIN_EVENTS = 5       # sotto questa numerosità il test non viene eseguito
MIN_POOL = 30        # controlli minimi nel terzile, altrimenti fallback su tutta la serie


def cross_dates(zseries: pd.Series, threshold: float, direction: int,
                debounce: int = 21) -> list:
    """
    Date in cui lo z incrocia la soglia (direzione +1: sale sopra +threshold;
    -1: scende sotto -threshold), con debounce in giorni di borsa.
    Causale: usa solo z(t-1) e z(t).
    """
    if direction > 0:
        raw = (zseries >= threshold) & (zseries.shift(1) < threshold)
    else:
        raw = (zseries <= -threshold) & (zseries.shift(1) > -threshold)
    pos = np.flatnonzero(raw.values)
    kept, last = [], -10 ** 9
    for p in pos:
        if p - last >= debounce:
            kept.append(p)
            last = p
    return list(zseries.index[kept])


def log_forward(price: pd.Series, h: int, start_lag: int = 0) -> pd.Series:
    """
    Rendimento log forward in %, dal giorno t+start_lag al giorno t+h.
    Con start_lag=0 è il forward classico; con start_lag>0 misura una
    "seconda gamba" (es. da t+21 a t+63 per il riassorbimento).
    """
    lp = np.log(price.astype(float))
    return (lp.shift(-h) - lp.shift(-start_lag)) * 100.0


def realized_vol(log_ret_daily: pd.Series, window: int = 21) -> pd.Series:
    """Volatilità realizzata annualizzata da rendimenti log giornalieri."""
    return log_ret_daily.rolling(window).std() * np.sqrt(252)


def pooled_event_study(events: list, outcomes: dict, vol: pd.Series,
                       direction: int, B: int = B_DEFAULT,
                       seed: int = SEED_DEFAULT) -> dict:
    """
    Event study aggregato con null appaiato per regime di volatilità.

    Args:
        events:    lista di tuple (chiave, data evento)
        outcomes:  dict chiave -> Serie del rendimento forward (%) già calcolato
        vol:       Serie di volatilità per la stratificazione (terzili)
        direction: direzione ATTESA dell'effetto (+1 o -1) — p one-sided

    Null: per ogni evento si estrae un controllo dalla STESSA serie e dallo
    stesso terzile di volatilità (esclusi i giorni entro EXCL_RADIUS da un
    evento); B ricampionamenti danno la distribuzione della media sotto H0.

    Returns:
        dict con n, effect (media eventi), null (centro bootstrap),
        excess (effect - null), p (one-sided nella direzione attesa).
    """
    terc = pd.qcut(vol.dropna(), 3, labels=False, duplicates="drop")
    rng = np.random.default_rng(seed)

    excluded = {}
    for k, d in events:
        s = outcomes.get(k)
        if s is None or d not in s.index:
            continue
        p = s.index.get_loc(d)
        lo, hi = max(0, p - EXCL_RADIUS), min(len(s.index), p + EXCL_RADIUS + 1)
        excluded.setdefault(k, set()).update(s.index[lo:hi])

    pools = {}
    for k, s in outcomes.items():
        tt = terc.reindex(s.index)
        base = s.notna() & tt.notna() & ~s.index.isin(list(excluded.get(k, set())))
        for t in (0, 1, 2):
            pools[(k, t)] = s[base & (tt == t)].values
        pools[(k, "all")] = s[base].values

    evt = []
    for k, d in events:
        s = outcomes.get(k)
        if s is None or d not in s.index or pd.isna(s.loc[d]):
            continue
        t = terc.get(d, np.nan)
        t = int(t) if not pd.isna(t) else 1
        pool = pools.get((k, t), np.array([]))
        if len(pool) < MIN_POOL:
            pool = pools.get((k, "all"), np.array([]))
        if len(pool) == 0:
            continue
        evt.append((float(s.loc[d]), pool))

    if len(evt) < MIN_EVENTS:
        return {"n": len(evt), "effect": np.nan, "null": np.nan,
                "excess": np.nan, "p": np.nan}

    vals = np.array([v for v, _ in evt])
    boot = np.empty(B)
    for b in range(B):
        boot[b] = np.mean([pool[rng.integers(len(pool))] for _, pool in evt])
    m0 = float(boot.mean())
    mean_evt = float(vals.mean())
    if direction > 0:
        p = (1.0 + np.sum(boot >= mean_evt)) / (B + 1.0)
    else:
        p = (1.0 + np.sum(boot <= mean_evt)) / (B + 1.0)
    return {"n": len(vals), "effect": mean_evt, "null": m0,
            "excess": mean_evt - m0, "p": float(p)}


def bh_fdr(pvals: list) -> list:
    """Q-value di Benjamini-Hochberg (controllo del false discovery rate)."""
    p = np.asarray(pvals, dtype=float)
    m = len(p)
    order = np.argsort(p)
    q = np.empty(m)
    prev = 1.0
    for back, i in enumerate(order[::-1]):
        rank = m - back
        prev = min(prev, p[i] * m / rank)
        q[i] = prev
    return q.tolist()
