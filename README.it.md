# Quotient: preventivi dei token e limiti di utilizzo per Claude Code

*[Read in English](README.md)*

**Sapere quanto costa un lavoro dell'IA prima di cominciarlo, e non perdere più una settimana per il limite di utilizzo.** Un plugin per [Claude Code](https://code.claude.com).

Oggi un lavoro con l'IA funziona come un meccanico che ti ripara la macchina senza dirti il prezzo: lo scopri alla cassa. Con un abbonamento la cassa è il limite di utilizzo, e un solo lavoro grande può consumare una settimana intera. Quotient ti dà prima il prezzo, ti fa scegliere, misura quanto è costato davvero e impara dalla differenza.

Il nome tiene insieme le due metà: comincia come *quote*, che in inglese vuol dire preventivo, e in matematica il *quotient* è il quoziente, il risultato di una divisione, come un lavoro grande diviso in rate.

## Cosa sa fare

- **Il preventivo prima di un lavoro grande**, in una finestra di scelta: *essenziale*, *buono* o *massimo*, ognuno con quello che comprende e il suo costo stimato.
- **Il ritmo lo scegli tu**: tutto oggi, oppure a rate, una al giorno, con la quantità al giorno. Oppure il ritmo che scrivi tu.
- **Il costo vero, dopo**, letto dai file di Claude Code e messo accanto alla stima.
- **Il lavoro separato dalla rilettura della chat**: a ogni passo Claude rilegge tutto quello che la chat contiene. Quotient lo misura a parte, così la stima riguarda il lavoro e la finestra mostra lavoro + rilettura = totale. In una chat lunga ti dice quanto risparmieresti in una chat nuova, e il lavoro si può fare lì (vedi [Lavoro e rilettura](#lavoro-e-rilettura-perché-una-chat-lunga-costa-di-più)).
- **Un lavoro può passare da una chat all'altra**: scelto in una chat e fatto in una nuova, oppure lasciato aperto in una e finito in un'altra, viene misurato lo stesso come un lavoro solo.
- **Impara dai suoi errori**: ogni preventivo viene corretto in base a quanto hanno sbagliato quelli di prima. Non parti da zero: finché non hai 5 lavori tuoi, parte dalla media condivisa dei lavori veri di tutti (solo numeri, vedi sotto).
- **Le rate lavorano mentre non ci sei**: il PC si sveglia, fa il pezzo del giorno e torna a dormire. Quando torni, una notifica e il resoconto nella chat del lavoro ti dicono cosa ha fatto (vedi sotto).
- **La settimana tutta insieme**: più lavori insieme non mangiano mai la parte di settimana che tieni per te.
- **I tuoi limiti sotto gli occhi**: quanto hai usato del limite delle 5 ore e di quello settimanale, e quanto resta. Se il ritmo di questa settimana arriverebbe al limite prima dell'azzeramento, Quotient te lo dice una volta, con quanto al giorno basterebbe.
- **Il suo peso, misurato**: il testo che Quotient aggiunge a una chat e le azioni che chiede vengono contati, così vedi quanto costa accanto a quanto aiuta.
- **Una pagina con i grafici**: `/quotient:report page` apre il resoconto nel browser (un file sul tuo PC, niente caricato da internet).
- **Modi di lavorare pronti** per i lavori lunghi a rate: un libro, una ricerca, una revisione di codice (`rate templates`).
- **Privato**: tutto resta sul tuo computer, tranne una riga di numeri per ogni lavoro finito, per la media condivisa, che puoi spegnere (vedi [Cosa viene condiviso](#cosa-viene-condiviso)).

## Installazione

In Claude Code:

```
/plugin marketplace add Korvonordico/quotient-claude-tokens
/plugin install quotient@quotient
```

Serve Python 3.8 o più recente e `sh` (su Windows arriva con Git for Windows, che Claude Code usa già).

La prima volta una finestra chiede quattro impostazioni: da che grandezza un lavoro riceve il preventivo, quanta parte della settimana tenere per te, la lingua, e se Quotient può svegliare il PC per le rate e rimetterlo a dormire. Le cambi quando vuoi con `/quotient:setup`. Poi una seconda finestra ti chiede se vuoi partecipare alla media condivisa, che aiuta il programma (sì, no, o quello che scrivi tu).

## Come va un lavoro grande

1. Chiedi una cosa grande, oppure dici «è un lavoro grosso».
2. Claude non comincia. Si apre una finestra con due domande:
   - **Livello**: essenziale, buono o massimo, con la stima di ognuno. Per un lavoro da circa 500.000 token: massimo 500.000, buono 250.000, essenziale 100.000.
   - **Ritmo**: tutto oggi, oppure per esempio «2 giorni, circa 250.000 al giorno» o «5 giorni, circa 100.000 al giorno». Nel campo libero scrivi il tuo, come «50.000 al giorno».
3. Se scegli **tutto oggi**, Claude fa il lavoro e Quotient misura quanto è costato davvero.
4. Se scegli **le rate**, una seconda finestra ti chiede quando parte la prima e a che ora partono le altre.

Le stime non sono garantite: all'inizio possono sbagliare parecchio. Si avvicinano al vero a ogni lavoro finito.

Se una risposta costa più della soglia e non ha avuto un preventivo, Quotient te lo dice una volta, in una riga, e la conta nel resoconto.

## Lavoro e rilettura: perché una chat lunga costa di più

A ogni passo (ogni chiamata al modello) Claude rilegge tutto quello che la chat contiene: il sistema, gli strumenti, le tue regole, la conversazione fin lì. Ogni token riletto costa poco (un decimo di uno nuovo, grazie alla cache), ma si somma. In una chat che parte da 165.000 token, ogni passo costa circa 16.500 token pesati prima ancora di lavorare; un lavoro da 100 passi, circa 1,65 milioni. Un modello che stima un lavoro pensa al lavoro, non a questo.

Per questo Quotient divide in due ogni lavoro che misura:

- **lavoro**: i passi del lavoro stesso. La stima riguarda questo, e la correzione si impara da qui.
- **rilettura**: quello che la chat conteneva già quando il lavoro è cominciato, riletto a ogni passo. Quotient la misura, e in un preventivo la aggiunge dalla grandezza della chat adesso e dai passi che il lavoro richiederà.

Un caso vero, 6 ottobre 2026: un lavoro è costato 4,67 milioni di token pesati, di cui 2,82 milioni di lavoro e 1,85 milioni per rileggere i 165.000 token con cui la chat era partita, in 107 passi.

Quando una chat è diventata lunga, la finestra propone anche di fare il lavoro **in una chat nuova**, e dice quanto si risparmia. Apri una chat nuova e chiedi di continuare: Quotient dice alla chat nuova che c'è un lavoro che aspetta, e lo misura lì.

## Le rate: il PC lavora mentre non ci sei

Lasci il PC **in sospensione o in ibernazione**, come fai sempre. Ogni rata poi va così:

1. **All'ora che hai scelto** (per esempio le 3 di notte), Windows sveglia il PC.
2. **Quotient avvia Claude Code** in sottofondo, senza aprire l'app. Claude legge il lavoro e una breve nota su dove si era fermato l'ultima volta.
3. **Claude lavora sul pezzo successivo** finché arriva alla quantità di quel giorno. Poi scrive dove si è fermato e si ferma in ordine.
4. **Se nessuno sta usando il PC** (tastiera e mouse fermi da 10 minuti), Quotient **lo rimette in sospensione**, o in ibernazione se hai scelto così. Se lo stai usando, resta acceso.
5. **Il giorno dopo, alla stessa ora, ricomincia**, finché il lavoro è finito. Poi l'orario si cancella da solo.

**Quando torni lo vedi subito.** Per ogni rata Windows mostra una notifica, che resta nel centro notifiche. Il resoconto completo ti aspetta nella chat in cui hai creato il lavoro e compare al tuo primo messaggio lì: quale rata, quando, quanto è costata rispetto alla quantità del giorno e alla settimana, cosa ha fatto, cosa manca e quando parte la prossima. Le altre chat te lo dicono una volta sola, e una seconda volta non prima di un giorno dopo; poi tacciono. Se vuoi i resoconti in un'altra chat, chiedilo a Claude lì (`rate here <lavoro>`).

Da sapere:
- Se preferisci che Quotient non tocchi mai il PC, lo scegli nella configurazione: le rate allora partono solo con il PC già acceso.
- Un timer può svegliare un PC **in sospensione o in ibernazione, non uno spento del tutto**. Se il PC era spento, la rata parte appena lo accendi.
- Windows deve permettere i timer di riattivazione. `rate check` ti dice se è così, e come attivarli.
- Se usi l'app desktop di Claude, fai una volta il login di Claude Code in un terminale (`claude auth login`): le rate girano fuori dall'app.
- Puoi far partire una rata in più lo stesso giorno, se accetti che consumi altro limite di quel giorno.
- Il risveglio e la sospensione funzionano su Windows. Su macOS e Linux Quotient ti dà la riga per programmarlo tu.

## La settimana: tutti i lavori insieme

Due o tre lavori possono stare ognuno nella settimana e non starci insieme. Quotient somma tutte le rate previste fino all'azzeramento del limite settimanale e tiene una riserva per il tuo uso normale (il 20%, se non la cambi). Se il piano non ci sta, una finestra ti chiede quali lavori tenere, rallentare o mettere in pausa. Una rata non entra mai nella riserva: si accorcia, o aspetta.

## I tuoi limiti

Quotient registra quanto hai usato del limite delle 5 ore e di quello settimanale e quando si azzerano, e può mostrarlo nella riga di stato di Claude Code:

```
Quotient · 5 ore: usato 31%, resta 69%, si azzera 19:30 · settimana: usato 6%, resta 94%, si azzera lun 12 07:00
```

Col tempo stima anche quanti token vale l'1% di ogni limite, così un preventivo può dire «questo prende circa l'8% della tua settimana». Anthropic non pubblica i limiti in token, quindi è una stima, con il suo margine.

## Cosa viene condiviso

Ogni copia di Quotient impara dai suoi errori, ma chi comincia non ne ha ancora. Allora le copie mettono insieme i loro numeri: dopo ogni lavoro finito, Quotient manda **una riga di numeri, esattamente questa e nient'altro**:

```json
{"v":1,"q":"0.9.5","family":"opus","estimate":225000,"actual":259000}
```

Il formato, la versione di Quotient, la famiglia del modello (opus, sonnet, haiku, fable o altro), la stima grezza e il costo vero del lavoro in token pesati (dalla 0.9.5 senza la rilettura della chat, che la stima non riguarda), arrotondati a 3 cifre. **Niente date, nomi, testi, percorsi, codici di sessione o di persona.** La riga parte all'inizio della chat successiva, mai a metà di una risposta, e niente parte prima che Claude Code ti abbia mostrato un messaggio che lo dice.

- Un piccolo servizio ([codice in `server/`](server/)) raccoglie le righe. Non tiene gli indirizzi IP: il suo codice non li legge e il registro delle richieste è spento.
- Al massimo una volta a settimana, dopo almeno 20 lavori nuovi e mai sotto i 30 in tutto, pubblica la media in un progetto tutto suo, [quotient-data](https://github.com/Korvonordico/quotient-data) (la chiave del servizio può scrivere solo lì, mai in questo programma). Ogni copia di Quotient scarica quel file una volta al giorno e lo usa solo fra x0,25 e x4: chiunque può mandare numeri, quindi è una media «al meglio».
- **Scegli tu**: la finestra del primo uso ti chiede se partecipi (di serie sì). Puoi cambiarlo quando vuoi: `/quotient:share off`, l'impostazione del plugin *Condividi numeri anonimi*, oppure `QUOTIENT_SHARE=0`. **Anche da spento ricevi la media condivisa.**
- `/quotient:share` ti mostra esattamente cosa parte e quante righe aspettano di partire.

Tutto nel dettaglio: [PRIVACY.md](PRIVACY.md).

## Cosa Quotient fa partire, manda e scarica

Tutto, così niente è una sorpresa:

- **Sul tuo computer, sempre**: il suo programma in Python, tramite `sh`, all'inizio di ogni chat, a ogni messaggio, alla fine di ogni risposta e prima di ogni strumento dentro una rata. Legge le trascrizioni delle tue chat che tiene Claude Code solo per dei numeri: i token di ogni chiamata, le righe per la macchina che scrive Claude, e quali strumenti Claude ha usato (per misurare il costo e il peso di Quotient stesso). Nessun testo di quelle chat viene mai mandato da nessuna parte.
- **Scrive** solo in `~/.quotient/` (o in `QUOTIENT_HOME`). L'unica eccezione è `setup-statusline --write`, che mette la riga di stato in `~/.claude/settings.json`, e solo quando lo lanci tu.
- **Per le rate, solo dopo che le hai scelte nella finestra**: attività dell'Utilità di pianificazione di Windows (`schtasks`) che partono all'ora che hai scelto e, se lo permetti, svegliano il PC; Claude Code stesso (`claude -p`) nella cartella del lavoro, con la modalità di permessi `acceptEdits`, senza richieste di permesso, e solo con gli strumenti che permetti in `rate.extra_args`; PowerShell per la notifica e per leggere quando parte la prossima rata; la sospensione o l'ibernazione dopo, se l'hai scelto e nessuno sta usando il PC. `rate check` legge (non cambia mai) l'impostazione dei timer di riattivazione con `powercfg`.
- **Manda**, se la condivisione è accesa: una riga di numeri per ogni lavoro finito a `https://quotient-share.korvonordico.workers.dev` (vedi [Cosa viene condiviso](#cosa-viene-condiviso)).
- **Scarica**, una volta al giorno: `https://raw.githubusercontent.com/Korvonordico/quotient-data/main/average.json`, oppure `/v1/average` del servizio quando GitHub non risponde. Tutti e due sono dell'autore.
- **La pagina con i grafici** è un file in `~/.quotient/report.html`, aperto nel tuo browser; non carica niente da internet.

## Comandi

Nella chat:

| Comando | Cosa fa |
|---|---|
| `/quotient:setup` | configura Quotient, o cambia le sue impostazioni |
| `/quotient:report` | stime contro costi veri, i tuoi limiti, le settimane; `/quotient:report page` lo apre come pagina con i grafici |
| `/quotient:rate <lavoro>` | dividi un lavoro grande in rate |
| `/quotient:share [on\|off]` | la media condivisa: cosa parte esattamente, e accenderla o spegnerla |
| `/quotient:help` | tutti i comandi, con quello che fanno |

Gli altri comandi li usa Claude per te quando scegli nelle finestre. `/quotient:help` li elenca tutti (`rate week`, `rate pause`, `rate check` e gli altri).

## Limiti, detti chiari

- Le prime stime saranno poco precise. Uno studio del 2026 ha chiesto a dei modelli di IA di prevedere il proprio costo prima di lavori di programmazione: otto modelli, correlazione con il costo vero al massimo 0,39, e stime sistematicamente troppo basse ([Bai e altri, arXiv:2604.22750](https://arxiv.org/abs/2604.22750)). Quotient non rende il modello più bravo a indovinare: misura l'errore e corregge la stima dopo.
- Dipende dal fatto che Claude segua le regole che Quotient gli dà. Se un preventivo salta, quel lavoro non viene misurato (una risposta grande senza preventivo viene contata e detta una volta).
- Anche Quotient ha un peso: le sue regole all'inizio di una chat (circa 1.700 token) e una riga a ogni messaggio (circa 270 token in una chat lunga), che restano nella chat e vengono rilette. Quotient misura questo peso e lo mostra nel resoconto, con i token contati dai caratteri (una stima).
- La parte di rilettura di un preventivo presume che la cache funzioni. Dopo una pausa più lunga di quanto dura la cache, la chat viene scritta di nuovo a un prezzo più alto: questo si misura dopo, non si prevede.
- Quanto Quotient fa risparmiare non si può misurare, perché un lavoro non fatto non ha un costo. Il resoconto dà una stima (per esempio quanto hanno evitato le scelte sotto il massimo) e dice che è una stima.
- Anthropic potrebbe aggiungere una funzione simile dentro Claude Code. Andrebbe bene così.

<details>
<summary>Dettagli tecnici</summary>

**L'unità.** I costi sono in token pesati: token di ingresso equivalenti, con le proporzioni dei prezzi delle API di Anthropic (ingresso 1, scrittura in cache 1,25 per 5 minuti o 2 per un'ora, lettura dalla cache 0,1, uscita 5). In una prova dal vivo il costo in dollari segnato da Claude Code era esattamente i token pesati per il prezzo di ingresso del modello.

**Come si aggancia.** All'inizio di una chat Quotient dà a Claude le sue regole una volta sola (circa 5.900 caratteri, più o meno 1.700 token); a ogni messaggio, una riga corta (circa 940 caratteri in una chat lunga, più o meno 270 token, con la CHAT PART: quanto aggiunge rileggere questa chat). Claude scrive delle righe per la macchina (`QUOTE:`, `CHOICE:`, `PACE:` con `today`, `new chat` o un piano, `JOB: CONTINUES`, `JOB: RESUME|CLOSE|DROP <codice>` per un lavoro di un'altra chat, `LIMITS:`) nell'ultimo messaggio di una risposta; Quotient le legge alla fine della risposta, sommando il suo costo e contando ogni chiamata una volta sola.

**Lavoro e rilettura, esattamente.** Il testo che una chiamata manda al modello viene letto prima dalla cache, poi scritto nella cache, poi mandato come ingresso normale. Per ogni chiamata, la parte che la chat conteneva quando il lavoro è cominciato (dalla posizione 0 alla grandezza della prima chiamata del lavoro) si paga con quei pesi: è la rilettura; il resto del costo è il lavoro. Una chiamata dopo una compattazione, che è più corta, non aggiunge chat vecchia. I lavori misurati prima della 0.9.5 ricevono la loro divisione una volta sola dalla trascrizione della loro chat, se esiste ancora. I passi che un preventivo richiederà sono il suo lavoro corretto diviso il lavoro per passo imparato dai lavori finiti (30.000 token pesati finché non ce ne sono 3).

**Le rate.** Ognuna è un'esecuzione senza finestra (`claude -p`) nella cartella del lavoro, avviata dall'Utilità di pianificazione di Windows tramite un piccolo lanciatore in `~/.quotient`, così continua a funzionare dopo gli aggiornamenti del plugin. Un hook rifiuta ogni strumento tranne l'aggiornamento della consegna quando quello che è stato speso più i due passi successivi (la grandezza delle ultime chiamate, al massimo il 40% del tetto) arriverebbe al tetto del giorno, così i passi che chiudono la rata ci stanno dentro. Ogni rata tiene nella consegna una riga `PROGRESS: <n>%`; da lì Quotient dice quanto manca e quante rate. Il tetto del giorno comprende la rilettura dell'inizio di ogni rata, imparata dalle rate prima. Due rate dello stesso lavoro non partono mai insieme. Il lavoro ricorda la chat che l'ha creato (Claude Code passa il codice della chat ai comandi; se non lo fa, Quotient lo prende alla fine della risposta). La notifica usa il sistema di notifiche di Windows tramite PowerShell (su macOS `osascript`, su Linux `notify-send`) e non scrive file; `config rate.notify false` la spegne.

**I tuoi dati.** Tutto sta in `~/.quotient/` (o in `QUOTIENT_HOME`). `export` scrive le righe esatte che la condivisione manda. Le righe in attesa sono in `share-outbox.jsonl`; la media scaricata è `average.json`; i lavori aperti in una chat sono in `chat-jobs.json` (dimenticati dopo 7 giorni); la pagina con i grafici è `report.html`.

**La media condivisa.** Finché non hai 5 lavori tuoi, la media condivisa conta come 5 lavori al suo fattore (quello della tua famiglia di modello se ne ha almeno 5, se no quello di tutti), accanto ai tuoi. Dal quinto lavoro tuo in poi contano solo i tuoi.

**Prove.** `python -m unittest discover -s tests` (Quotient, senza internet) e `node --test server/test/stats.test.mjs` (i numeri del servizio). GitHub le lancia tutte e due a ogni salvataggio, su Windows e su Ubuntu.

</details>

## Autore

Francesco Candela (Korvonordico). L'idea, la soglia, l'imparare dagli errori, le rate e il bilancio della settimana sono sue; il codice è scritto insieme a Claude.

## Licenza

MIT
