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

Più: sezione **"Segnali attivi e cosa aspettarsi"** (gruppi in attenzione estrema
con l'attesa misurata in-sample), **modalità ricerca** che nasconde l'out-of-sample
(30% finale della storia), pannello diagnostico dati e download CSV.

## Risultati della prima scansione IS (2009 → gen 2021)

Eventi = incrocio di soglia dello z (±1.5/±2, debounce 21g); null appaiato per
terzili di volatilità; BH-FDR, jackknife, esclusione epoche. In sintesi:

- **Robusto (settori):** mean-reversion dell'attenzione — dopo z > +2 la quota
  restituisce ~1–1.7 pp entro 63g (17/60 test p<0.05, tutti concordi).
- **Robusto (macro):** l'attenzione sull'**oro** fa *blow-off*: +2 pp di quota a
  21g dopo lo spike (coerente nei due semiperiodi), riassorbita a 63g (−1 pp).
- **Bocciato:** "spike di attenzione → mercato debole" (artefatto del rimbalzo
  2009); a livello macro nessun evento di attenzione predice VTI nell'IS.
- **Parcheggiati per la fase 2:** debolezza assoluta a 5–21g dopo spike su
  Tecnologia/Industriali/Consumi discrezionali (q-FDR ≈ 0.19 su VTI: da
  ritestare con i rendimenti forward del settore stesso).

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

Gli 11 check garantiscono: quote che sommano a 1, **nessun look-ahead** (troncare
la storia non cambia il passato), pressione in [-1, +1] e non inchiodata
dall'accrual, coerenza della rotazione, cutoff IS/OOS, e il motore event study
(rileva un effetto piantato, è deterministico a parità di seed, BH-FDR sano).

## Fase 2 — protocollo pre-registrato (attivo)

Il confine IS/OOS è **congelato**: `IS_END_DATE = "2021-01-04"` in `src/config.py`.
Le **7 ipotesi** (climax di attenzione settoriale → sottoperformance relativa a
21/63g; settore trascurato → recupero; blow-off dell'oro mappato su GLD, gamba
momentum + gamba riassorbimento) sono pre-registrate in **`research/HYPOTHESES.md`**
con disegno statistico completo (null appaiato per vol, test one-sided, B=5000
seed=42, BH-FDR q≤0.10) e si eseguono dalla pagina **🧪 Event study fase 2**
dell'app: calibrazione IS libera e ripetibile, **un solo** passaggio
out-of-sample a regole ferme. Il motore statistico è `src/event_study.py`
(puro, coperto dal selftest); la copia operativa delle ipotesi è
`src/hypotheses.py`.

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
