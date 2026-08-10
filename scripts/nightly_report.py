"""
nightly_report.py — Job notturno: pipeline completa, rilevazione eventi,
log real-time e report Telegram.

Eseguito da GitHub Actions (.github/workflows/nightly.yml) dopo la chiusura USA.

Logica dei messaggi (per non generare alert-fatigue):
    - nuovi eventi sull'ultima barra (z incrocia ±1.5/±2)  -> ALERT completo
    - sabato mattina (dati del venerdì)                     -> DIGEST settimanale
    - altrimenti                                            -> silenzio

Il file research/live_events_log.csv è il REGISTRO REAL-TIME degli eventi per
il re-test futuro (strada 1 del protocollo): ogni evento viene "chiamato" e
committato prima che i suoi rendimenti forward esistano — look-ahead
impossibile per costruzione.

Uso locale senza secrets:
    python scripts/nightly_report.py --selftest       # rendering su dati finti, niente rete
Uso manuale con secrets (variabili d'ambiente):
    python scripts/nightly_report.py --force-digest   # digest anche se non è sabato
"""

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import numpy as np
import pandas as pd
import requests

from src.config import (
    START_DATE, MACRO_GROUPS, SECTOR_GROUPS, DEFAULT_SMOOTH, Z_WINDOW, DV_MODE,
)
from src.calculations import group_dollar_volume, dv_shares, attention_z
from src.event_study import cross_dates
from src.hypotheses import DEBOUNCE

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
LOG_PATH = os.path.join(ROOT, "research", "live_events_log.csv")
STATE_PATH = os.path.join(ROOT, "research", "nightly_state.json")

THRESHOLDS = (1.5, 2.0)
ACTIVE_Z = 1.5          # soglia "segnale attivo" nei riepiloghi
TELEGRAM_MAX = 4096     # limite hard dell'API sendMessage

LOG_COLUMNS = ["date", "level", "group", "threshold", "direction",
               "z", "share_pct", "logged_at_utc"]


# ===================================================
# FETCH (senza Streamlit: questo script gira su GitHub Actions)
# ===================================================

def fetch_eod(ticker: str, start: str, api_key: str) -> pd.DataFrame:
    """Storico EOD di un ticker da EODHD (stesso parsing di src/data_fetcher)."""
    url = (f"https://eodhd.com/api/eod/{ticker}"
           f"?from={start}&period=d&api_token={api_key}&fmt=json")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    if not payload:
        raise ValueError(f"nessun dato per {ticker}")
    df = pd.DataFrame(payload)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    cols = ["open", "high", "low", "close", "adjusted_close", "volume"]
    return df[[c for c in cols if c in df.columns]].astype(float)


def fetch_universe_plain(tickers: list, start: str, api_key: str):
    data, errors = {}, {}
    for t in tickers:
        try:
            data[t] = fetch_eod(t, start, api_key)
        except Exception as exc:  # noqa: BLE001 — un ticker rotto non ferma il report
            errors[t] = str(exc)
    return data, errors


# ===================================================
# PIPELINE E RILEVAZIONE EVENTI
# ===================================================

def compute_level(data: dict, groups: dict) -> dict:
    """Pipeline congelata per un livello: DV -> quote -> z -> rotazione 21g."""
    dv = group_dollar_volume(data, groups, DV_MODE)
    shares = dv_shares(dv, DEFAULT_SMOOTH)
    z = attention_z(shares, Z_WINDOW)
    rot = (shares - shares.shift(21)) * 100.0
    return {"dv": dv, "shares": shares, "z": z, "rot": rot}


def detect_new_events(level_name: str, lv: dict, last_bar: pd.Timestamp) -> list:
    """Eventi il cui incrocio di soglia cade esattamente sull'ultima barra."""
    out = []
    for g in lv["z"].columns:
        for th in THRESHOLDS:
            for d in (+1, -1):
                evs = cross_dates(lv["z"][g], th, d, DEBOUNCE)
                if evs and evs[-1] == last_bar:
                    out.append({
                        "date": last_bar.date().isoformat(),
                        "level": level_name,
                        "group": g,
                        "threshold": th,
                        "direction": "su" if d > 0 else "giu",
                        "z": round(float(lv["z"][g].loc[last_bar]), 2),
                        "share_pct": round(float(lv["shares"][g].loc[last_bar]) * 100, 2),
                        "logged_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    })
    return out


def merge_for_message(events: list) -> list:
    """Stesso gruppo/direzione con doppio incrocio (1.5 e 2.0 insieme):
    nel messaggio si mostra solo la soglia più alta."""
    best = {}
    for e in events:
        k = (e["level"], e["group"], e["direction"])
        if k not in best or e["threshold"] > best[k]["threshold"]:
            best[k] = e
    return sorted(best.values(), key=lambda e: -abs(e["z"]))


# ===================================================
# LOG EVENTI (registro real-time per il re-test futuro)
# ===================================================

def load_log(path: str = LOG_PATH) -> pd.DataFrame:
    if os.path.exists(path):
        return pd.read_csv(path)
    return pd.DataFrame(columns=LOG_COLUMNS)


def append_log(events: list, path: str = LOG_PATH) -> int:
    """Accoda al log gli eventi non già presenti. Ritorna quanti ne ha aggiunti."""
    log = load_log(path)
    key_cols = ["date", "level", "group", "threshold", "direction"]
    existing = {tuple(r) for r in log[key_cols].astype(str).itertuples(index=False)} \
        if len(log) else set()
    fresh = [e for e in events
             if tuple(str(e[c]) for c in key_cols) not in existing]
    if fresh:
        log = pd.concat([log, pd.DataFrame(fresh)[LOG_COLUMNS]], ignore_index=True)
    # Il file viene scritto SEMPRE (anche solo header): lo step di commit del
    # workflow fa `git add` sul path e non deve mai trovarlo mancante.
    os.makedirs(os.path.dirname(path), exist_ok=True)
    log.to_csv(path, index=False)
    return len(fresh)


# ===================================================
# TILT VALIDATI (specchio degli insight in dashboard)
# ===================================================

def tilt(level: str, group: str, direction: str) -> str:
    if level == "SETTORI":
        if direction == "su":
            return ("tilt: sottoperformance relativa media −1.3% (IS) / −0.6% (OOS) "
                    "a 63g — non significativo")
        return "tilt: recupero relativo medio +0.6% a 63g — non significativo"
    if group == "Oro/Metalli" and direction == "su":
        return ("blow-off di attività (quota +2pp a 21g), nessuna implicazione "
                "di prezzo su GLD (H4 ritirata)")
    if group == "Treasury" and direction == "su":
        return "lieve reversione della quota a 21g (solo IS)"
    if group in ("Treasury", "Credito") and direction == "giu":
        return "quota in recupero a 21-63g (solo IS)"
    return "informazione di regime, nessun tilt validato"


# ===================================================
# RENDERING MESSAGGI (HTML Telegram, autosufficienti)
# ===================================================

def esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _z_leaderboard(lv: dict, last_bar: pd.Timestamp) -> str:
    zrow = lv["z"].loc[:last_bar].iloc[-1].dropna().sort_values(ascending=False)
    parts = []
    for g, v in zrow.items():
        mark = " 🔴" if v >= ACTIVE_Z else (" 🔵" if v <= -ACTIVE_Z else "")
        parts.append(f"{esc(g)} <code>{v:+.1f}</code>{mark}")
    return " · ".join(parts)


def _rotation_line(lv: dict, last_bar: pd.Timestamp, full: bool) -> str:
    rrow = lv["rot"].loc[:last_bar].iloc[-1].dropna().sort_values(ascending=False)
    if rrow.empty:
        return "n.d."
    if full:
        return " · ".join(f"{esc(g)} <code>{v:+.2f}</code>" for g, v in rrow.items())
    up, dn = rrow.index[0], rrow.index[-1]
    return (f"↑ {esc(up)} <code>{rrow.iloc[0]:+.2f}</code>   "
            f"↓ {esc(dn)} <code>{rrow.iloc[-1]:+.2f}</code>")


def _active_signals(levels: dict, last_bar: pd.Timestamp) -> list:
    out = []
    for lname, lv in levels.items():
        zrow = lv["z"].loc[:last_bar].iloc[-1].dropna()
        for g, v in zrow[zrow.abs() >= ACTIVE_Z].sort_values(key=abs, ascending=False).items():
            out.append((lname, g, float(v)))
    return out


def _regime_block(levels: dict, last_bar: pd.Timestamp) -> str:
    macro = levels["MACRO"]
    tot = macro["dv"].sum(axis=1).rolling(DEFAULT_SMOOTH).mean().loc[:last_bar].dropna()
    dv_now = tot.iloc[-1]
    pctl = float((tot.iloc[-252:] <= dv_now).mean() * 100) if len(tot) >= 252 else np.nan
    hhi = (macro["shares"] ** 2).sum(axis=1)
    hhi_z = ((hhi - hhi.rolling(252, min_periods=252).mean())
             / hhi.rolling(252, min_periods=252).std()).loc[:last_bar].dropna()
    srow = macro["shares"].loc[:last_bar].iloc[-1].sort_values(ascending=False)
    top = " · ".join(f"{esc(g)} <code>{v * 100:.1f}%</code>" for g, v in srow.head(3).items())
    lines = [f"DV totale (media {DEFAULT_SMOOTH}g): <code>${dv_now / 1e9:,.0f}B</code>"
             + (f" — {pctl:.0f}° pctl su 1 anno" if not np.isnan(pctl) else "")]
    if len(hhi_z):
        lines.append(f"Concentrazione macro (HHI, z): <code>{hhi_z.iloc[-1]:+.1f}</code>")
    lines.append(f"Quote principali: {top}")
    return "\n".join(lines)


def _footer(log_count: int) -> str:
    return (f"📒 Registro eventi live: <code>{log_count}</code> totali\n"
            f"⚠️ <i>Tilt informativi, non segnali operativi "
            f"(ciclo 1: direzione confermata, q=0.29 — vedi HYPOTHESES.md)</i>")


def render_alert(new_events: list, levels: dict, last_bar: pd.Timestamp,
                 log_count: int, fetch_warnings: list) -> str:
    lines = [f"🌊 <b>LIQUIDITY FLOW MAP</b> — dati al {last_bar:%d/%m/%Y}",
             "🚨 <b>Nuovi eventi di attenzione</b>", ""]
    for e in merge_for_message(new_events):
        icona = "🔴" if e["direction"] == "su" else "🔵"
        soglia = f"+{e['threshold']}" if e["direction"] == "su" else f"−{e['threshold']}"
        lines.append(f"{icona} <b>[{e['level']}] {esc(e['group'])}</b> — z incrocia "
                     f"{soglia} (z <code>{e['z']:+.2f}</code>, "
                     f"quota <code>{e['share_pct']:.2f}%</code>)")
        lines.append(f"<i>{esc(tilt(e['level'], e['group'], e['direction']))}</i>")
        lines.append("")
    att = _active_signals(levels, last_bar)
    lines.append(f"📌 <b>Segnali attivi (|z| ≥ {ACTIVE_Z})</b>")
    if att:
        for lname, g, v in att:
            lines.append(f"{'🔴' if v > 0 else '🔵'} [{lname}] {esc(g)} <code>{v:+.1f}</code>")
    else:
        lines.append("nessuno")
    lines.append("")
    lines.append("🔄 <b>Rotazione 21g (Δ quota, pp)</b>")
    for lname, lv in levels.items():
        lines.append(f"{lname}: {_rotation_line(lv, last_bar, full=False)}")
    lines.append("")
    lines.append("🌡️ <b>Regime</b>")
    lines.append(_regime_block(levels, last_bar))
    if fetch_warnings:
        lines.append(f"\n⚠️ ticker non scaricati: {esc(', '.join(fetch_warnings))}")
    lines.append("")
    lines.append(_footer(log_count))
    return "\n".join(lines)


def render_digest(levels: dict, last_bar: pd.Timestamp, week_events: pd.DataFrame,
                  log_count: int, fetch_warnings: list) -> str:
    lines = [f"🌊 <b>LIQUIDITY FLOW MAP</b> — digest settimanale",
             f"dati al {last_bar:%d/%m/%Y}", ""]
    lines.append("🏆 <b>Attenzione (z-score vs propria norma 252g)</b>")
    for lname, lv in levels.items():
        lines.append(f"<b>{lname}</b>: {_z_leaderboard(lv, last_bar)}")
    lines.append("")
    lines.append("🔄 <b>Rotazione 21g (Δ quota, pp)</b>")
    for lname, lv in levels.items():
        lines.append(f"<b>{lname}</b>: {_rotation_line(lv, last_bar, full=True)}")
    lines.append("")
    att = _active_signals(levels, last_bar)
    lines.append(f"📌 <b>Segnali attivi (|z| ≥ {ACTIVE_Z}) e tilt</b>")
    if att:
        for lname, g, v in att:
            d = "su" if v > 0 else "giu"
            lines.append(f"{'🔴' if v > 0 else '🔵'} [{lname}] {esc(g)} "
                         f"<code>{v:+.1f}</code> — <i>{esc(tilt(lname, g, d))}</i>")
    else:
        lines.append("nessuno — rotazione ordinaria")
    lines.append("")
    lines.append("🗓️ <b>Eventi degli ultimi 7 giorni</b>")
    if len(week_events):
        best = {}
        for _, e in week_events.iterrows():
            k = (e["date"], e["level"], e["group"], e["direction"])
            if k not in best or float(e["threshold"]) > float(best[k]["threshold"]):
                best[k] = e
        for e in sorted(best.values(), key=lambda r: str(r["date"])):
            icona = "🔴" if e["direction"] == "su" else "🔵"
            lines.append(f"{icona} {e['date']} [{e['level']}] {esc(e['group'])} "
                         f"z <code>{float(e['z']):+.2f}</code> (soglia {e['threshold']})")
    else:
        lines.append("nessuno")
    lines.append("")
    lines.append("🌡️ <b>Regime</b>")
    lines.append(_regime_block(levels, last_bar))
    if fetch_warnings:
        lines.append(f"\n⚠️ ticker non scaricati: {esc(', '.join(fetch_warnings))}")
    lines.append("")
    lines.append(_footer(log_count))
    return "\n".join(lines)


# ===================================================
# TELEGRAM
# ===================================================

def clip_html(text: str) -> str:
    """
    Tronca al limite Telegram senza spezzare i tag HTML: taglia all'ultimo
    newline utile (nel nostro rendering ogni riga apre e chiude i propri tag,
    quindi il taglio a fine riga è sempre HTML-valido). Un taglio a offset
    fisso lascerebbe tag aperti e l'API risponderebbe 400 'can't parse
    entities', facendo fallire l'intero job.
    """
    if len(text) <= TELEGRAM_MAX:
        return text
    cut = text.rfind("\n", 0, TELEGRAM_MAX - 20)
    if cut <= 0:
        cut = TELEGRAM_MAX - 20
    return text[:cut] + "\n…(troncato)"


def send_telegram(text: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    text = clip_html(text)
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": True},
        timeout=30,
    )
    resp.raise_for_status()
    if not resp.json().get("ok", False):
        raise RuntimeError(f"telegram: {resp.text[:200]}")


# ===================================================
# STATO (idempotenza nei weekend/festivi)
# ===================================================

def load_state() -> dict:
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1)


# ===================================================
# MAIN
# ===================================================

def run(force_digest: bool = False) -> None:
    api_key = os.environ["EODHD_API_KEY"]
    tickers = sorted({t for m in MACRO_GROUPS.values() for t in m}
                     | {t for m in SECTOR_GROUPS.values() for t in m})
    data, errors = fetch_universe_plain(tickers, START_DATE, api_key)

    for groups, label in [(MACRO_GROUPS, "macro"), (SECTOR_GROUPS, "settori")]:
        dead = [g for g, mm in groups.items() if not any(t in data for t in mm)]
        if dead:
            raise RuntimeError(f"gruppi {label} senza dati: {dead}")

    levels = {"MACRO": compute_level(data, MACRO_GROUPS),
              "SETTORI": compute_level(data, SECTOR_GROUPS)}
    last_bar = min(lv["shares"].dropna(how="all").index[-1] for lv in levels.values())

    state = load_state()
    last_iso = last_bar.date().isoformat()
    new_bar = state.get("last_bar") != last_iso
    # Il digest è "dovuto" il sabato finché non è stato inviato per questa
    # barra: così un venerdì festivo di borsa (barra ferma a giovedì) non fa
    # saltare il digest in silenzio con l'early-return sullo stato.
    digest_day = force_digest or datetime.now(timezone.utc).weekday() == 5
    digest_due = digest_day and (force_digest
                                 or state.get("last_digest_bar") != last_iso)

    if not new_bar and not digest_due:
        print(f"nessuna barra nuova (ultima: {last_bar.date()}) "
              f"e nessun digest dovuto — silenzio")
        return

    new_events = []
    if new_bar:
        for lname, lv in levels.items():
            new_events += detect_new_events(lname, lv, last_bar)
    added = append_log(new_events)
    log = load_log()
    week_mask = pd.to_datetime(log["date"]) >= last_bar - pd.Timedelta(days=7) \
        if len(log) else pd.Series(dtype=bool)
    week_events = log[week_mask] if len(log) else log

    msg = None
    if digest_due:
        msg = render_digest(levels, last_bar, week_events, len(log), list(errors))
    elif new_events:
        msg = render_alert(new_events, levels, last_bar, len(log), list(errors))

    if msg:
        send_telegram(msg)
        print(f"messaggio inviato ({'digest' if digest_due else 'alert'}, "
              f"{len(msg)} caratteri)")
    else:
        print("nessun evento nuovo e nessun digest dovuto — silenzio")

    state["last_bar"] = last_iso
    if digest_due:
        state["last_digest_bar"] = last_iso
    save_state(state)
    print(f"barra {last_bar.date()} | eventi nuovi: {added} | log totale: {len(log)}")


def selftest() -> None:
    """Rendering e log su dati finti: niente rete, niente secrets."""
    idx = pd.bdate_range("2026-06-01", periods=40)
    rng = np.random.default_rng(3)

    def fake_level(names):
        z = pd.DataFrame(rng.uniform(-1.2, 1.2, (len(idx), len(names))),
                         index=idx, columns=names)
        z.iloc[-1, 0] = 2.1
        z.iloc[-1, 1] = -1.7
        sh = pd.DataFrame(rng.uniform(0.5, 2.0, (len(idx), len(names))),
                          index=idx, columns=names)
        sh = sh.div(sh.sum(axis=1), axis=0)
        rot = pd.DataFrame(rng.normal(0, 0.5, (len(idx), len(names))),
                           index=idx, columns=names)
        dv = sh * 6e11
        return {"dv": dv, "shares": sh, "z": z, "rot": rot}

    levels = {"MACRO": fake_level(list(MACRO_GROUPS)),
              "SETTORI": fake_level(list(SECTOR_GROUPS))}
    last_bar = idx[-1]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    events = [
        {"date": last_bar.date().isoformat(), "level": "SETTORI", "group": "Energia",
         "threshold": 1.5, "direction": "su", "z": 2.14, "share_pct": 16.7,
         "logged_at_utc": now},
        {"date": last_bar.date().isoformat(), "level": "SETTORI", "group": "Energia",
         "threshold": 2.0, "direction": "su", "z": 2.14, "share_pct": 16.7,
         "logged_at_utc": now},
        {"date": last_bar.date().isoformat(), "level": "MACRO", "group": "Oro/Metalli",
         "threshold": 1.5, "direction": "su", "z": 1.62, "share_pct": 5.3,
         "logged_at_utc": now},
    ]

    import tempfile
    tmp = os.path.join(tempfile.gettempdir(), "lfm_test_log.csv")
    if os.path.exists(tmp):
        os.remove(tmp)
    a1 = append_log(events, tmp)
    a2 = append_log(events, tmp)
    assert a1 == 3 and a2 == 0, f"dedup log rotto: {a1}, {a2}"

    log = load_log(tmp)
    alert = render_alert(events, levels, last_bar, len(log), ["FXY.US (test)"])
    digest = render_digest(levels, last_bar, log, len(log), [])
    for name, m in [("ALERT", alert), ("DIGEST", digest)]:
        assert len(m) < TELEGRAM_MAX, f"{name} troppo lungo: {len(m)}"
        print(f"\n{'=' * 24} {name} ({len(m)} caratteri) {'=' * 24}\n")
        print(m)

    long_text = "\n".join(f"<b>riga {i}</b> — <i>tilt di prova</i> "
                          f"<code>{i:+.1f}</code>" for i in range(200))
    clipped = clip_html(long_text)
    assert len(clipped) <= TELEGRAM_MAX, "clip_html oltre il limite"
    assert clipped.endswith("…(troncato)"), "clip_html senza suffisso"
    body = clipped.rsplit("\n", 1)[0]
    for tag in ("b", "i", "code"):
        assert body.count(f"<{tag}>") == body.count(f"</{tag}>"), \
            f"clip_html spezza i tag <{tag}>"
    print("\n[selftest OK] dedup log, lunghezze, rendering e clip_html verificati")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        try:
            run(force_digest="--force-digest" in sys.argv)
        except Exception as exc:  # noqa: BLE001 — avvisa su Telegram, poi fallisci
            try:
                send_telegram(f"⚠️ <b>Liquidity Flow Map</b>: job notturno fallito\n"
                              f"<code>{esc(type(exc).__name__)}: {esc(str(exc)[:300])}</code>")
            except Exception:  # noqa: BLE001
                pass
            raise
