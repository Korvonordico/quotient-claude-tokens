# Quotient: preventivi dei token e limiti di utilizzo per Claude Code

*[Read in English](README.md)*

**Sapere quanto costa un lavoro dell'IA prima di cominciarlo, e non perdere più una settimana per il limite di utilizzo.** Un plugin per [Claude Code](https://code.claude.com).

Oggi un lavoro con l'IA funziona come un meccanico che ti ripara la macchina senza dirti il prezzo: lo scopri alla cassa. Con un abbonamento la cassa è il limite di utilizzo, e un solo lavoro grande può consumare una settimana intera. Quotient ti dà prima il prezzo, ti fa scegliere, misura quanto è costato davvero e impara dalla differenza.

Il nome tiene insieme le due metà: comincia come *quote*, che in inglese vuol dire preventivo, e in matematica il *quotient* è il quoziente, il risultato di una divisione, come un lavoro grande diviso in rate.

## Cosa sa fare

- **Il preventivo prima di un lavoro grande.** Quando un lavoro costerà probabilmente più della tua soglia, o ogni volta che dici che è un lavoro grosso, Claude si ferma e apre una finestra di scelta: *essenziale*, *buono* o *massimo*, ognuno con quello che comprende e il suo costo stimato, proporzionati al lavoro. Le stime non sono garantite: diventano più precise con l'uso.
- **Il ritmo, lo scegli tu.** Nella stessa finestra: tutto oggi, oppure a rate, scritte in giorni e quantità al giorno («5 giorni, circa 100.000 al giorno»). Nel campo libero scrivi il ritmo che vuoi.
- **Il costo vero, dopo.** Quotient legge i file di Claude Code e somma quanto è costato davvero il lavoro, contando ogni chiamata una volta sola, in token pesati (token di ingresso equivalenti, con le proporzioni dei prezzi delle API).
- **Impara dai suoi errori.** Il rapporto fra costo vero e stima diventa un fattore di correzione per i preventivi dopo; il resoconto mostra quanto sbagliava all'inizio e quanto sbaglia adesso.
- **Le rate lavorano mentre non ci sei.** Un lavoro grande si divide in pezzi: una rata al giorno (o più, se vuoi), ognuna con un tetto di spesa e un file di consegna che dice cosa è fatto e da dove riprendere. Su Windows una rata sveglia il PC dalla sospensione o dall'ibernazione, lavora e lo rimette a dormire se nessuno lo usa. Quando arriva al tetto si ferma in ordine invece di essere tagliata a metà, e due rate dello stesso lavoro non partono mai insieme. Puoi farne partire una in più lo stesso giorno, a tuo rischio.
- **La settimana tutta insieme.** Due o tre lavori possono stare ognuno nella settimana e non starci insieme. Quotient somma tutte le rate previste fino all'azzeramento del limite settimanale, tiene una riserva per il tuo uso normale e, quando il piano non ci sta, ti chiede quali lavori tenere, rallentare o mettere in pausa. Una rata non entra mai nella riserva: si accorcia, o aspetta.
- **I tuoi limiti sotto gli occhi.** Registra la parte usata del limite delle 5 ore e di quello settimanale e quando si azzerano, mostra quanto resta nella riga di stato, e stima quanti token vale l'1% di ogni limite, così un preventivo può dire «questo prende circa l'8% della tua settimana».
- **Si configura una volta.** Al primo uso si apre una finestra con quattro impostazioni: soglia, riserva della settimana, lingua, cosa fa il PC dopo le rate. `/quotient:setup` le cambia, `/quotient:help` elenca tutti i comandi.
- **Privato.** Tutto resta sul tuo computer. Quotient non si collega mai a internet; `export` dà solo numeri, da condividere se vuoi.

## Installazione

In Claude Code:

```
/plugin marketplace add Korvonordico/quotient-claude-tokens
/plugin install quotient@quotient
```

Serve Python 3.8 o più recente (solo la libreria standard) e `sh` (su Windows arriva con Git for Windows, che Claude Code usa già).

## Il primo uso

La prima volta Quotient chiede quattro impostazioni in una finestra di scelta: la soglia (da quanti token pesati un lavoro riceve un preventivo), la parte della settimana tenuta libera per l'uso normale, la lingua del resoconto, e cosa fa il PC dopo le rate programmate. Le stesse quattro compaiono nelle impostazioni dei plugin di Claude Code. Per cambiarle dopo: `/quotient:setup`.

## Come funziona

- **All'inizio di una chat** (hook `SessionStart`), Quotient dà a Claude le regole del preventivo una volta sola: circa 650 token. **A ogni messaggio** (hook `UserPromptSubmit`) solo una riga corta: la soglia, il fattore di correzione, quanto è grande la conversazione e le novità delle tue rate. Circa 70 token.
- **Quando interviene:** quando un lavoro costerà probabilmente più della soglia, e ogni volta che dici che è un lavoro grosso o chiedi un preventivo.
- **Si apre una finestra di scelta** (quella di Claude Code) con due domande:
  - **Livello**: *essential* (essenziale), *good* (buono), *max* (massimo), proporzionati al lavoro. Per un lavoro da 500.000: massimo 500.000, medio 250.000, minimo 100.000.
  - **Ritmo**: tutto oggi, oppure a rate, adatte al lavoro: per esempio 250.000 al giorno per 2 giorni, o 100.000 al giorno per 5 giorni.
  - La finestra ha sempre un campo libero: lì scrivi il tuo ritmo, per esempio «50.000 al giorno».
- Claude scrive una riga per la macchina con le stime grezze, `QUOTE: essential=100k good=250k max=500k`, e dopo la tua risposta `CHOICE: good` e `PACE: today` (o `PACE: daily=100k`). Le righe per la macchina sono sempre in inglese; la spiegazione Claude te la dà nella tua lingua. Se un lavoro dura più di una risposta, ogni risposta non finita chiude con `JOB: CONTINUES`, e il costo delle risposte dopo si somma.
- **Alla fine di ogni risposta** (hook `Stop`), Quotient legge il file della conversazione e somma il costo di quella risposta. Ogni chiamata si conta **una volta sola**: il file ripete la stessa chiamata una volta per ogni pezzo, e contando tutte le righe il risultato verrebbe doppio.

### L'unità: i token pesati

Il costo è in **token pesati**: token di ingresso equivalenti, con le proporzioni dei prezzi delle API di Anthropic.

| Parte della chiamata | Peso |
|---|---|
| ingresso | 1 |
| scrittura in cache, 5 minuti | 1,25 |
| scrittura in cache, 1 ora | 2 |
| lettura dalla cache | 0,1 |
| uscita | 5 |

La percentuale del limite dell'abbonamento non c'è nei file di Claude Code, quindi Quotient non dice di saperla. I token pesati si muovono insieme a lei, e permettono di confrontare un lavoro con un altro.

Una cosa che i numeri mostrano subito: a ogni chiamata il modello rilegge tutta la conversazione. In una conversazione da 400.000 token sono circa 40.000 token pesati a chiamata, prima ancora che Claude scriva una parola. Le conversazioni lunghe costano più di quanto sembra.

## La settimana: tutti i lavori a rate insieme

Ogni lavoro da solo può stare nella settimana, mentre due o tre insieme no. Quotient somma le rate di tutti i lavori attivi fino all'azzeramento del limite settimanale e le confronta con quello che resta, tolta una **riserva per l'uso normale** (20% di partenza, `config week.reserve_percent 25` per cambiarla).

```
python scripts/quotient.py rate week               # ogni lavoro attivo, il totale, e se ci sta
python scripts/quotient.py rate pause libro        # le sue rate programmate lo saltano
python scripts/quotient.py rate resume libro
python scripts/quotient.py rate set libro --daily 150000   # rallentarlo: rate più piccole
```

- Quando i lavori non ci stanno più, la prossima volta che scrivi si apre una finestra: quali lavori tenere, rallentare o mettere in pausa. Lo chiede una volta per ogni situazione nuova.
- Prima di creare un lavoro nuovo, Claude controlla la settimana e, se non ci starebbe, te lo dice nella finestra.
- Una rata non entra mai nella riserva: se la settimana è corta la rata si accorcia, e se non resta quasi niente aspetta.

La percentuale della settimana ha bisogno della stima di quanto vale l'1% (vedi sotto): finché Quotient non ha qualche giorno di letture, il piano si vede solo in token pesati.

## Il PC lavora mentre non ci sei

Su Windows, una rata programmata **sveglia il PC dalla sospensione o dall'ibernazione**, lavora e, se l'hai scelto, **lo rimette a dormire**, ma solo se nessuno ha usato tastiera o mouse negli ultimi 10 minuti: se stai usando il PC, resta acceso. Mentre la rata lavora, Windows non può rimettersi a dormire a metà. Se all'ora prevista il PC era spento, la rata parte appena si riaccende.

```
python scripts/quotient.py rate check                   # questo PC si può svegliare con un timer?
python scripts/quotient.py rate after libro sleep       # dopo ogni rata: sleep (sospensione) | hibernate | nothing
```

Limiti: un timer sveglia il PC dalla sospensione o dall'ibernazione, non da spento del tutto. Windows deve permettere i timer di riattivazione (Opzioni risparmio energia > Sospensione > Consenti timer di riattivazione); `rate check` legge l'impostazione e dice come attivarla, ma Quotient non la cambia mai al posto tuo. Le attività programmate chiamano un piccolo lanciatore in `~/.quotient`, così continuano a funzionare dopo gli aggiornamenti del plugin. Due rate dello stesso lavoro non partono mai insieme.

## I limiti del piano: quanto hai usato, quanto resta, quanto vale l'1%

Con un abbonamento Pro o Max, Claude Code passa alla riga di stato la percentuale usata del limite delle 5 ore e di quello settimanale, e quando si azzerano. Quotient registra queste letture e le mostra nella riga di stato:

```
Quotient · 5 ore: usato 31%, resta 69%, si azzera 19:30 · settimana: usato 6%, resta 94%, si azzera lun 12 07:00
```

Per attivarla: `python scripts/quotient.py setup-statusline` mostra l'impostazione da aggiungere, e con `--write` la aggiunge a `~/.claude/settings.json` (solo se non hai già una riga di stato). Dove la riga di stato non c'è, Claude può leggere i limiti da solo (nell'app desktop di Claude ha uno strumento apposta) e scrivere una riga `LIMITS:`, che Quotient registra allo stesso modo.

Dalle letture e dai costi che misura, Quotient stima **quanti token pesati vale l'1% di ogni limite**, così un preventivo può dire «questo livello prende circa l'8% della tua settimana, resterebbe l'86%». Anthropic non pubblica i limiti in token: è una stima, con il suo margine (in alcune fonti le percentuali sono numeri interi, quindi ogni finestra aggiunge fino a un punto di errore), e l'uso fuori dalle sessioni di Quotient (per esempio le chat su claude.ai) fa sembrare i limiti più piccoli di quanto sono.

Il resoconto elenca le settimane: la quota più alta del limite settimanale usata in ognuna, e i token pesati misurati. Se le settimane si stanno alleggerendo lo dice solo dopo 4 settimane complete: con meno sarebbe rumore.

## Comandi

Nella chat:

| Comando | Cosa fa |
|---|---|
| `/quotient:setup` | configura Quotient, o cambia le sue quattro impostazioni |
| `/quotient:report` | stime contro costi veri, limiti del piano, le settimane |
| `/quotient:rate <job>` | dividi un lavoro grande in rate, con la finestra di scelta |
| `/quotient:help` | questa lista |

Dal terminale, con `python scripts/quotient.py <comando>` (o `sh scripts/run.sh <comando>`):

| Comando | Cosa fa |
|---|---|
| `report` | il resoconto, dal terminale |
| `setup --threshold N --reserve N --lang it\|en --after sleep\|hibernate\|nothing` | salva le quattro impostazioni |
| `config [key [value]]` | mostra tutte le impostazioni, o ne cambia una |
| `export` | solo i numeri dei lavori finiti, da condividere |
| `setup-statusline [--write]` | mostra i limiti del piano nella riga di stato |
| `rate new <job> --dir <folder> --task-file <file> --quote N (--days N \| --daily N)` | crea un lavoro a rate |
| `rate run <job> [--force]` | fa una rata adesso (--force: anche se oggi ne ha già fatta una) |
| `rate once <job> --time HH:MM` | una rata a quell'ora (domani se è passata); sveglia il PC |
| `rate schedule <job> --time HH:MM [--force]` | una rata ogni giorno a quell'ora; sveglia il PC |
| `rate after <job> sleep\|hibernate\|nothing` | cosa fa il PC dopo ogni rata, se nessuno lo usa |
| `rate week` | tutti i lavori attivi contro quello che resta della settimana |
| `rate set <job> --daily N --per-day N --days N` | cambia un lavoro: quanto vale ogni rata, quante al giorno, quante in tutto |
| `rate pause <job> / rate resume <job>` | mette in pausa un lavoro, o lo fa ripartire |
| `rate stop <job>` | ferma un lavoro e toglie i suoi orari |
| `rate status [job]` | rate fatte e token pesati spesi |
| `rate check` | una rata programmata può svegliare il PC, e Claude Code è collegato |

## Le rate

Un lavoro troppo grande per un giorno può andare a pezzi:

```
python scripts/quotient.py rate new libro --dir ~/libro --task-file lavoro.md --quote 500000 --daily 100000   # 5 rate
python scripts/quotient.py rate run libro                     # una rata adesso
python scripts/quotient.py rate schedule libro --time 03:00   # una ogni giorno
python scripts/quotient.py rate status
```

Quando scegli le rate, una seconda finestra ti chiede quando parte la prima (adesso, oggi a un'ora che scrivi tu, o stanotte) e a che ora partono le altre ogni giorno. Quando una rata finisce, la prossima volta che scrivi si apre una finestra: far partire la prossima subito (consuma altro limite di oggi, a tuo rischio), a un'ora che scegli oggi, o all'ora solita. Ogni scelta ha il campo libero: il piano lo decidi tu.

```
python scripts/quotient.py rate once libro --time 15:30   # un'altra rata oggi a quell'ora
python scripts/quotient.py rate run libro --force          # un'altra rata adesso
python scripts/quotient.py rate stop libro                 # ferma il lavoro e i suoi orari
```

Ogni rata è un'esecuzione nuova di Claude Code senza finestra (`claude -p`) nella cartella del lavoro. Legge la descrizione del lavoro e un file di consegna (cosa è fatto, cosa resta, da dove si riprende), lavora, e aggiorna la consegna dopo ogni passo. Quando il tetto del giorno è speso, un hook rifiuta ogni strumento tranne l'aggiornamento della consegna, così la rata si ferma in ordine invece di essere tagliata a metà. Dopo la prima rata Quotient impara anche quanti dollari Claude Code segna per ogni token pesato, e aggiunge `--max-budget-usd` come freno di sicurezza.

Una rata nuova con una consegna corta rilegge molto meno di una conversazione lunga, quindi le rate potrebbero costare **meno in totale**, non solo meno al giorno. È un'ipotesi: lo dirà il resoconto.

Limiti: il lavoro deve essere divisibile (un romanzo a capitoli sì; una revisione che deve vedere tutto il testo insieme, meno). Le rate partono con `--permission-mode acceptEdits` e non possono rispondere alle richieste di permesso: i comandi che servono vanno permessi nelle impostazioni. Su Windows `rate schedule` crea un'attività nell'Utilità di pianificazione; su macOS e Linux scrive la riga da aggiungere a `crontab`.

## I tuoi dati

Tutto resta in `~/.quotient/` (o in `QUOTIENT_HOME`): le impostazioni, i preventivi, i costi misurati. Quotient non manda niente a nessuno. `export` scrive solo numeri (data, numero di scelte, livello scelto, stima, costo vero, turni): niente testi, niente percorsi, niente codici delle sessioni.

## Imparare tutti insieme (non ancora attivo)

Con i dati di una persona sola il fattore di correzione ha bisogno di qualche lavoro prima di voler dire qualcosa (circa cinque, una stima da controllare con l'uso). I numeri di tante persone messi insieme aiuterebbero chi comincia a partire dalla media di tutti. Il piano: chi vuole manda a questo progetto quello che scrive `export`, e il plugin propone il fattore comune come punto di partenza. Finché nessuno manda numeri, non c'è niente da mettere insieme.

## Limiti, detti chiari

- Le prime stime saranno poco precise. Uno studio del 2026 ha chiesto a dei modelli di IA di prevedere il proprio costo prima di lavori di programmazione: otto modelli, correlazione con il costo vero al massimo 0,39, e stime sistematicamente troppo basse ([Bai e altri, arXiv:2604.22750](https://arxiv.org/abs/2604.22750)). Quotient non rende il modello più bravo a indovinare: misura l'errore e corregge la stima successiva.
- La correzione è un fattore solo: la mediana del rapporto fra costo vero e stima negli ultimi 20 lavori. Se i tuoi lavori sono molto diversi fra loro, l'errore resta grande.
- Dipende dal fatto che Claude scriva le righe `QUOTE:` e `CHOICE:`. Se se ne dimentica, quel lavoro non viene misurato.
- Anthropic potrebbe aggiungere una funzione simile dentro Claude Code. Andrebbe bene così.

## Prove

```
python -m unittest discover -s tests
```

## Autore

Francesco Candela (Korvonordico). L'idea, la soglia, l'imparare dagli errori e le rate sono sue; il codice è scritto insieme a Claude.

## Licenza

MIT
