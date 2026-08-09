# 🌊 Liquidity Flow Map

Dashboard Streamlit che traccia **dove si muove l'attività in dollari** (dollar volume)
tra le macro-classi del mercato USA, usando gli ETF più liquidi come proxy. Dati EODHD.

## L'idea

Il postulato "la liquidità non si crea, si trasferisce" è falso sui dollar volume
assoluti — l'attività aggregata si espande e si contrae con la volatilità. Ma diventa
**vero per costruzione** lavorando sulle **quote**: `share_g = DV_g / Σ DV` somma a 1,
quindi un gruppo guadagna quota solo se altri la perdono. Il "flusso" è la variazione
di quota, letta su due canali:

- **Attenzione** — z-score della quota vs la propria storia rolling (252g): quanto un
  gruppo è sopra/sotto la propria norma, al netto della dominanza di SPY e del trend
  secolare di adozione degli ETF.
- **Pressione firmata** — volume pesato per il segno del rendimento *in eccesso*
  (total-return demeaned su 63 giorni), in [-1, +1]: distingue l'accumulo dalla
  distribuzione. Il demean è necessario: col segno del rendimento grezzo gli ETF
  cash (BIL/SHV) resterebbero inchiodati a ~+0.9 per pura meccanica di accrual
  del NAV.

## Universo (fisso dal 2008)

| Gruppo | ETF |
|---|---|
| Azionario USA | SPY, QQQ, IWM |
| Treasury | TLT, IEF, SHY |
| Credito | LQD, HYG |
| Commodity | DBC, USO |
| Oro/Metalli | GLD, SLV |
| Cash (T-Bill) | BIL, SHV |
| Valute | UUP, FXE, FXY |
| Estero | EEM, EFA |

Livello 2 (drill-down equity): i 9 SPDR settoriali storici (XLK, XLF, XLE, XLV, XLI,
XLY, XLP, XLU, XLB), vivi dal 1998. XLRE/XLC/IBIT esclusi: l'ingresso a metà storia
spezzerebbe le quote.

## Pannelli

1. **Il fiume** — area impilata 100% delle quote (vista di regime)
2. **Heatmap** — z-score di attenzione o pressione firmata, settimanale/mensile
3. **Rotazione** — Δquota per gruppo su finestra 5/21/63g (barre divergenti; niente
   Sankey: gli accoppiamenti "da chi a chi" non sono identificabili dai dati)
4. **La pista** — livello vs momentum dell'attenzione con scie (stile RRG)

Più: **modalità ricerca** che nasconde l'out-of-sample (30% finale della storia) per
non contaminare la futura ricerca pattern, pannello diagnostico dati e download CSV.

## Deploy su Streamlit Cloud

1. Pusha questo repository su GitHub
2. [share.streamlit.io](https://share.streamlit.io) → **New app** → seleziona repo e `app.py`
3. **Advanced settings → Secrets**:
   ```toml
   EODHD_API_KEY = "la-tua-chiave-eodhd"
   ```
4. Deploy → l'app è live

## Esecuzione locale

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # inserisci la chiave
streamlit run app.py
```

## Verifica offline (senza chiave API)

```bash
python scripts/selftest.py          # invarianti pipeline su dati sintetici
python scripts/selftest.py --live   # + smoke test EODHD con chiave demo
```

I check garantiscono: quote che sommano a 1, **nessun look-ahead** (troncare la storia
non cambia il passato), pressione in [-1, +1], coerenza della rotazione, cutoff IS/OOS.

## Roadmap — fase 2 (ricerca pattern)

Eventi discreti (es. `z > 2` con pressione positiva) → event study sui rendimenti
forward vs null appaiato. Protocollo IS/OOS 70/30 cronologico: regole e soglie
calibrate solo sull'in-sample, congelate, un solo passaggio finale sull'out-of-sample.

## Caveat onesti

- Il DV degli ETF è un proxy dell'**attenzione**, non dei flussi reali (futures e
  single stock dominano l'attività; i fund flows veri richiederebbero lo storico
  di creations/redemptions).
- Volume ≈ volatilità: un picco di z dice "sta succedendo qualcosa", la pressione
  firmata dice in che verso.
- Il gruppo Valute pesa pochissimo in quota assoluta (UUP+FXE+FXY ≈ 0,1% del totale):
  va letto in z-score, non nel fiume.
- `DV_MODE = "adj"` (adjusted_close × volume) è il default corretto per EODHD:
  il feed serve volume split-adjusted e close as-traded (verificato sullo split
  AAPL 4:1 del 31/08/2020), quindi `close × volume` sottostimerebbe di ~8× il DV
  di USO pre-2020. Residuo noto: l'adjusted include i dividendi (drift lento,
  assorbito in gran parte dallo z-score rolling). Il pannello diagnostico resta
  come guardia.
- La pressione firmata del gruppo Cash va letta come "assente" (rumore attorno a
  zero), non come segnale: il prezzo di BIL/SHV non contiene informazione
  direzionale.
