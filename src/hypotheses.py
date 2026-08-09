"""
hypotheses.py — Ipotesi PRE-REGISTRATE della fase 2 (copia operativa).

Il documento umano è research/HYPOTHESES.md: questo file è la versione che il
codice legge. CONGELATE il 2026-08-09 sulla base della scansione in-sample
2009 -> gen 2021. Qualsiasi modifica dopo aver toccato l'out-of-sample
equivale a una nuova pre-registrazione con OOS bruciato.

Campi di ogni ipotesi:
    famiglia   'settori' (eventi su tutti i 9 XL*) oppure 'oro' (Oro/Metalli)
    soglia/dir definizione dell'evento: z incrocia +soglia (dir=+1) o -soglia (dir=-1)
    esito      'relativo' = log-fwd settore - media dei 9 settori
               'assoluto' = log-fwd del settore stesso
               'gld'      = log-fwd di GLD
    h          orizzonte in giorni di borsa
    start_lag  inizio della finestra esito (0 = dall'evento; 21 = seconda gamba)
    attesa     direzione attesa dell'eccesso vs null (+1/-1) — test one-sided
    primaria   True = ipotesi principale del protocollo
"""

FROZEN_DATE = "2026-08-09"

DEBOUNCE = 21          # giorni di borsa tra eventi dello stesso segnale
ALPHA = 0.05           # significatività one-sided per singola ipotesi
FDR_Q = 0.10           # soglia BH-FDR sulla famiglia dei 7 test
B_BOOT = 5000          # ricampionamenti bootstrap
SEED = 42              # determinismo

HYPOTHESES = [
    {"id": "H1a", "famiglia": "settori", "soglia": 2.0, "dir": +1,
     "esito": "relativo", "h": 21, "start_lag": 0, "attesa": -1, "primaria": True,
     "descrizione": "Climax di attenzione: dopo z>+2 il settore sottoperforma "
                    "il paniere EW dei 9 settori a 21 giorni"},
    {"id": "H1b", "famiglia": "settori", "soglia": 2.0, "dir": +1,
     "esito": "relativo", "h": 63, "start_lag": 0, "attesa": -1, "primaria": True,
     "descrizione": "Climax di attenzione: sottoperformance relativa a 63 giorni"},
    {"id": "H2", "famiglia": "settori", "soglia": 1.5, "dir": -1,
     "esito": "relativo", "h": 63, "start_lag": 0, "attesa": +1, "primaria": False,
     "descrizione": "Settore trascurato: dopo z<-1.5 sovraperformance relativa "
                    "a 63 giorni"},
    {"id": "H3a", "famiglia": "settori", "soglia": 2.0, "dir": +1,
     "esito": "assoluto", "h": 5, "start_lag": 0, "attesa": -1, "primaria": False,
     "descrizione": "Climax di attenzione: debolezza assoluta del settore a 5 giorni"},
    {"id": "H3b", "famiglia": "settori", "soglia": 2.0, "dir": +1,
     "esito": "assoluto", "h": 21, "start_lag": 0, "attesa": -1, "primaria": False,
     "descrizione": "Climax di attenzione: debolezza assoluta del settore a 21 giorni"},
    {"id": "H4a", "famiglia": "oro", "soglia": 1.5, "dir": +1,
     "esito": "gld", "h": 21, "start_lag": 0, "attesa": +1, "primaria": True,
     "descrizione": "Blow-off oro, gamba momentum: dopo z>+1.5 su Oro/Metalli, "
                    "GLD sale nei 21 giorni successivi"},
    {"id": "H4b", "famiglia": "oro", "soglia": 1.5, "dir": +1,
     "esito": "gld", "h": 63, "start_lag": 21, "attesa": -1, "primaria": False,
     "descrizione": "Blow-off oro, gamba riassorbimento: GLD debole da t+21 a t+63"},
]
