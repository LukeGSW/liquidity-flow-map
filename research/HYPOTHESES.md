# Pre-registrazione fase 2 — Liquidity Flow Map

**Versione 2 — 2026-08-09** (v1 stesso giorno; revisione dopo calibrazione IS sui prezzi) · In-sample: 2009 → **2021-01-04** (incluso) · Out-of-sample: 2021-01-05 → oggi · **CICLO 1 CHIUSO il 2026-08-10: nessuna ipotesi confermata (vedi §7)**

Questo documento congela ipotesi e disegno statistico PRIMA di qualsiasi test
sull'out-of-sample. La copia operativa letta dal codice è `src/hypotheses.py`;
il motore è `src/event_study.py`; l'esecuzione avviene nella pagina
**🧪 Event study** dell'app.

---

## 1. Da dove vengono le ipotesi (scansione IS, ammissione onesta)

La scansione esplorativa in-sample (2009 → gen 2021) è stata fatta su **quote e
z-score di dollar volume**, con un solo prezzo disponibile (VTI). Ha prodotto:

- **Robusto (settori):** mean-reversion dell'attenzione — dopo z>+2 la quota
  restituisce ~1–1.7 pp entro 63g (17/60 test p<0.05, tutti concordi nel segno).
- **Robusto (macro):** blow-off dell'oro — dopo z>+1.5 la quota sale ancora
  (+2 pp a 21g, coerente nei due semiperiodi, eventi su 9 anni), poi si
  riassorbe a 63g (−1 pp; gamba meno stabile).
- **Candidati deboli:** debolezza di mercato a 5–21g dopo spike su
  Tecnologia/Industriali/Cons. discrezionali (q-FDR ≈ 0.19 su VTI).
- **Bocciato:** "spike di attenzione ⇒ mercato debole" aggregato (artefatto 2009).

Le ipotesi qui sotto **traducono quei comportamenti delle quote in attese sui
prezzi**. I prezzi settoriali NON sono ancora stati guardati: la "calibrazione
IS" nella pagina Event study è il primo sguardo, ed è lecita perché resta
dentro l'in-sample. Se un'ipotesi non regge nemmeno in IS sui prezzi, si
revisiona PRIMA di toccare l'OOS.

## 2. Pipeline congelata

- Universo e dati: come `src/config.py` (universo fisso dal 2008, `DV_MODE="adj"`)
- Quote: smoothing **21g**; z-score: rolling **252g**; eventi: incrocio soglia
  con **debounce 21g**
- Split: `IS_END_DATE = "2021-01-04"` (congelato in config)

## 3. Le ipotesi attive (v2 — 4 test)

| ID | Evento | Esito atteso | Orizzonte | Direzione | Peso |
|---|---|---|---|---|---|
| **H1a** | z settore > +2.0 | sottoperformance vs paniere EW | 21g | − | **primaria** |
| **H1b** | z settore > +2.0 | sottoperformance vs paniere EW | 63g | − | **primaria** |
| H2 | z settore < −1.5 | sovraperformance vs paniere EW | 63g | + | secondaria |
| H3a | z settore > +2.0 | rendimento assoluto negativo | 5g | − | secondaria |

### Ipotesi ritirate in calibrazione IS (v1 → v2, OOS mai guardato)

| ID | Motivo del ritiro |
|---|---|
| H4a | **Direzione opposta all'attesa**: GLD dopo lo spike di attenzione rende −0.38% a 21g contro +0.41% del null (eccesso −0.79%, p one-sided 0.73, n=15). Il momentum della *quota* (+2 pp, reale) non si trasferisce al *prezzo*: l'attività extra è churn bilaterale, non domanda netta. |
| H4b | Gamba secondaria della famiglia oro: con la primaria morta esce dal protocollo (era comunque non significativa: eccesso −0.86%, p=0.31). |
| H3b | La più debole della famiglia settori (eccesso −0.40%, p=0.23) e ridondante con H1a/H3a: tolta per non diluire l'FDR. |

Definizioni precise:
- **Rendimento forward**: log-rendimento su adjusted_close, in %, da t (o da
  t+21 per H4b) a t+h.
- **Paniere EW**: media aritmetica dei log-rendimenti forward dei 9 XL*.
  Esito "relativo" = forward del settore − paniere.
- Eventi settoriali: aggregati sui 9 settori (ogni settore contribuisce con i
  propri eventi e il proprio esito).

## 4. Disegno statistico (identico alla scansione IS)

- **Null appaiato per regime di volatilità**: per ogni evento, controlli
  estratti dalla stessa serie e dallo stesso terzile di volatilità realizzata
  21g (paniere EW per H1–H3, GLD per H4), esclusi i giorni entro ±10g da un
  evento; bootstrap **B=5000**, **seed=42** (risultati riproducibili).
- **Test one-sided** nella direzione pre-dichiarata; α = 0.05 per ipotesi.
- **BH-FDR q ≤ 0.10** sulla famiglia dei test attivi (4 in v2 — i falsi
  positivi si contano).
- Numerosità minima: 5 eventi, altrimenti il test è "non eseguibile".

## 5. Procedura e criteri

1. **Calibrazione IS** (libera, ripetibile): le ipotesi devono mostrare in IS
   effetto nella direzione attesa. Ipotesi morte in IS → si eliminano o si
   riformulano QUI, con nuova data, prima di ogni sguardo all'OOS.
2. **Passaggio OOS: UNO SOLO.** Si esegue quando le regole sono ferme.
   Conferma = direzione giusta E q ≤ 0.10 (per le primarie); le secondarie
   confermate solo se anche una primaria della stessa famiglia regge.
3. Dopo l'OOS, qualsiasi modifica alle regole apre un NUOVO ciclo: nuova
   pre-registrazione, e il vecchio OOS diventa il nuovo IS (l'OOS pulito
   sarà solo il futuro non ancora osservato).

## 6. Cosa NON è in gioco

Ipotesi già bocciate in IS e quindi escluse: "spike di attenzione ⇒ mercato
debole" (VTI), qualsiasi timing di mercato da eventi macro di attenzione,
segnali dalla pressione firmata del gruppo Cash, e — dalla v2 — qualsiasi
implicazione direzionale sul prezzo di GLD dall'attenzione sull'oro.

## 7. Registro delle esecuzioni

**2026-08-09 — Calibrazione IS (prezzi), protocollo v1, 7 test**
(`event_study_is.csv`; n = eventi, eccesso = effetto − null, p one-sided)

| ID | n | Effetto % | Null % | Eccesso % | p | q | Esito |
|---|---|---|---|---|---|---|---|
| H1a | 120 | −0.37 | +0.12 | −0.49 | 0.051 | 0.157 | ➖ direzione giusta |
| H1b | 120 | −0.95 | +0.31 | −1.26 | 0.0058 | 0.041 | ✅ confermata in IS |
| H2 | 144 | +0.24 | −0.38 | +0.62 | 0.108 | 0.190 | ➖ direzione giusta |
| H3a | 120 | −0.22 | +0.20 | −0.42 | 0.067 | 0.157 | ➖ direzione giusta |
| H3b | 120 | +0.41 | +0.81 | −0.40 | 0.228 | 0.319 | ➖ debole → ritirata |
| H4a | 15 | −0.38 | +0.41 | −0.79 | 0.734 | 0.734 | ❌ opposta → ritirata |
| H4b | 15 | −0.04 | +0.82 | −0.86 | 0.306 | 0.357 | ritirata (famiglia) |

Decisione: protocollo ridotto a v2 (H1a, H1b, H2, H3a).

---

**2026-08-10 — Passaggio OOS (2021-01-05 → 2026-08) — CICLO 1 CHIUSO**
(`event_study_oos.csv`)

*Nota di protocollo:* il run è avvenuto con la v1 ancora deployata, quindi il
CSV contiene anche le ipotesi ritirate (famiglia da 7 test). I p per-ipotesi
non dipendono dalla famiglia; il q è stato **ricalcolato sulla famiglia v2**
(4 test attivi): tutte le attive risultano q = 0.288.

| ID | n | Effetto % | Null % | Eccesso % | p | q (v2) | Esito |
|---|---|---|---|---|---|---|---|
| H1a | 49 | −0.40 | −0.09 | −0.31 | 0.288 | 0.288 | ➖ direzione giusta |
| H1b | 49 | −0.45 | +0.19 | −0.64 | 0.242 | 0.288 | ➖ direzione giusta (≈metà dell'effetto IS) |
| H2 | 55 | +0.66 | +0.11 | +0.55 | 0.267 | 0.288 | ➖ direzione giusta |
| H3a | 49 | −0.22 | +0.23 | −0.46 | 0.113 | 0.288 | ➖ direzione giusta |

Ritirate, riportate solo per trasparenza (nessuna decisione ne dipende):
H3b di nuovo in direzione opposta (+0.16%, il ritiro era corretto);
H4a/H4b stavolta in direzione "giusta" (+1.80% / −2.32%, n=8) — con 8 eventi
il segno rimbalza da un campione all'altro: è la dimostrazione che erano
rumore, non un motivo per resuscitarle.

**VERDETTO CICLO 1: nessuna ipotesi confermata** secondo il criterio
pre-registrato (direzione giusta E q ≤ 0.10). Il fenomeno "climax di
attenzione → debolezza relativa" esce però con direzione giusta in IS **e**
OOS, con effetto dimezzato (−1.26% → −0.64% a 63g): reale ma debole, e con
~50 eventi ogni 5 anni la potenza statistica non basta per effetti di questa
taglia. Esito operativo: **declassato a tilt informativo** nella dashboard;
nessuna regola di trading.

Conseguenze (§5.3): il 2021-2026 non è più out-of-sample per nessuna ipotesi
correlata a queste. Un eventuale **ciclo 2** (es. fattore cross-sectional di
attenzione: rank mensile dei settori per z, long trascurati / short climax —
usa tutti i dati, non solo gli estremi, quindi molta più potenza) dovrà
dichiarare che il 2021-2026 è semi-contaminato e cercare la validazione vera
solo sul futuro non ancora osservato.
