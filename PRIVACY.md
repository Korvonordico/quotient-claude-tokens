# Privacy

*Italiano più sotto.*

Token Quotient (Quotient for short) is a Claude Code plugin by Francesco Candela (Korvonordico). It runs on your computer. This page says exactly what leaves it.

## What stays on your computer

Everything Quotient records: your quotes, the real costs, your limits, your settings, your installment jobs, the jobs left open in a chat, and the page with charts (`report.html`). They are in `~/.quotient/` (or `QUOTIENT_HOME`). To measure costs, Quotient reads from Claude Code's transcripts numbers (the token counts of each call), the machine lines Claude writes and the names of the tools Claude called; it never sends their text anywhere, and never reads your files, memory or chat history for sharing. In a reply that gives a quote it also reads what Claude wrote and the options of the choice window, only to check that each level shows its time and shares (since 1.1.3); it keeps none of it.

An installment job also remembers which chat created it (the chat's id), so each installment's report comes back there; to tell you where the report waits, Quotient reads that chat's title from Claude Code's files on your computer. The notification at the end of an installment is shown by your own system (on Windows it stays in the notification center). None of this leaves your computer.

If you use Hermes Agent, Quotient also reads Hermes' local session store, read-only: the token counters (also those of its calls in the background), the model and the title of each chat. Since 1.1.5, when a reply of Hermes gives a quote, Quotient also reads what Hermes wrote in that reply and the choices of its clarify window, only to check that the quote shows the time and the shares of each level; it keeps none of it. It never reads your messages. This stays on your computer too.

Since 1.1.4, to tell when something around your jobs changes (a plugin installed, for example), Quotient also reads the **names** of the plugins turned on, of the MCP servers and of the hooks, from Claude Code's settings files and from Hermes' `config.yaml`. For a hook it keeps the event and the name of the script it runs. It never keeps their command lines, arguments, settings, keys or other secrets. The names stay in `~/.quotient/` (`env.jsonl` and your jobs) and are not part of the shared line.

Since 1.1.6, Quotient sets its measures against others. These stay on your computer too, as numbers only:

- **Claude Code's own telemetry, only if you turn it on** (`telemetry on`). Claude Code then sends its token and cost counters (OpenTelemetry) to a small receiver of Quotient's on `127.0.0.1:4318`, which only this computer can reach. The receiver keeps tokens by type, cost, model, kind of call, session and time in `~/.quotient/otel.jsonl`, and drops everything else Claude Code attaches (e-mail, account and organization ids). The settings Quotient prints ask Claude Code for metrics only: no events, no prompts, no account id. `telemetry on --write` and `telemetry off --write` change the `env` block of `~/.claude/settings.json`, after a copy of it; without `--write` nothing is written. The receiver stops by itself after 2 hours without data.
- **Hermes' own estimate of each chat's cost**, from the same read-only session store.
- **The cost the status line gets**, if you set the status line up: Claude Code's cost of the session, in `statusline-cost.jsonl`.
- **Your plan** (Pro, Max 5x, Max 20x, other), only if you choose it in the setup window.

## What is shared, and why

To help everyone start from real numbers instead of from zero, Quotient shares **one line of numbers for each finished job**. Exactly this, and nothing else:

```json
{"v":1,"q":"1.2.4","family":"opus","estimate":225000,"actual":259000,"plan":"max5","per_point":3220000,"per_point_5h":322000}
```

| Field | What it is |
|---|---|
| `v` | the format of the line |
| `q` | the Quotient version |
| `family` | the model family that did most of the job: opus, sonnet, haiku, fable or other |
| `estimate` | the raw estimate, in weighted tokens, rounded to 3 significant digits |
| `actual` | the real cost of the work, in weighted tokens, rounded to 3 significant digits (from 0.9.5 without re-reading what the chat held when the job started, which the estimate is not about; the version in `q` tells the two apart) |
| `plan` | from 1.1.6, and only if you chose your plan in Quotient's settings: pro, max5, max20 or other |
| `per_point` | from 1.1.6, and only once Quotient has learned it from your own readings of the limits: how many weighted tokens 1% of your week holds, rounded to 3 significant digits |
| `per_point_5h` | from 1.1.7, the same for the 5-hour window: how many weighted tokens 1% of your 5 hours holds, rounded to 3 significant digits, only once Quotient has learned it from your own readings |

The last three are there so that a new user of the same plan starts from the real size of 1% of the week and of the 5 hours of that plan, instead of from nothing, and so that the limits of each plan are confirmed by other people. What a new user gets is an estimate to start from, taken from other users, with its margin, not a certainty: Anthropic does not publish the limits in tokens and changes them. Without them the line is the five fields, as before.

No date or time, no names, no text, no file paths, no session or user ids, no account. `quotient export` prints the lines your jobs produce; `/token-quotient:share` shows the state, the exact form of the line and how many lines are waiting.

**When**: the line waits on your computer and leaves at the start of your next Claude Code session (or at the end of a background installment), never in the middle of a reply. Nothing is queued before you have been told: the first time, Claude Code shows you a message saying what is shared and how to turn it off.

**Where**: to a small service run on Cloudflare Workers by the author, whose code is public in [`server/`](server/). It accepts only lines of exactly that shape; anything else is refused.

**You choose, and you can change it any time**: the first-use window asks whether you take part (yes by default). To change it: `/token-quotient:share off`, `quotient share off`, the plugin setting *Share anonymous numbers*, or the environment variable `QUOTIENT_SHARE=0`. When it is off nothing is sent, and lines that were waiting are deleted. **You still download and use the shared average.** Installments that run in the background read the setting from Quotient's own file, so `/token-quotient:share off` covers them; the environment variable covers them only if it is set in Windows itself.

## What the service keeps

- The fields above (the five, and `plan`, `per_point` and `per_point_5h` when sent), in a database, in order of arrival: no date, no address. Only the most recent 5,000 lines are kept.
- Two global counters for everybody together, one for the current minute and one for the current day, used only to refuse floods. They are overwritten when the minute or the day changes, so no history of arrival times is kept.
- The last average.

It **does not keep your IP address**: its code never reads it, and request logging is turned off (Cloudflare turns it on by default for new services; here it is off, see `server/wrangler.toml`). Cloudflare, which runs the service, carries the connection like any network provider does; its own handling is described in [Cloudflare's privacy policy](https://www.cloudflare.com/privacypolicy/). Cloudflare also keeps automatic restore points of the database for a limited time (D1 Time Travel), from which the person running the service could in principle tell roughly when a line arrived.

## What is published

At most once a week, and only after at least 20 new jobs, the service computes the average (the median of real cost / estimate, for each model family and for all jobs, rounded to 2 decimals) and publishes it as `average.json` in a separate repository, [Korvonordico/quotient-data](https://github.com/Korvonordico/quotient-data), which holds only that file: the service's key can write there and nowhere else, never in Quotient's code. Nothing is published below 30 jobs, in all or for a family. From 1.1.6 the same file also holds, for each plan with at least 30 jobs that sent both `plan` and `per_point`, the median size of 1% of the week with its middle half, rounded to 3 significant digits; from 1.1.7 the same for the 5 hours, for each plan with at least 30 jobs that sent `plan` and `per_point_5h` (`jobs_5h`, `per_point_5h`, `p25_5h`, `p75_5h`). So someone who only watches the file cannot tell a single job apart. The limit, said plainly: the service does not know who sends what, so someone who deliberately sends false lines could learn roughly on which side of the average one real job falls; never whose it is.

It is a best-effort average: anyone can send numbers. The service refuses ratios beyond x10 either way and sudden jumps backed by few jobs, and every copy of Quotient uses the average only between x0.25 and x4, and only until you have 5 jobs of your own.

## What is downloaded

Once a day, at the start of a session, Quotient downloads `average.json` from the quotient-data repository on GitHub (`raw.githubusercontent.com`), or, if GitHub does not answer, the same file from the service. As with any download, GitHub or Cloudflare see the connection. Nothing else is sent with it, and only its numbers are kept. To stop the download too: `quotient config share.average_url ""` and `quotient config share.endpoint ""`. Only if you run `quotient prices update`, Quotient also downloads a public price table from GitHub; nothing is sent with it.

## What is read from Anthropic

To show your plan limits, Quotient runs Claude Code's own `/usage` command (`claude -p /usage`, without hooks and without saving a session). Claude Code answers it with its own login, as it does when you type `/usage`; Quotient never reads your login or any other credential, and sends nothing itself. It keeps only the used percentages and the reset times. It asks at most every minute (from 1.1.8; before, every 10 minutes, and from 1.1.6 every minute while a job or an installment was open), in the background (always since 1.1.7, so no message waits for it), and spends no tokens. To turn it off: `quotient config limits.live false`.

## How long

Only the most recent 5,000 lines are kept; the average uses the most recent 500 jobs per family and 2,000 in all. Because the lines carry nothing that points to a person, they cannot be found and deleted one by one; if you want sharing to stop, turn it off.

## Contact

Open an issue at https://github.com/Korvonordico/quotient-claude-tokens/issues.

---

# Privacy (italiano)

Token Quotient (in breve Quotient) è un plugin per Claude Code di Francesco Candela (Korvonordico). Gira sul tuo computer. Questa pagina dice esattamente cosa ne esce.

**Resta sul tuo computer** tutto quello che Quotient registra: preventivi, costi veri, limiti, impostazioni, lavori a rate, lavori lasciati aperti in una chat e la pagina con i grafici (`report.html`), in `~/.quotient/`. Per misurare i costi Quotient legge dalle trascrizioni di Claude Code dei numeri (i token di ogni chiamata), le righe per la macchina che scrive Claude e i nomi degli strumenti usati; non manda mai il testo delle conversazioni, i tuoi file, la memoria o la cronologia. In una risposta con un preventivo legge anche quello che ha scritto Claude e le scelte della finestra, solo per controllare che ogni livello abbia il tempo e le quote (dalla 1.1.3); non ne tiene niente.

Un lavoro a rate ricorda anche quale chat l'ha creato (il codice della chat), così il resoconto di ogni rata torna lì; per dirti dove ti aspetta, Quotient legge il titolo di quella chat dai file di Claude Code sul tuo computer. La notifica alla fine di una rata la mostra il tuo sistema (su Windows resta nel centro notifiche). Niente di tutto questo esce dal tuo computer.

Se usi Hermes Agent, Quotient legge anche il suo archivio locale delle sessioni, in sola lettura: i contatori dei token (anche quelli delle sue chiamate in sottofondo), il modello e il titolo di ogni chat. Dalla 1.1.5, quando una risposta di Hermes dà un preventivo, Quotient legge anche quello che Hermes ha scritto in quella risposta e le scelte della sua finestra clarify, solo per controllare che il preventivo mostri il tempo e le quote di ogni livello; non ne tiene niente. Non legge mai i tuoi messaggi. Anche questo resta sul tuo computer.

Dalla 1.1.4, per accorgersi quando cambia qualcosa intorno ai tuoi lavori (per esempio un plugin installato), Quotient legge anche i **nomi** dei plugin accesi, dei server MCP e degli hook, dai file delle impostazioni di Claude Code e dal `config.yaml` di Hermes. Di un hook tiene l'evento e il nome dello script che lancia. Non tiene mai le righe di comando, gli argomenti, le impostazioni, le chiavi o altri segreti. I nomi restano in `~/.quotient/` (`env.jsonl` e i tuoi lavori) e non fanno parte della riga condivisa.

Dalla 1.1.6 Quotient mette le sue misure accanto ad altre. Anche queste restano sul tuo computer, solo numeri:

- **La telemetria di Claude Code, solo se la accendi** (`telemetry on`). Claude Code manda allora i suoi contatori di token e costi (OpenTelemetry) a un piccolo ricevitore di Quotient su `127.0.0.1:4318`, raggiungibile solo da questo computer. Il ricevitore tiene token per tipo, costo, modello, tipo di chiamata, sessione e ora in `~/.quotient/otel.jsonl`, e scarta tutto il resto che Claude Code ci aggiunge (e-mail, codici di account e di organizzazione). Le impostazioni che Quotient stampa chiedono a Claude Code solo le metriche: niente eventi, niente prompt, niente codice di account. `telemetry on --write` e `telemetry off --write` cambiano il blocco `env` di `~/.claude/settings.json`, dopo averne fatto una copia; senza `--write` non si scrive niente. Il ricevitore si ferma da solo dopo 2 ore senza dati.
- **La stima del costo di ogni chat che fa Hermes**, dallo stesso archivio letto in sola lettura.
- **Il costo che riceve la riga di stato**, se l'hai accesa: il costo della sessione secondo Claude Code, in `statusline-cost.jsonl`.
- **Il tuo piano** (Pro, Max 5x, Max 20x, altro), solo se lo scegli nella finestra delle impostazioni.

**Cosa viene condiviso**: una riga di numeri per ogni lavoro finito, esattamente questa e nient'altro:

```json
{"v":1,"q":"1.2.4","family":"opus","estimate":225000,"actual":259000,"plan":"max5","per_point":3220000,"per_point_5h":322000}
```

Il formato, la versione di Quotient, la famiglia del modello, la stima grezza e il costo vero del lavoro in token pesati (dalla 0.9.5 senza la rilettura di quello che la chat conteneva quando il lavoro è cominciato, che la stima non riguarda), arrotondati a 3 cifre. Dalla 1.1.6, solo quando si sanno: il piano (`plan`), solo se l'hai scelto nelle impostazioni di Quotient, e quanti token pesati tiene l'1% della tua settimana (`per_point`, arrotondato a 3 cifre), solo quando Quotient l'ha imparato dalle tue letture dei limiti; dalla 1.1.7 lo stesso per la finestra di 5 ore (`per_point_5h`). Servono perché un utente nuovo dello stesso piano parta dalla misura vera dell'1% della settimana e delle 5 ore di quel piano invece che da zero, e perché i limiti di ogni piano li confermino altre persone. Quello che riceve l'utente nuovo è una stima di partenza presa da altri utenti, con il suo margine, non una certezza: Anthropic non pubblica i limiti in token e li cambia. Senza, la riga resta di cinque campi come prima. Niente date né orari, niente nomi, testi, percorsi, codici di sessione o di persona, niente account. La riga parte all'inizio della sessione successiva, mai a metà di una risposta, e niente parte prima che tu sia avvisato: la prima volta Claude Code ti mostra un messaggio che dice cosa viene condiviso e come spegnerlo. Va a un piccolo servizio su Cloudflare Workers, il cui codice è pubblico in [`server/`](server/), che accetta solo righe di quella forma.

**Scegli tu, e puoi cambiare idea quando vuoi**: la finestra del primo uso ti chiede se partecipi (di serie sì). Per cambiarlo: `/token-quotient:share off`, l'impostazione del plugin *Condividi numeri anonimi*, oppure `QUOTIENT_SHARE=0`. Da spento non parte niente, e le righe in attesa vengono cancellate. **La media condivisa la scarichi e la usi lo stesso.**

**Il servizio non tiene il tuo indirizzo IP**: il suo codice non lo legge, e il registro delle richieste è spento (Cloudflare lo accende di serie nei servizi nuovi; qui è spento). Cloudflare, che fa girare il servizio, trasporta la connessione come ogni rete: vedi la [sua informativa](https://www.cloudflare.com/privacypolicy/). Due contatori, uno per il minuto e uno per il giorno in corso, servono solo a fermare le inondazioni e vengono sovrascritti: nessuna storia degli orari d'arrivo. Cloudflare tiene anche dei punti di ripristino automatici del database per un tempo limitato, dai quali chi gestisce il servizio potrebbe in teoria capire più o meno quando è arrivata una riga.

**Cosa viene pubblicato**: al massimo una volta a settimana, e solo dopo almeno 20 lavori nuovi, la media (mediana di costo vero / stima, per famiglia di modello e in tutto, arrotondata a 2 decimali) va in `average.json`, in un progetto separato, [Korvonordico/quotient-data](https://github.com/Korvonordico/quotient-data), che contiene solo quel file: la chiave del servizio può scrivere lì e da nessun'altra parte, mai nel programma. Sotto i 30 lavori non si pubblica niente. Dalla 1.1.6 lo stesso file contiene anche, per ogni piano con almeno 30 lavori che hanno mandato `plan` e `per_point`, la misura mediana dell'1% della settimana con la sua metà centrale, arrotondata a 3 cifre; dalla 1.1.7 lo stesso per le 5 ore, per ogni piano con almeno 30 lavori che hanno mandato `plan` e `per_point_5h`. Così chi guarda solo il file non può riconoscere un singolo lavoro. Il limite, detto chiaro: il servizio non sa chi manda cosa, quindi chi manda apposta righe false potrebbe capire più o meno da che parte della media cade un lavoro vero, mai di chi è. È una media «al meglio»: chiunque può mandare numeri; per questo il servizio rifiuta i rapporti oltre x10 e i salti improvvisi con pochi lavori, e Quotient usa la media solo fra x0,25 e x4.

**Cosa viene scaricato**: una volta al giorno, `average.json` da quotient-data su GitHub, o dal servizio se GitHub non risponde. Si tengono solo i numeri. Per fermare anche lo scaricamento: `quotient config share.average_url ""` e `quotient config share.endpoint ""`.

**Cosa viene letto da Anthropic**: per mostrarti i limiti del piano, Quotient fa girare il comando `/usage` di Claude Code stesso (`claude -p /usage`, senza hook e senza salvare una sessione). Risponde Claude Code con il suo login, come quando scrivi `/usage`; Quotient non legge mai il tuo login né altre credenziali, e non manda niente da sé. Tiene solo le percentuali usate e gli orari di azzeramento. Chiede al massimo ogni minuto (dalla 1.1.8; prima ogni 10 minuti, e dalla 1.1.6 ogni minuto mentre era aperto un lavoro o una rata), in sottofondo (sempre dalla 1.1.7, così nessun messaggio la aspetta), e non spende token. Per spegnerla: `quotient config limits.live false`.

**Per quanto tempo**: si tengono solo le ultime 5.000 righe; la media usa gli ultimi 500 lavori per famiglia e 2.000 in tutto. Le righe non contengono niente che porti a una persona, quindi non si possono ritrovare e cancellare una per una: se vuoi che la condivisione si fermi, spegnila.
