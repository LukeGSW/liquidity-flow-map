# Pre-registrazione fase 2 — Liquidity Flow Map

**Data di congelamento: 2026-08-09** · In-sample: 2009 → **2021-01-04** (incluso) · Out-of-sample: 2021-01-05 → oggi

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

## 3. Le 7 ipotesi

| ID | Evento | Esito atteso | Orizzonte | Direzione | Peso |
|---|---|---|---|---|---|
| **H1a** | z settore > +2.0 | sottoperformance vs paniere EW | 21g | − | **primaria** |
| **H1b** | z settore > +2.0 | sottoperformance vs paniere EW | 63g | − | **primaria** |
| H2 | z settore < −1.5 | sovraperformance vs paniere EW | 63g | + | secondaria |
| H3a | z settore > +2.0 | rendimento assoluto negativo | 5g | − | secondaria |
| H3b | z settore > +2.0 | rendimento assoluto negativo | 21g | − | secondaria |
| **H4a** | z Oro/Metalli > +1.5 | GLD positivo (gamba momentum) | 21g | + | **primaria** |
| H4b | z Oro/Metalli > +1.5 | GLD negativo da t+21 a t+63 (riassorbimento) | 21→63g | − | secondaria |

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
- **BH-FDR q ≤ 0.10** sulla famiglia dei 7 test (i falsi positivi si contano).
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
segnali dalla pressione firmata del gruppo Cash.
