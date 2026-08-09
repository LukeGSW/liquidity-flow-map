"""
pages/1_Event_study_fase_2.py — Esecuzione del protocollo pre-registrato.

Ipotesi e regole: research/HYPOTHESES.md (copia operativa in src/hypotheses.py).
Questa pagina NON permette di cambiare soglie/orizzonti: è il punto del
protocollo. Due modalità: calibrazione IS (libera) e passaggio OOS (unico).
"""

import numpy as np
import pandas as pd
import streamlit as st

from src.config import (
    START_DATE, MACRO_GROUPS, SECTOR_GROUPS, DEFAULT_SMOOTH, Z_WINDOW,
    DV_MODE, IS_END_DATE,
)
from src.data_fetcher import fetch_universe
from src.calculations import group_dollar_volume, dv_shares, attention_z
from src.event_study import (
    cross_dates, log_forward, realized_vol, pooled_event_study, bh_fdr,
)
from src.hypotheses import (
    FROZEN_DATE, DEBOUNCE, ALPHA, FDR_Q, B_BOOT, SEED, HYPOTHESES,
)

# ===================================================
# CONFIGURAZIONE PAGINA
# ===================================================
st.set_page_config(
    page_title="Event study fase 2 | Kriterion Quant",
    page_icon="🧪",
    layout="wide",
)

st.title("🧪 Event study — fase 2 (protocollo pre-registrato)")
st.markdown(
    f"""
Le **7 ipotesi congelate il {FROZEN_DATE}** (documento: `research/HYPOTHESES.md`)
vengono testate qui sui **prezzi**, con lo stesso disegno statistico della
scansione esplorativa: null appaiato per terzile di volatilità, test one-sided
nella direzione pre-dichiarata, bootstrap B={B_BOOT} con seed fisso, BH-FDR
sulla famiglia. Soglie e orizzonti **non sono modificabili da questa pagina**:
è il punto del protocollo.

> **Come si usa:** resta in *Calibrazione IS* finché le regole non sono ferme.
> Il *Passaggio OOS* è previsto **una sola volta**: ripeterlo dopo aver
> modificato le regole invalida il protocollo.
"""
)

# Tabella delle ipotesi congelate
hyp_df = pd.DataFrame([{
    "ID": h["id"],
    "Ipotesi": h["descrizione"],
    "Orizzonte": (f"{h['start_lag']}→{h['h']}g" if h["start_lag"] else f"{h['h']}g"),
    "Direzione attesa": "−" if h["attesa"] < 0 else "+",
    "Peso": "primaria" if h["primaria"] else "secondaria",
} for h in HYPOTHESES])
st.dataframe(hyp_df, use_container_width=True, hide_index=True)
st.divider()

# ===================================================
# API KEY
# ===================================================
try:
    EODHD_API_KEY = st.secrets["EODHD_API_KEY"]
except (KeyError, FileNotFoundError):
    st.error("❌ EODHD_API_KEY non configurata (vedi README).")
    st.stop()

# ===================================================
# SCELTA MODALITÀ
# ===================================================
IS_END = pd.Timestamp(IS_END_DATE)

mode = st.radio(
    "Modalità",
    ["📐 Calibrazione in-sample (fino al " + f"{IS_END:%d/%m/%Y})",
     "🔒 Passaggio out-of-sample (unico, dal " + f"{IS_END:%d/%m/%Y})"],
)
is_oos = mode.startswith("🔒")

if is_oos:
    st.warning(
        "**Questo è IL passaggio out-of-sample previsto dal protocollo.** "
        "Il risultato va accettato così com'è: ripetere l'OOS dopo aver "
        "ritoccato regole o soglie trasforma l'out-of-sample in in-sample."
    )
    confirmed = st.checkbox(
        "Confermo: le regole sono ferme, questo passaggio OOS fa fede."
    )
    if not confirmed:
        st.stop()

# ===================================================
# FETCH DATI (settori + macro; GLD è nell'universo macro)
# ===================================================
sector_tickers = sorted({t for m in SECTOR_GROUPS.values() for t in m})
macro_tickers = sorted({t for m in MACRO_GROUPS.values() for t in m})
tickers = sorted(set(sector_tickers) | set(macro_tickers))

with st.spinner("⏳ Caricamento dati EODHD…"):
    data, errors = fetch_universe(tickers, START_DATE, EODHD_API_KEY)

if errors:
    st.warning("⚠️ Ticker non scaricati: " + ", ".join(f"`{t}`" for t in errors))
essential = set(sector_tickers) | {"GLD.US", "SLV.US"}
missing_essential = [t for t in essential if t not in data]
if missing_essential:
    st.error(f"❌ Mancano ticker essenziali per il protocollo: {missing_essential}")
    st.stop()

# ===================================================
# PIPELINE CONGELATA (smoothing 21g, z 252g — indipendente dagli slider
# della dashboard principale)
# ===================================================
z_sector = attention_z(
    dv_shares(group_dollar_volume(data, SECTOR_GROUPS, DV_MODE), DEFAULT_SMOOTH),
    Z_WINDOW,
)
z_macro = attention_z(
    dv_shares(group_dollar_volume(data, MACRO_GROUPS, DV_MODE), DEFAULT_SMOOTH),
    Z_WINDOW,
)

# Prezzi (adjusted = total return) e volatilità per la stratificazione
sector_px = {name: data[members[0]]["adjusted_close"]
             for name, members in SECTOR_GROUPS.items() if members[0] in data}
gld_px = data["GLD.US"]["adjusted_close"]

basket_daily = pd.DataFrame(
    {name: np.log(px.astype(float)).diff() for name, px in sector_px.items()}
).mean(axis=1)
vol_basket = realized_vol(basket_daily)
vol_gld = realized_vol(np.log(gld_px.astype(float)).diff())

# ===================================================
# COSTRUZIONE ESITI PER OGNI (h, start_lag) RICHIESTO
# ===================================================
needed = sorted({(h["h"], h["start_lag"]) for h in HYPOTHESES})
abs_fwd, rel_fwd, gld_fwd = {}, {}, {}
for (h, lag) in needed:
    fdf = pd.DataFrame({name: log_forward(px, h, lag)
                        for name, px in sector_px.items()})
    basket = fdf.mean(axis=1)
    abs_fwd[(h, lag)] = {name: fdf[name] for name in fdf.columns}
    rel_fwd[(h, lag)] = {name: fdf[name] - basket for name in fdf.columns}
    gld_fwd[(h, lag)] = {"GLD": log_forward(gld_px, h, lag)}

# Finestra temporale della modalità corrente
if is_oos:
    win = slice(IS_END + pd.Timedelta(days=1), None)
    win_label = f"OUT-OF-SAMPLE ({IS_END + pd.Timedelta(days=1):%d/%m/%Y} → oggi)"
else:
    win = slice(None, IS_END)
    win_label = f"IN-SAMPLE (inizio storia → {IS_END:%d/%m/%Y})"


def in_window(dates):
    lo = win.start or pd.Timestamp.min
    hi = win.stop or pd.Timestamp.max
    return [d for d in dates if lo <= d <= hi]


# ===================================================
# ESECUZIONE DELLE 7 IPOTESI
# ===================================================
rows, event_log = [], {}
with st.spinner("🧮 Bootstrap in corso…"):
    for hyp in HYPOTHESES:
        key = (hyp["h"], hyp["start_lag"])
        if hyp["famiglia"] == "settori":
            events = [(name, d) for name in z_sector.columns
                      for d in in_window(cross_dates(z_sector[name], hyp["soglia"],
                                                     hyp["dir"], DEBOUNCE))]
            outcomes = rel_fwd[key] if hyp["esito"] == "relativo" else abs_fwd[key]
            vol = vol_basket
        else:
            events = [("GLD", d)
                      for d in in_window(cross_dates(z_macro["Oro/Metalli"],
                                                     hyp["soglia"], hyp["dir"],
                                                     DEBOUNCE))]
            outcomes = gld_fwd[key]
            vol = vol_gld

        outcomes_w = {k: s.loc[win] for k, s in outcomes.items()}
        vol_w = vol.loc[win]
        res = pooled_event_study(events, outcomes_w, vol_w, hyp["attesa"],
                                 B=B_BOOT, seed=SEED)
        event_log[hyp["id"]] = events
        rows.append({**{"ID": hyp["id"], "Ipotesi": hyp["descrizione"],
                        "attesa": hyp["attesa"],
                        "Peso": "primaria" if hyp["primaria"] else "secondaria"},
                     **res})

res_df = pd.DataFrame(rows)

# BH-FDR solo sui test eseguibili
valid = res_df["p"].notna()
res_df.loc[valid, "q"] = bh_fdr(res_df.loc[valid, "p"].tolist())


def verdetto(r) -> str:
    """Verdetto leggibile secondo i criteri pre-registrati."""
    if pd.isna(r["p"]):
        return f"⚪ non eseguibile (n={int(r['n'])} < 5)"
    giusta = np.sign(r["excess"]) == np.sign(r["attesa"])
    if giusta and r["q"] <= FDR_Q:
        return "✅ CONFERMATA (direzione giusta, q ≤ 0.10)"
    if giusta and r["p"] <= ALPHA:
        return "🟡 direzione giusta, p ≤ 0.05 ma q > 0.10"
    if giusta:
        return "➖ direzione giusta, non significativa"
    return "❌ direzione opposta all'attesa"


res_df["Verdetto"] = res_df.apply(verdetto, axis=1)

# ===================================================
# PRESENTAZIONE RISULTATI
# ===================================================
st.subheader(f"Risultati — {win_label}")
st.markdown(
    """
**Come leggere la tabella:** *effetto* = rendimento medio dopo gli eventi;
*null* = cosa produce il caso nello stesso regime di volatilità; *eccesso* =
la differenza, cioè il pattern. Il *p* è one-sided nella direzione attesa;
il *q* corregge per il fatto che i test sono 7 (i falsi positivi si contano).
"""
)

show = res_df.copy()
show["n eventi"] = show["n"].astype(int)
show["effetto %"] = show["effect"].map(lambda v: f"{v:+.2f}" if pd.notna(v) else "—")
show["null %"] = show["null"].map(lambda v: f"{v:+.2f}" if pd.notna(v) else "—")
show["eccesso %"] = show["excess"].map(lambda v: f"{v:+.2f}" if pd.notna(v) else "—")
show["p (one-sided)"] = show["p"].map(lambda v: f"{v:.4f}" if pd.notna(v) else "—")
show["q (BH)"] = show["q"].map(lambda v: f"{v:.3f}" if pd.notna(v) else "—")
st.dataframe(
    show[["ID", "Ipotesi", "Peso", "n eventi", "effetto %", "null %",
          "eccesso %", "p (one-sided)", "q (BH)", "Verdetto"]],
    use_container_width=True, hide_index=True,
)

n_conf = int((res_df["Verdetto"].str.startswith("✅")).sum())
n_prim = int((res_df["Verdetto"].str.startswith("✅")
              & (res_df["Peso"] == "primaria")).sum())
st.markdown(f"**Sintesi:** {n_conf}/7 ipotesi confermate, di cui {n_prim} primarie.")
if is_oos:
    st.info(
        "📋 **Registra questo risultato in research/HYPOTHESES.md** (data, esito, "
        "numeri) — è il verdetto del ciclo. Le ipotesi confermate diventano "
        "candidate operative; quelle bocciate si archiviano, non si ritoccano."
    )

with st.expander("📅 Date degli eventi per ipotesi"):
    for hid, events in event_log.items():
        if events:
            elenco = ", ".join(f"{d:%d/%m/%Y} ({k.split('.')[0]})"
                               for k, d in sorted(events, key=lambda e: e[1]))
        else:
            elenco = "nessun evento nella finestra"
        st.markdown(f"**{hid}** — {len(events)} eventi: {elenco}")

with st.expander("ℹ️ Metodologia (riassunto del protocollo)"):
    st.markdown(
        f"""
- Pipeline congelata: quote smoothing {DEFAULT_SMOOTH}g, z rolling {Z_WINDOW}g,
  debounce {DEBOUNCE}g, `DV_MODE={DV_MODE}` — indipendente dagli slider della
  dashboard principale.
- Esiti: log-rendimenti forward su adjusted_close (total return). Paniere EW =
  media aritmetica dei log-forward dei 9 XL*.
- Null appaiato: controlli dalla stessa serie e stesso terzile di volatilità
  realizzata 21g (paniere per i settori, GLD per l'oro), esclusi ±10g dagli
  eventi; bootstrap B={B_BOOT}, seed={SEED} (riproducibile).
- Conferma pre-registrata: direzione giusta E q ≤ {FDR_Q} (α singolo {ALPHA}).
- Documento completo: `research/HYPOTHESES.md` (congelato il {FROZEN_DATE}).
"""
    )

st.download_button(
    "⬇️ Scarica risultati (CSV)",
    res_df.drop(columns=["attesa"]).to_csv(index=False).encode("utf-8"),
    file_name=f"event_study_{'oos' if is_oos else 'is'}.csv",
    mime="text/csv",
)
