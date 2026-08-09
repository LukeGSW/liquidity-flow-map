"""
app.py — Liquidity Flow Map: dove si muove l'attività in dollari tra le macro-classi USA.

Organizzazione:
    - Configurazione pagina e API key
    - Sidebar con parametri (universo, smoothing, finestre, modalità ricerca)
    - Pipeline: DV -> quote -> z-score -> pressione -> rotazione
    - Sezioni: KPI, fiume, heatmap, rotazione, pista, diagnostica, metodologia
"""

import pandas as pd
import streamlit as st

from src.config import (
    START_DATE, MACRO_GROUPS, SECTOR_GROUPS, GROUP_COLORS, SECTOR_COLORS,
    SMOOTH_WINDOWS, DEFAULT_SMOOTH, ROTATION_WINDOWS, DEFAULT_ROTATION,
    Z_WINDOW, DV_MODE, PRESSURE_MODE, PRESSURE_DEMEAN, HEATMAP_FREQS,
    IS_FRACTION, IS_END_DATE,
)
from src.data_fetcher import fetch_universe
from src.calculations import (
    group_dollar_volume, dv_shares, attention_z, signed_pressure,
    rotation, resample_mean, is_oos_cutoff, data_quality,
)
from src.charts import (
    build_river, build_heatmap, build_rotation_bars, build_liquidity_track,
)

# ===================================================
# CONFIGURAZIONE PAGINA
# ===================================================
st.set_page_config(
    page_title="Liquidity Flow Map | Kriterion Quant",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ===================================================
# API KEY (da st.secrets — configurata su Streamlit Cloud)
# ===================================================
try:
    EODHD_API_KEY = st.secrets["EODHD_API_KEY"]
except (KeyError, FileNotFoundError):
    st.error(
        "❌ **EODHD_API_KEY non configurata.**\n\n"
        "- In locale: crea `.streamlit/secrets.toml` con `EODHD_API_KEY = \"...\"` "
        "(vedi `.streamlit/secrets.toml.example`)\n"
        "- Su Streamlit Cloud: Settings → Secrets"
    )
    st.stop()

# ===================================================
# SIDEBAR — PARAMETRI UTENTE
# ===================================================
CURRENT_YEAR = pd.Timestamp.today().year

with st.sidebar:
    st.title("⚙️ Parametri")
    st.divider()

    level = st.radio(
        "Universo",
        ["Macro-classi", "Settori azionari (XL*)"],
        help=(
            "Macro-classi: 8 gruppi (equity, treasury, credito, commodity, oro, "
            "cash, valute, estero). Settori: drill-down dentro l'equity con i 9 "
            "SPDR storici — le quote sono calcolate SOLO dentro l'universo settoriale."
        ),
    )

    smooth = st.select_slider(
        "Smoothing quote (giorni)", options=SMOOTH_WINDOWS, value=DEFAULT_SMOOTH,
        help="Media mobile sul dollar volume prima del calcolo delle quote.",
    )
    rot_win = st.select_slider(
        "Finestra rotazione (giorni)", options=ROTATION_WINDOWS, value=DEFAULT_ROTATION,
        help="Orizzonte della variazione di quota nel pannello rotazione.",
    )
    heat_freq_label = st.radio("Risoluzione heatmap", list(HEATMAP_FREQS), index=1)
    heat_metric = st.radio(
        "Metrica heatmap", ["Attenzione (z-score)", "Pressione firmata"],
        help=(
            "Z-score: quota vs la propria norma rolling (quanto). "
            "Pressione: direzione netta del volume in [-1, +1] (in che verso)."
        ),
    )

    st.divider()
    research_mode = st.toggle(
        "🔒 Modalità ricerca (solo IS)",
        value=False,
        help=(
            f"Nasconde il {int((1 - IS_FRACTION) * 100)}% più recente della storia "
            "(out-of-sample). Da tenere attiva durante l'esplorazione dei pattern: "
            "ciò che l'occhio vede sull'OOS non è più out-of-sample."
        ),
    )
    show_from = st.slider("Mostra dall'anno", 2008, CURRENT_YEAR, 2008)

    st.divider()
    st.caption("📡 Dati: EODHD — universo fisso dal 2008")
    data_date_caption = st.empty()

groups = MACRO_GROUPS if level == "Macro-classi" else SECTOR_GROUPS
colors = GROUP_COLORS if level == "Macro-classi" else SECTOR_COLORS

# ===================================================
# HEADER
# ===================================================
st.title("🌊 Liquidity Flow Map")
st.markdown(
    """
Questa dashboard traccia **dove si concentra l'attività in dollari** (dollar volume =
prezzo × volume) tra le macro-classi USA, usando gli ETF più liquidi come proxy.

Il postulato "la liquidità non si crea, si trasferisce" è falso sui dollar volume
assoluti (l'attività aggregata si espande e si contrae con la volatilità), ma è **vero
per costruzione sulle quote**: la quota di un gruppo può salire solo se quella di altri
scende. Il "flusso" che vedi qui è la variazione di quota, su due canali:
**attenzione** (quanta attività, z-score della quota) e **pressione** (in che verso,
volume firmato).

> **Come si usa:** scegli universo e finestre nella sidebar. Il fiume dà il quadro di
> regime, la heatmap evidenzia le anomalie gruppo per gruppo, rotazione e pista dicono
> chi sta attraendo attività adesso.
"""
)
st.divider()

# ===================================================
# FETCH DATI
# ===================================================
tickers = sorted({t for members in groups.values() for t in members})

with st.spinner("⏳ Caricamento dati EODHD…"):
    data, errors = fetch_universe(tickers, START_DATE, EODHD_API_KEY)

if errors:
    st.warning(
        "⚠️ Ticker non scaricati (l'app prosegue senza): "
        + ", ".join(f"`{t}`" for t in errors)
    )

missing_groups = [g for g, members in groups.items()
                  if not any(t in data for t in members)]
if missing_groups:
    st.error(f"❌ Nessun dato per i gruppi: {', '.join(missing_groups)}. "
             "Verifica la chiave API e i ticker in src/config.py.")
    st.stop()

# ===================================================
# PIPELINE
# ===================================================
group_dv = group_dollar_volume(data, groups, DV_MODE)
shares = dv_shares(group_dv, smooth).dropna(how="all")
z = attention_z(shares, Z_WINDOW)
pressure = signed_pressure(data, groups, smooth, DV_MODE, PRESSURE_MODE,
                           PRESSURE_DEMEAN)
rot = rotation(shares, rot_win)

if shares.empty:
    st.error("❌ Pipeline vuota: dati insufficienti dopo il warm-up.")
    st.stop()

data_date_caption.caption(f"Ultimo dato: {shares.index.max():%d/%m/%Y}")

# ===================================================
# FILTRO VISTA (modalità ricerca + anno di partenza)
# ===================================================
# Cutoff calcolato su group_dv.index (indipendente dallo smoothing scelto in
# sidebar: shares.index perde il warm-up e sposterebbe il confine di ~17 giorni
# tra smooth=5 e smooth=63). Con IS_END_DATE congelato in config, il confine
# diventa una data assoluta e smette anche di avanzare col passare dei giorni.
if IS_END_DATE:
    cutoff = pd.Timestamp(IS_END_DATE)
else:
    cutoff = is_oos_cutoff(group_dv.index, IS_FRACTION)

if research_mode:
    view_end = cutoff
    st.info(
        f"🔒 **Modalità ricerca attiva**: visualizzazione limitata all'in-sample, "
        f"fino al **{cutoff:%d/%m/%Y}** ({int(IS_FRACTION * 100)}% della storia). "
        f"L'out-of-sample resta sigillato per la validazione futura dei pattern."
    )
else:
    view_end = shares.index.max()

view_start = pd.Timestamp(f"{show_from}-01-01")


def view(df: pd.DataFrame) -> pd.DataFrame:
    """Applica il filtro temporale di visualizzazione corrente."""
    return df.loc[(df.index >= view_start) & (df.index <= view_end)]


shares_v = view(shares)
z_v = view(z)
pressure_v = view(pressure)
rot_v = view(rot).dropna(how="all")

if shares_v.empty or rot_v.empty:
    st.warning("⚠️ Nessun dato nell'intervallo selezionato: allarga il periodo "
               "o disattiva la modalità ricerca.")
    st.stop()

# ===================================================
# SEZIONE 0: KPI
# ===================================================
total_dv_sm = group_dv.sum(axis=1).rolling(smooth, min_periods=smooth).mean()
total_dv_last = total_dv_sm.loc[:view_end].iloc[-1]

z_last = z_v.iloc[-1].dropna()
rot_last = rot_v.iloc[-1].dropna()

c1, c2, c3, c4 = st.columns(4)
c1.metric(f"Dollar volume totale (media {smooth}g)", f"${total_dv_last / 1e9:,.1f} B")
if not z_last.empty:
    g_hot = z_last.abs().idxmax()
    c2.metric("Attenzione più anomala", g_hot, f"z {z_last[g_hot]:+.1f}",
              delta_color="off")
if not rot_last.empty:
    c3.metric(f"Attrae di più ({rot_win}g)", rot_last.idxmax(),
              f"{rot_last.max():+.2f} pp")
    c4.metric(f"Cede di più ({rot_win}g)", rot_last.idxmin(),
              f"{rot_last.min():+.2f} pp", delta_color="inverse")

st.divider()

# ===================================================
# SEZIONE 1: IL FIUME
# ===================================================
st.subheader("🌊 Il fiume — quote di dollar volume")
st.markdown(
    f"""
Ogni banda è la **quota** di un gruppo sull'attività totale dell'universo (media
{smooth} giorni). Le quote sommano al 100% per costruzione: quando una banda si
allarga, altre si stringono. È la vista di **regime** — i grandi episodi (2008 credito,
2020 tutto, 2022 commodity e duration) si leggono qui.
"""
)
st.plotly_chart(
    build_river(shares_v, colors, f"Quote di dollar volume — smoothing {smooth}g | dal {view_start:%Y}"),
    use_container_width=True,
)

# ===================================================
# SEZIONE 2: HEATMAP
# ===================================================
st.subheader("🔥 Attenzione relativa e pressione")
st.markdown(
    f"""
Il fiume è dominato dai gruppi grandi. Qui ogni gruppo è confrontato **con la propria
storia**: lo z-score della quota su finestra rolling di {Z_WINDOW} giorni (rosso =
attività sopra la propria norma, blu = sotto). La **pressione firmata** aggiunge la
direzione: volume pesato per il segno del rendimento *in eccesso* (total-return meno
la propria media rolling {PRESSURE_DEMEAN}g), in [-1, +1] — distingue l'accumulo
dalla distribuzione. Nota onesta: per il gruppo Cash la pressione è strutturalmente
vicina al rumore (il prezzo si muove quasi solo per accrual) — va letta come
"assente", non come segnale. È il pannello dove cercare le anomalie.
"""
)
freq = HEATMAP_FREQS[heat_freq_label]
if heat_metric == "Attenzione (z-score)":
    panel = resample_mean(z_v, freq).dropna(how="all")
    fig_heat = build_heatmap(
        panel, f"Z-score di attenzione ({heat_freq_label.lower()}) | finestra {Z_WINDOW}g",
        "z", zmin=-3.0, zmax=3.0, colorscale="RdBu_r",
    )
else:
    panel = resample_mean(pressure_v, freq).dropna(how="all")
    fig_heat = build_heatmap(
        panel, f"Pressione firmata ({heat_freq_label.lower()}) | rolling {smooth}g",
        "pressione", zmin=-0.5, zmax=0.5, colorscale="RdYlGn",
    )
st.plotly_chart(fig_heat, use_container_width=True)

# ===================================================
# SEZIONE 3: ROTAZIONE
# ===================================================
st.subheader("🔄 Rotazione in corso")
st.markdown(
    f"""
Chi ha **guadagnato quota** e chi l'ha **ceduta** negli ultimi {rot_win} giorni
(al {rot_v.index[-1]:%d/%m/%Y}). Niente Sankey "da chi a chi": dai dati si conoscono
solo i saldi netti per gruppo, non gli accoppiamenti — le barre dicono tutto ciò che
i dati sanno davvero.
"""
)
st.plotly_chart(
    build_rotation_bars(rot_last, f"Δ quota a {rot_win} giorni"),
    use_container_width=True,
)

# ===================================================
# SEZIONE 4: LA PISTA DELLA LIQUIDITÀ
# ===================================================
st.subheader("🏁 La pista della liquidità")
st.markdown(
    """
Livello vs momentum dell'attenzione, su dati settimanali: **x** = z-score della quota,
**y** = variazione dello z nelle ultime 4 settimane, con scia di 13 settimane.
Alto-destra = caldo e in accelerazione; basso-destra = caldo ma in raffreddamento;
alto-sinistra = freddo ma in riscaldamento (spesso il quadrante più interessante).
"""
)
z_weekly = resample_mean(z_v, "W-FRI").dropna(how="all")
if len(z_weekly) >= 6:
    st.plotly_chart(
        build_liquidity_track(z_weekly, momentum_window=4, trail=13,
                              colors=colors, title="Attenzione: livello vs momentum (settimanale)"),
        use_container_width=True,
    )
else:
    st.caption("Dati insufficienti per la pista nell'intervallo selezionato.")

st.divider()

# ===================================================
# DIAGNOSTICA E DOWNLOAD
# ===================================================
with st.expander("🧪 Diagnostica dati"):
    st.markdown(
        """
Copertura per ticker, **buchi dati** (giorni mancanti / volume zero: diventano DV=0 e
distorcono la quota del gruppo per la durata dello smoothing — sul livello settoriale,
1 ticker per gruppo, distorcono tutte le quote) e **salti anomali di dollar volume**.
Il default `DV_MODE = "adj"` (adjusted_close × volume) è quello coerente col feed
EODHD, che serve volume split-adjusted e close as-traded (verificato sullo split AAPL
4:1 del 31/08/2020). Un `max_salto_dv` > ~8 in corrispondenza di uno split noto
(es. USO 1:8 del 28/04/2020) segnalerebbe il contrario: in quel caso verificare la
continuità del DV nelle due modalità e correggere `src/config.py`.
"""
    )
    qa = data_quality(data, DV_MODE)
    st.dataframe(qa, use_container_width=True)
    suspects = qa[qa["max_salto_dv"] > 8]
    if not suspects.empty:
        st.warning("⚠️ Possibili split non gestiti: "
                   + ", ".join(f"`{t}`" for t in suspects.index))

with st.expander("ℹ️ Metodologia e note"):
    st.markdown(
        f"""
**Pipeline** (tutta causale, rolling su dati ≤ t — nessun look-ahead):

1. `DV = adjusted_close × volume` per ETF (`DV_MODE = {DV_MODE}`: il feed EODHD
   serve volume split-adjusted e close as-traded, quindi questo è l'unico prodotto
   continuo attraverso gli split — verificato su AAPL 4:1 del 31/08/2020)
2. Somma per gruppo → media mobile {smooth}g → **quota** = DV gruppo / DV totale
3. **Z-score di attenzione** = (quota − media rolling {Z_WINDOW}g) / dev.std rolling
4. **Pressione firmata** = Σ(DV × segno del rendimento in eccesso) / Σ(DV), rolling
   {smooth}g — rendimento su adjusted_close demeaned {PRESSURE_DEMEAN}g, altrimenti
   l'accrual del NAV inchioderebbe il gruppo Cash a ~+0.9 in permanenza
5. **Rotazione** = Δquota a {rot_win}g in punti percentuali

**Caveat onesti:**
- Il DV degli ETF è un proxy dell'**attenzione**, non dei flussi reali di capitale
  (futures e single stock dominano; i fund flows veri richiederebbero
  creations/redemptions, non affidabili come storico su EODHD).
- Volume e volatilità sono legati: un picco di z dice "qui sta succedendo qualcosa",
  è la pressione firmata a dire in che verso.
- Il gruppo Valute (UUP/FXE/FXY) pesa pochissimo in quota assoluta: è pensato per
  essere letto in z-score, non nel fiume.
- Universo **fisso dal 2008**: niente ETF entrati dopo (XLRE, XLC, IBIT) per non
  spezzare le quote a metà storia.

**Roadmap ricerca pattern (fase 2):** eventi discreti (es. z > 2 con pressione
positiva) → event study su rendimenti forward vs null appaiato, regole calibrate
solo sull'in-sample (fino al {cutoff:%d/%m/%Y}), un solo passaggio finale
sull'out-of-sample. La modalità ricerca nella sidebar serve a non contaminare
l'OOS nemmeno visivamente. Il cutoff mostrato avanza col passare dei giorni
(70% posizionale): all'avvio della fase 2 va **congelato** impostando
`IS_END_DATE` in `src/config.py`, così il confine diventa una data assoluta.
"""
    )

col_dl1, col_dl2 = st.columns(2)
col_dl1.download_button(
    "⬇️ Scarica quote (CSV)",
    shares_v.to_csv().encode("utf-8"),
    file_name="liquidity_shares.csv",
    mime="text/csv",
)
col_dl2.download_button(
    "⬇️ Scarica z-score (CSV)",
    z_v.to_csv().encode("utf-8"),
    file_name="liquidity_zscores.csv",
    mime="text/csv",
)
