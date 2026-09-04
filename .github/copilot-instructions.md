# Istruzioni Copilot per amisim

## Descrizione del software

AMISim è uno strumento avanzato per la meso-simulazione e l'analisi del traffico veicolare su scala urbana e regionale. Grazie ai file di configurazione di tipo JSON e INI, è possibile personalizzare parametri come la rete stradale, la domanda di traffico, le regole di circolazione e le strategie di controllo. 

## Ambito
Queste istruzioni si applicano all'intero repository.

## Contesto del progetto
- Questo e un pacchetto Python con il codice sorgente in `src/amisim`.
- Mantieni la compatibilita con la struttura del pacchetto esistente e con gli entry point della CLI.

## Regole di sviluppo
- Preferisci modifiche piccole e mirate.
- Il codice è typed, quindi utilizza le annotazioni di tipo per tutte le funzioni e variabili pubbliche.
- Mantieni le API pubbliche esistenti, salvo richiesta esplicita di modifica.
- Aggiungi test per i cambiamenti di comportamento in `tests/`.
- Mantieni uno stile di codice coerente con il progetto.
- Evita di aggiungere dipendenze pesanti se non necessario.
- Prediligi l'efficienza quando viene richiesto di sviluppare codice senza fare compromettere troppo la leggibilità.
- Nello sviluppo verranno usate librerie ga-* (ad esempio `ga-configreader`, `ga-graph`, ecc.) che sono sviluppate da me e presente nei repository andreagemma/configreader, andreagemma/graph, ecc. Se noti criticità o problemi in queste librerie, segnala e contribuisci alle correzioni nei rispettivi repository chiedendolo prima.

## Controlli di qualita
Prima di finalizzare le modifiche, esegui:
- `pytest -q`

Se rilevante per i file modificati, esegui anche gli script di qualita del progetto.

## Regole di verifica e allineamento
- A ogni richiesta di verifica o review, controlla e mantieni aggiornato `CHANGELOG.md`.
- Mantieni sempre aggiornata la documentazione del progetto (inclusi `README.md` e contenuti in `docs/`) in base alle modifiche effettuate.
- Verifica che tutte le dipendenze necessarie siano dichiarate correttamente in `pyproject.toml`.
- Verifica la coerenza del nome del progetto e aggiorna dove necessario: documentazione, file di licenza e changelog.
- Mantieni aggiornato `MANIFEST.in`

## Regole licenze terze parti
- In base ai pacchetti dichiarati nei file `.toml` (in particolare `pyproject.toml`), raccogli e archivia i file di licenza dei pacchetti terzi.
- Per ogni pacchetto, salva i file in `licenses/third_party/packages/<nome_pacchetto>/`.
- Salva almeno un file `LICENSE` per pacchetto e, se presente a monte, salva anche `COPYING`.
- Mantieni aggiornato `licenses/third_party/summary.tsv` con almeno queste colonne: package, version, license_file, source_url.
- Mantieni aggiornato anche `THIRD_PARTY_NOTICE.md` con il riepilogo delle dipendenze terze parti e dei relativi riferimenti di licenza.
- Mantieni aggiornato `MANIFEST.in`

## Documentazione
- Aggiorna `README.md` e `CHANGELOG.md` quando cambiano il comportamento o le interfacce rivolte all'utente.
- Verifica che le docstring siano concise e utili in stile sphinx con breve descrizione all'inizio, parametri, e valore di ritorno e eventuali eccezioni sollevate, utilizzando la sintassi corretta per ciascun elemento. Suggerisci correzioni se necessario.
- Nel supporto alla realizzazione della documentazione segui le indicazione sulla produzione della documentazione.
- Mantieni aggiornato `MANIFEST.in`

## Sicurezza
- Non eseguire operazioni distruttive sulla cronologia git.
- Se i requisiti non sono chiari, chiedi chiarimenti prima di fare refactor estesi.
