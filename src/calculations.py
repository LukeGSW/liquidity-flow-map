"""
calculations.py — Pipeline quantitativa pura (nessuna dipendenza da Streamlit).

Catena: OHLCV per ticker -> dollar volume -> DV per gruppo -> quote (share)
-> z-score di attenzione -> pressione firmata -> rotazione.

Principio fondante: il postulato "la liquidità si trasferisce, non si crea"
è falso sui dollar volume assoluti (il DV aggregato scala con la volatilità:
a marzo 2020 il DV di tutto è triplicato), ma è vero PER COSTRUZIONE sulle
quote: share_g = DV_g / Σ DV somma a 1, quindi un gruppo guadagna quota solo
se altri la perdono. Il "flusso" è la variazione di quota.

Tutte le trasformazioni sono causali (rolling su dati <= t): nessun look-ahead.
Questa proprietà è verificata da scripts/selftest.py.
"""

import numpy as np
import pandas as pd


# === DOLLAR VOLUME ===

def dollar_volume(df: pd.DataFrame, mode: str = "raw") -> pd.Series:
    """
    Dollar volume giornaliero di un singolo ETF.

    Args:
        df:   OHLCV EODHD con colonne 'close', 'adjusted_close', 'volume'
        mode: 'raw' = close * volume (default); 'adj' = adjusted_close * volume

    Returns:
        Serie DV in dollari, indicizzata per data.
    """
    px = df["close"] if mode == "raw" else df["adjusted_close"]
    return (px * df["volume"]).rename("dv")


def group_dollar_volume(data: dict, groups: dict, mode: str = "raw") -> pd.DataFrame:
    """
    DV aggregato per gruppo: somma dei DV dei membri disponibili.

    I giorni in cui un membro non ha dati contribuiscono 0 al gruppo: la quota
    del gruppo risulta sottostimata per `smooth` giorni. I buchi sono rari
    post-2008 e sono conteggiati esplicitamente dal pannello diagnostico
    (colonne giorni_mancanti e volume_zero di data_quality); nel livello
    settoriale (1 ticker per gruppo) un buco distorce tutte le quote, quindi
    va controllato lì con più attenzione.
    I giorni con DV totale nullo (festività parziali nel feed) sono eliminati.

    Args:
        data:   dict ticker -> DataFrame OHLCV
        groups: dict nome gruppo -> lista ticker
        mode:   modalità dollar volume (vedi dollar_volume)

    Returns:
        DataFrame [date x gruppi] con DV in dollari.
    """
    cols = {}
    for gname, tickers in groups.items():
        members = [dollar_volume(data[t], mode) for t in tickers if t in data]
        if not members:
            continue
        cols[gname] = pd.concat(members, axis=1).sum(axis=1, min_count=1)
    dv = pd.DataFrame(cols).sort_index().fillna(0.0)
    return dv[dv.sum(axis=1) > 0]


# === QUOTE ===

def dv_shares(group_dv: pd.DataFrame, smooth: int = 21) -> pd.DataFrame:
    """
    Quote di dollar volume per gruppo, dopo smoothing.

    La media mobile a `smooth` giorni è applicata PRIMA del rapporto, poi si
    rinormalizza: le quote sommano a 1 per costruzione (sistema chiuso).

    Returns:
        DataFrame [date x gruppi] con quote in [0, 1]; le prime smooth-1
        righe sono NaN (warm-up).
    """
    sm = group_dv.rolling(smooth, min_periods=smooth).mean()
    return sm.div(sm.sum(axis=1), axis=0)


def attention_z(shares: pd.DataFrame, window: int = 252, clip: float = 4.0) -> pd.DataFrame:
    """
    Z-score di "attenzione": quota corrente vs la propria storia rolling.

    Serve a due cose: (1) neutralizzare la dominanza strutturale dei gruppi
    grandi (SPY schiaccerebbe tutto il resto), (2) rimuovere il trend secolare
    di adozione degli ETF. Finestra rolling, quindi lo z al giorno t usa solo
    dati <= t: nessun look-ahead.
    """
    mu = shares.rolling(window, min_periods=window).mean()
    sd = shares.rolling(window, min_periods=window).std()
    z = (shares - mu) / sd.replace(0.0, np.nan)
    return z.clip(-clip, clip)


# === PRESSIONE FIRMATA ===

def _direction(df: pd.DataFrame, mode: str = "sign", demean_window: int = 63) -> pd.Series:
    """
    Direzione giornaliera del volume.

    'sign'  = segno del rendimento total-return IN ECCESSO: rendimento su
              adjusted_close meno la propria media rolling a `demean_window`
              giorni. Il segno del rendimento grezzo è inutilizzabile per gli
              ETF cash/bond: per BIL/SHV l'accrual del NAV produce ~+1-2bp al
              giorno e la pressione resterebbe inchiodata a ~+0.9 in permanenza
              (misurato), senza alcuna informazione su accumulo/distribuzione;
              gli stacchi mensili di SHY/IEF/TLT/LQD/HYG aggiungerebbero -1
              spuri sui giorni ex-div. Il demean rolling (causale, dati <= t)
              rimuove il drift; per gli equity cambia pochissimo (media
              giornaliera << volatilità giornaliera).
    'range' = posizione della chiusura nel range del giorno,
              2*(C-L)/(H-L) - 1, clippata in [-1, 1] (i feed EOD reali
              contengono barre sporche con close fuori da [low, high]).
    """
    if mode == "range":
        rng = df["high"] - df["low"]
        loc = np.where(rng > 0, 2.0 * (df["close"] - df["low"]) / rng - 1.0, 0.0)
        return pd.Series(np.clip(loc, -1.0, 1.0), index=df.index)
    ret = df["adjusted_close"].pct_change()
    excess = ret - ret.rolling(demean_window, min_periods=demean_window).mean()
    return np.sign(excess)


def signed_pressure(data: dict, groups: dict, smooth: int = 21,
                    dv_mode: str = "raw", dir_mode: str = "sign",
                    demean_window: int = 63) -> pd.DataFrame:
    """
    Pressione netta firmata per gruppo, in [-1, +1]:

        pressure_g(t) = Σ_rolling(DV * direzione) / Σ_rolling(DV)

    Distingue "tanta attività in acquisto" da "tanta attività in vendita":
    la quota da sola non lo dice (un picco su TLT può essere panico in vendita
    o corsa al rifugio). Caveat onesto: per il gruppo Cash (BIL/SHV) il prezzo
    quasi non si muove al netto dell'accrual, quindi la pressione è
    strutturalmente vicina al rumore — va letta come "assente", non come segnale.
    """
    out = {}
    for gname, tickers in groups.items():
        num, den = None, None
        for t in tickers:
            if t not in data:
                continue
            dv = dollar_volume(data[t], dv_mode)
            sgn = dv * _direction(data[t], dir_mode, demean_window)
            num = sgn if num is None else num.add(sgn, fill_value=0.0)
            den = dv if den is None else den.add(dv, fill_value=0.0)
        if num is None:
            continue
        num_s = num.rolling(smooth, min_periods=smooth).sum()
        den_s = den.rolling(smooth, min_periods=smooth).sum()
        out[gname] = num_s / den_s.replace(0.0, np.nan)
    return pd.DataFrame(out).sort_index()


# === ROTAZIONE ===

def rotation(shares: pd.DataFrame, window: int = 21) -> pd.DataFrame:
    """Variazione della quota su `window` giorni, in punti percentuali."""
    return (shares - shares.shift(window)) * 100.0


# === UTILITÀ ===

def resample_mean(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Downsampling per heatmap e pista (media nel periodo)."""
    return df.resample(freq).mean()


def is_oos_cutoff(index: pd.DatetimeIndex, is_fraction: float = 0.70) -> pd.Timestamp:
    """
    Data di taglio cronologico in-sample / out-of-sample: il primo
    `is_fraction` della storia è IS. Split cronologico, mai casuale:
    su serie storiche un split random distruggerebbe la struttura temporale.
    """
    idx = index.sort_values()
    pos = int(np.floor(len(idx) * is_fraction)) - 1
    pos = max(0, min(pos, len(idx) - 1))
    return idx[pos]


def data_quality(data: dict, dv_mode: str = "raw") -> pd.DataFrame:
    """
    Tabella diagnostica per ticker: copertura e salti sospetti di dollar volume.

    max_salto_dv = massimo rapporto giornaliero tra DV consecutivi (in entrambe
    le direzioni). Valori > ~8 in corrispondenza di split noti (es. USO 1:8 del
    28/04/2020) indicano che la modalità DV scelta (raw/adj in config.DV_MODE)
    è incoerente con l'aggiustamento volumi del feed EODHD.

    giorni_mancanti = barre assenti rispetto al calendario-unione di tutti i
    ticker (dalla prima data del ticker in poi); volume_zero = barre presenti
    ma con volume nullo. Entrambi diventano DV=0 nel gruppo e distorcono la
    quota per la durata dello smoothing: se > 0 su ticker recenti, indagare.
    """
    union_idx = None
    for df in data.values():
        union_idx = df.index if union_idx is None else union_idx.union(df.index)
    rows = []
    for t, df in data.items():
        dv = dollar_volume(df, dv_mode).replace(0.0, np.nan).dropna()
        ratio = pd.concat([dv / dv.shift(1), dv.shift(1) / dv], axis=1).max(axis=1).dropna()
        expected = union_idx[union_idx >= df.index.min()]
        rows.append({
            "ticker": t,
            "prima_data": df.index.min().date(),
            "ultima_data": df.index.max().date(),
            "n_barre": len(df),
            "giorni_mancanti": int(len(expected.difference(df.index))),
            "volume_zero": int((df["volume"] <= 0).sum()),
            "max_salto_dv": round(float(ratio.max()), 1) if len(ratio) else np.nan,
            "data_max_salto": ratio.idxmax().date() if len(ratio) else None,
        })
    return pd.DataFrame(rows).set_index("ticker")
