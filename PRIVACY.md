# Privacy

*Italiano più sotto.*

Quotient is a Claude Code plugin by Francesco Candela (Korvonordico). It runs on your computer. This page says exactly what leaves it.

## What stays on your computer

Everything Quotient records: your quotes, the real costs, your limits, your settings, your installment jobs, the jobs left open in a chat, and the page with charts (`report.html`). They are in `~/.quotient/` (or `QUOTIENT_HOME`). To measure costs, Quotient reads from Claude Code's transcripts only numbers (the token counts of each call), the machine lines Claude writes and the names of the tools Claude called; it never sends their text anywhere, and never reads your files, memory or chat history for sharing.

An installment job also remembers which chat created it (the chat's id), so each installment's report comes back there; to tell you where the report waits, Quotient reads that chat's title from Claude Code's files on your computer. The notification at the end of an installment is shown by your own system (on Windows it stays in the notification center). None of this leaves your computer.

## What is shared, and why

To help everyone start from real numbers instead of from zero, Quotient shares **one line of numbers for each finished job**. Exactly this, and nothing else:

```json
{"v":1,"q":"0.9.5","family":"opus","estimate":225000,"actual":259000}
```

| Field | What it is |
|---|---|
| `v` | the format of the line |
| `q` | the Quotient version |
| `family` | the model family that did most of the job: opus, sonnet, haiku, fable or other |
| `estimate` | the raw estimate, in weighted tokens, rounded to 3 significant digits |
| `actual` | the real cost of the work, in weighted tokens, rounded to 3 significant digits (from 0.9.5 without re-reading what the chat held when the job started, which the estimate is not about; the version in `q` tells the two apart) |

No date or time, no names, no text, no file paths, no session or user ids, no account. `quotient export` prints the lines your jobs produce; `/quotient:share` shows the state, the exact form of the line and how many lines are waiting.

**When**: the line waits on your computer and leaves at the start of your next Claude Code session (or at the end of a background installment), never in the middle of a reply. Nothing is queued before you have been told: the first time, Claude Code shows you a message saying what is shared and how to turn it off.

**Where**: to a small service run on Cloudflare Workers by the author, whose code is public in [`server/`](server/). It accepts only lines of exactly that shape; anything else is refused.

**You choose, and you can change it any time**: the first-use window asks whether you take part (yes by default). To change it: `/quotient:share off`, `quotient share off`, the plugin setting *Share anonymous numbers*, or the environment variable `QUOTIENT_SHARE=0`. When it is off nothing is sent, and lines that were waiting are deleted. **You still download and use the shared average.** Installments that run in the background read the setting from Quotient's own file, so `/quotient:share off` covers them; the environment variable covers them only if it is set in Windows itself.

## What the service keeps

- The five fields above, in a database, in order of arrival: no date, no address. Only the most recent 5,000 lines are kept.
- Two global counters for everybody together, one for the current minute and one for the current day, used only to refuse floods. They are overwritten when the minute or the day changes, so no history of arrival times is kept.
- The last average.

It **does not keep your IP address**: its code never reads it, and request logging is turned off (Cloudflare turns it on by default for new services; here it is off, see `server/wrangler.toml`). Cloudflare, which runs the service, carries the connection like any network provider does; its own handling is described in [Cloudflare's privacy policy](https://www.cloudflare.com/privacypolicy/). Cloudflare also keeps automatic restore points of the database for a limited time (D1 Time Travel), from which the person running the service could in principle tell roughly when a line arrived.

## What is published

At most once a week, and only after at least 20 new jobs, the service computes the average (the median of real cost / estimate, for each model family and for all jobs, rounded to 2 decimals) and publishes it as `average.json` in a separate repository, [Korvonordico/quotient-data](https://github.com/Korvonordico/quotient-data), which holds only that file: the service's key can write there and nowhere else, never in Quotient's code. Nothing is published below 30 jobs, in all or for a family. So someone who only watches the file cannot tell a single job apart. The limit, said plainly: the service does not know who sends what, so someone who deliberately sends false lines could learn roughly on which side of the average one real job falls; never whose it is.

It is a best-effort average: anyone can send numbers. The service refuses ratios beyond x10 either way and sudden jumps backed by few jobs, and every copy of Quotient uses the average only between x0.25 and x4, and only until you have 5 jobs of your own.

## What is downloaded

Once a day, at the start of a session, Quotient downloads `average.json` from the quotient-data repository on GitHub (`raw.githubusercontent.com`), or, if GitHub does not answer, the same file from the service. As with any download, GitHub or Cloudflare see the connection. Nothing else is sent with it, and only its numbers are kept. To stop the download too: `quotient config share.average_url ""` and `quotient config share.endpoint ""`.

## How long

Only the most recent 5,000 lines are kept; the average uses the most recent 500 jobs per family and 2,000 in all. Because the lines carry nothing that points to a person, they cannot be found and deleted one by one; if you want sharing to stop, turn it off.

## Contact

Open an issue at https://github.com/Korvonordico/quotient-claude-tokens/issues.

---

# Privacy (italiano)

Quotient è un plugin per Claude Code di Francesco Candela (Korvonordico). Gira sul tuo computer. Questa pagina dice esattamente cosa ne esce.

**Resta sul tuo computer** tutto quello che Quotient registra: preventivi, costi veri, limiti, impostazioni, lavori a rate, lavori lasciati aperti in una chat e la pagina con i grafici (`report.html`), in `~/.quotient/`. Per misurare i costi Quotient legge dalle trascrizioni di Claude Code solo numeri (i token di ogni chiamata), le righe per la macchina che scrive Claude e i nomi degli strumenti usati; non manda mai il testo delle conversazioni, i tuoi file, la memoria o la cronologia.

Un lavoro a rate ricorda anche quale chat l'ha creato (il codice della chat), così il resoconto di ogni rata torna lì; per dirti dove ti aspetta, Quotient legge il titolo di quella chat dai file di Claude Code sul tuo computer. La notifica alla fine di una rata la mostra il tuo sistema (su Windows resta nel centro notifiche). Niente di tutto questo esce dal tuo computer.

**Cosa viene condiviso**: una riga di numeri per ogni lavoro finito, esattamente questa e nient'altro:

```json
{"v":1,"q":"0.9.5","family":"opus","estimate":225000,"actual":259000}
```

Il formato, la versione di Quotient, la famiglia del modello, la stima grezza e il costo vero del lavoro in token pesati (dalla 0.9.5 senza la rilettura di quello che la chat conteneva quando il lavoro è cominciato, che la stima non riguarda), arrotondati a 3 cifre. Niente date né orari, niente nomi, testi, percorsi, codici di sessione o di persona, niente account. La riga parte all'inizio della sessione successiva, mai a metà di una risposta, e niente parte prima che tu sia avvisato: la prima volta Claude Code ti mostra un messaggio che dice cosa viene condiviso e come spegnerlo. Va a un piccolo servizio su Cloudflare Workers, il cui codice è pubblico in [`server/`](server/), che accetta solo righe di quella forma.

**Scegli tu, e puoi cambiare idea quando vuoi**: la finestra del primo uso ti chiede se partecipi (di serie sì). Per cambiarlo: `/quotient:share off`, l'impostazione del plugin *Condividi numeri anonimi*, oppure `QUOTIENT_SHARE=0`. Da spento non parte niente, e le righe in attesa vengono cancellate. **La media condivisa la scarichi e la usi lo stesso.**

**Il servizio non tiene il tuo indirizzo IP**: il suo codice non lo legge, e il registro delle richieste è spento (Cloudflare lo accende di serie nei servizi nuovi; qui è spento). Cloudflare, che fa girare il servizio, trasporta la connessione come ogni rete: vedi la [sua informativa](https://www.cloudflare.com/privacypolicy/). Due contatori, uno per il minuto e uno per il giorno in corso, servono solo a fermare le inondazioni e vengono sovrascritti: nessuna storia degli orari d'arrivo. Cloudflare tiene anche dei punti di ripristino automatici del database per un tempo limitato, dai quali chi gestisce il servizio potrebbe in teoria capire più o meno quando è arrivata una riga.

**Cosa viene pubblicato**: al massimo una volta a settimana, e solo dopo almeno 20 lavori nuovi, la media (mediana di costo vero / stima, per famiglia di modello e in tutto, arrotondata a 2 decimali) va in `average.json`, in un progetto separato, [Korvonordico/quotient-data](https://github.com/Korvonordico/quotient-data), che contiene solo quel file: la chiave del servizio può scrivere lì e da nessun'altra parte, mai nel programma. Sotto i 30 lavori non si pubblica niente: così chi guarda solo il file non può riconoscere un singolo lavoro. Il limite, detto chiaro: il servizio non sa chi manda cosa, quindi chi manda apposta righe false potrebbe capire più o meno da che parte della media cade un lavoro vero, mai di chi è. È una media «al meglio»: chiunque può mandare numeri; per questo il servizio rifiuta i rapporti oltre x10 e i salti improvvisi con pochi lavori, e Quotient usa la media solo fra x0,25 e x4.

**Cosa viene scaricato**: una volta al giorno, `average.json` da quotient-data su GitHub, o dal servizio se GitHub non risponde. Si tengono solo i numeri. Per fermare anche lo scaricamento: `quotient config share.average_url ""` e `quotient config share.endpoint ""`.

**Per quanto tempo**: si tengono solo le ultime 5.000 righe; la media usa gli ultimi 500 lavori per famiglia e 2.000 in tutto. Le righe non contengono niente che porti a una persona, quindi non si possono ritrovare e cancellare una per una: se vuoi che la condivisione si fermi, spegnila.
