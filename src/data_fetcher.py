"""
data_fetcher.py — Fetch e caching dei dati EODHD.

Solo I/O: nessun calcolo quantitativo qui (vive in calculations.py).
"""

import pandas as pd
import requests
import streamlit as st

EODHD_BASE = "https://eodhd.com/api/eod"


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def fetch_ohlcv_cached(ticker: str, start: str, api_key: str) -> pd.DataFrame:
    """
    Scarica lo storico EOD di un ticker da EODHD (da `start` a oggi).

    Args:
        ticker:  simbolo EODHD (es. 'SPY.US')
        start:   data inizio YYYY-MM-DD
        api_key: chiave API EODHD

    Returns:
        DataFrame indicizzato per data con open/high/low/close/adjusted_close/volume.

    Raises:
        requests.HTTPError su errori API, ValueError su payload vuoto.
    """
    url = (
        f"{EODHD_BASE}/{ticker}"
        f"?from={start}&period=d&api_token={api_key}&fmt=json"
    )
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    if not payload:
        raise ValueError(f"nessun dato restituito per {ticker}")
    df = pd.DataFrame(payload)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    cols = ["open", "high", "low", "close", "adjusted_close", "volume"]
    return df[[c for c in cols if c in df.columns]].astype(float)


def fetch_universe(tickers: list, start: str, api_key: str):
    """
    Scarica l'intero universo, ticker per ticker, senza fermarsi al primo errore.

    Returns:
        (data, errors): dict ticker -> DataFrame, dict ticker -> messaggio errore
    """
    data, errors = {}, {}
    progress = st.progress(0.0, text="Download dati EODHD…")
    for i, t in enumerate(tickers):
        try:
            data[t] = fetch_ohlcv_cached(t, start, api_key)
        except Exception as exc:  # noqa: BLE001 — un ticker rotto non deve bloccare l'app
            errors[t] = str(exc)
        progress.progress((i + 1) / len(tickers), text=f"Download {t} ({i + 1}/{len(tickers)})")
    progress.empty()
    return data, errors
