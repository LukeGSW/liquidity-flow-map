"""
config.py — Configurazione centralizzata: universo ETF, gruppi, colori, parametri pipeline.

Tutte le scelte "bloccate" della metodologia vivono qui, in un posto solo.
"""

# === PERIODO ===
# Universo FISSO dal 2008: tutti gli ETF sotto sono vivi da prima di questa data.
# Non aggiungere ticker con inception successiva senza gestire il salto di quota
# (l'ingresso di un nuovo membro sposta artificialmente le quote di tutti).
START_DATE = "2008-01-01"

# === LIVELLO 1: MACRO-CLASSI ===
# Formato ticker EODHD (suffisso .US). 2-3 ETF liquidi per gruppo.
MACRO_GROUPS = {
    "Azionario USA": ["SPY.US", "QQQ.US", "IWM.US"],
    "Treasury":      ["TLT.US", "IEF.US", "SHY.US"],
    "Credito":       ["LQD.US", "HYG.US"],
    "Commodity":     ["DBC.US", "USO.US"],
    "Oro/Metalli":   ["GLD.US", "SLV.US"],
    "Cash (T-Bill)": ["BIL.US", "SHV.US"],
    "Valute":        ["UUP.US", "FXE.US", "FXY.US"],
    "Estero":        ["EEM.US", "EFA.US"],
}

# Valutari minori DELIBERATAMENTE esclusi (DV ~1-5 M$/giorno, troppo rumorosi
# per lo z-score giornaliero): FXB.US, FXF.US, FXC.US, FXA.US.
# Per includerli basta aggiungerli alla lista "Valute" qui sopra.

# === LIVELLO 2: SETTORI AZIONARI (drill-down dentro l'equity) ===
# SPDR storici, tutti vivi dal 1998 -> universo fisso anche qui.
# XLRE (2015) e XLC (2018) esclusi: entrerebbero a metà storia spezzando le quote.
SECTOR_GROUPS = {
    "Tecnologia":       ["XLK.US"],
    "Finanziari":       ["XLF.US"],
    "Energia":          ["XLE.US"],
    "Salute":           ["XLV.US"],
    "Industriali":      ["XLI.US"],
    "Consumi discrez.": ["XLY.US"],
    "Consumi difens.":  ["XLP.US"],
    "Utility":          ["XLU.US"],
    "Materiali":        ["XLB.US"],
}

# === COLORI (tema dark) ===
GROUP_COLORS = {
    "Azionario USA": "#2196F3",
    "Treasury":      "#7E57C2",
    "Credito":       "#26A69A",
    "Commodity":     "#FF7043",
    "Oro/Metalli":   "#FFCA28",
    "Cash (T-Bill)": "#B0BEC5",
    "Valute":        "#EC407A",
    "Estero":        "#9CCC65",
}

SECTOR_COLORS = {
    "Tecnologia":       "#2196F3",
    "Finanziari":       "#26A69A",
    "Energia":          "#FF7043",
    "Salute":           "#EC407A",
    "Industriali":      "#8D6E63",
    "Consumi discrez.": "#FFCA28",
    "Consumi difens.":  "#B0BEC5",
    "Utility":          "#7E57C2",
    "Materiali":        "#9CCC65",
}

# === PARAMETRI PIPELINE ===
SMOOTH_WINDOWS = [5, 21, 63]      # smoothing quote (giorni)
DEFAULT_SMOOTH = 21

ROTATION_WINDOWS = [5, 21, 63]    # finestra rotazione Δquota (giorni)
DEFAULT_ROTATION = 21

Z_WINDOW = 252                    # finestra rolling z-score attenzione (giorni)

# Modalità dollar volume: "adj" = adjusted_close * volume; "raw" = close * volume.
# Default "adj": verificato sul feed EODHD (AAPL attorno allo split 4:1 del
# 31/08/2020) che 'volume' è split-adjusted mentre 'close' è as-traded, quindi
# close*volume salta di un fattore pari allo split (USO 1:8 apr 2020 => DV
# pre-split sottostimato ~8x), mentre adjusted_close*volume è continuo.
# Residuo noto di "adj": l'adjusted include anche i dividendi, che introducono
# un drift moltiplicativo lento sulla storia lunga — in gran parte assorbito
# dallo z-score rolling. Il pannello diagnostico resta come guardia.
DV_MODE = "adj"

# Direzione per la pressione firmata: "sign" = segno del rendimento total-return
# IN ECCESSO (demeaned su finestra rolling, vedi PRESSURE_DEMEAN) — il segno del
# rendimento grezzo è inutilizzabile per gli ETF cash/bond, dominati da accrual
# ed ex-div; "range" = posizione della chiusura nel range del giorno.
PRESSURE_MODE = "sign"

# Finestra rolling (giorni) per il demean del rendimento nella pressione firmata.
PRESSURE_DEMEAN = 63

# Risoluzioni heatmap (label -> freq pandas)
HEATMAP_FREQS = {"Settimanale": "W-FRI", "Mensile": "ME"}

# Split cronologico in-sample / out-of-sample per la ricerca pattern.
# CONGELATO il 2026-08-09 all'avvio della fase 2: l'in-sample termina il
# 2021-01-04 (ultima data dei CSV usati per la scansione esplorativa).
# NON modificare senza una nuova pre-registrazione (research/HYPOTHESES.md).
IS_FRACTION = 0.70
IS_END_DATE = "2021-01-04"
