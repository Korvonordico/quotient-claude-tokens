# Token Quotient: preventivi dei token e limiti di utilizzo per Claude Code

Sapere quanto costa un lavoro di [Claude Code](https://code.claude.com) prima di cominciarlo, e far stare i lavori grandi nei limiti delle 5 ore e della settimana.

[![tests](https://github.com/Korvonordico/quotient-claude-tokens/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/Korvonordico/quotient-claude-tokens/actions/workflows/tests.yml)
[![version](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2FKorvonordico%2Fquotient-claude-tokens%2Fmain%2F.claude-plugin%2Fplugin.json&query=%24.version&label=version)](CHANGELOG.md)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

*[Read in English](README.md)*

![Demo di Token Quotient](docs/demo.it.svg)

## Perché

Con un abbonamento a Claude un lavoro si paga in limiti di utilizzo: una finestra di 5 ore e un tetto settimanale. Claude Code non ti dice quanto costerà un lavoro prima di cominciarlo, quindi lo scopri alla cassa. Un refactoring grosso o una ricerca lunga possono arrivare al limite delle 5 ore a metà strada, o consumare buona parte della settimana.

Token Quotient (in breve Quotient) ti dà prima il prezzo, ti fa scegliere, misura quanto è costato davvero e impara dalla differenza. I lavori troppo grandi per oggi possono andare a rate, una al giorno, anche di notte.

Il nome tiene insieme le due metà: comincia come *quote*, che in inglese vuol dire preventivo, e in matematica il *quotient* è il quoziente, il risultato di una divisione, come un lavoro grande diviso in rate. *Token*, perché quel prezzo si conta in token.

## Cosa fa

- **Il preventivo prima di un lavoro grande.** Sopra una soglia che scegli tu (300.000 token pesati di serie), Claude non comincia. Una finestra di scelta propone da 1 a 4 livelli, di più per un lavoro più grande, ognuno con quello che comprende, il suo costo stimato, il suo tempo e la sua parte dei limiti. Questi numeri li calcola Quotient, così non ne manca nessuno. Il campo libero è per una scelta tua, per esempio un misto di due livelli.
- **Il ritmo lo scegli tu.** Tutto oggi, a parte adesso (in una sessione separata, che parte subito), un piano in giorni con la quantità al giorno e l'ora (piani più lunghi per i lavori più grandi), oppure il ritmo che scrivi tu, come «5 giorni alle 2:00».
- **Il costo vero, dopo**, letto dai file di Claude Code e messo accanto alla stima.
- **Anche quanto tempo.** Ogni livello dice anche quanto dovrebbe durare il lavoro, imparato dai tuoi lavori finiti. Quotient legge il tempo da quello che Claude Code e Hermes registrano già (nessuna finestra in più), conta solo il tempo di lavoro, e alla fine mette il tempo vero accanto a quello previsto.
- **Un preventivo nuovo a metà.** Dopo il primo milione di token pesati di un lavoro, Claude scrive quanto ne ha fatto. Quando il resto che ne viene si allontana dal preventivo di più del 30%, Quotient fa un preventivo nuovo del resto, e Claude te lo mostra una volta e ti chiede se continuare.
- **Un fattore di correzione.** Ogni preventivo viene corretto in base a quanto hanno sbagliato quelli di prima, con un fattore suo per ogni tipo di lavoro (codice, scrittura, ricerca, altro) quando quel tipo ha 3 lavori. Finché non hai 5 lavori tuoi, parte da una media condivisa di lavori veri (solo numeri, vedi [Privacy](#privacy)).
- **Le rate lavorano mentre non ci sei.** Il PC si sveglia, fa il pezzo del giorno e torna a dormire. Una notifica e un resoconto nella chat del lavoro ti dicono cosa ha fatto.

Inoltre Quotient:

- mostra quanto hai usato del limite delle 5 ore e di quello settimanale e quanto resta, e ti avvisa una volta se il ritmo di questa settimana arriverebbe al limite prima dell'azzeramento;
- pianifica la settimana tutta insieme, così più lavori a rate non mangiano mai la parte di settimana che tieni per te;
- misura a parte quanto Claude spende per rileggere una chat lunga, e propone una chat nuova quando conviene (vedi [Lavoro e rilettura](#lavoro-e-rilettura-perché-una-chat-lunga-costa-di-più));
- misura un lavoro come un lavoro solo anche quando passa da una chat all'altra;
- conta a parte le risposte su altro mentre un lavoro è in corso: stanno nel costo vero, non in quello da cui impara la correzione;
- mette ogni lavoro finito accanto a quanto è salito il limite della settimana, e ti avvisa quando i due non tornano (vedi [Come controlliamo le misure](#come-controlliamo-le-misure));
- si accorge di un lavoro contato in due pezzi, o di una misura che non torna con la settimana, e propone la riparazione (`fix`), che Claude lancia solo con il tuo sì;
- tiene i nomi dei plugin, dei server MCP e degli hook intorno a ogni lavoro, e mostra separati i lavori prima e dopo un cambio, così vedi quanto un plugin fa risparmiare o spendere; e dice quanto hanno speso le altre chat mentre un lavoro girava;
- misura il suo stesso peso, così vedi quanto costa accanto a quanto aiuta;
- apre il resoconto come pagina con i grafici (`/token-quotient:report page`, un file sul tuo PC);
- ha modi di lavorare pronti per i lavori lunghi a rate: un libro, una ricerca, una revisione di codice (`rate templates`);
- funziona anche dentro [Hermes Agent](#per-cominciare-hermes-agent).

## Per cominciare: Claude Code

In Claude Code:

```
/plugin marketplace add Korvonordico/quotient-claude-tokens
/plugin install token-quotient@token-quotient
```

L'avevi installato come `quotient@quotient`, prima della versione 0.9.8? Togli prima quello, poi aggiungi di nuovo il marketplace: `/plugin uninstall quotient@quotient` e `/plugin marketplace remove quotient`. I tuoi dati in `~/.quotient` restano.

Serve Python 3.8 o più recente (solo la libreria standard, niente da installare) e `sh`, che su Windows arriva con Git for Windows, già usato da Claude Code.

La prima volta una finestra chiede quattro impostazioni: da che grandezza un lavoro riceve il preventivo, quanta parte della settimana tenere per te, la lingua, e se Quotient può svegliare il PC per le rate e rimetterlo a dormire. Una seconda finestra ti chiede se vuoi partecipare alla media condivisa (sì, no, o quello che scrivi tu) e cosa fare con le chat lunghe (tenerle come sono, o farle compattare da sole a una certa grandezza). Le cambi quando vuoi con `/token-quotient:setup`.

Poi lavori come sempre. Sotto la soglia Claude lavora e basta; sopra, o quando dici «è un lavoro grosso», ricevi prima un preventivo.

## Per cominciare: Hermes Agent

Se usi anche [Hermes Agent](https://github.com/NousResearch/hermes-agent) con il tuo login di Claude, le sue chat consumano gli stessi limiti delle 5 ore e della settimana. Quotient può contarle e fare i preventivi anche dentro Hermes.

1. Clona questo progetto in una cartella dove può restare:

   ```
   git clone https://github.com/Korvonordico/quotient-claude-tokens
   ```

2. Aggiungi due hook nel `config.yaml` di Hermes, dove `<percorso>` è la cartella che hai clonato:

   ```yaml
   hooks:
     pre_llm_call:
       - command: "<percorso>/scripts/quotient.py hermes-hook"
     post_llm_call:
       - command: "<percorso>/scripts/quotient.py hermes-hook"
   ```

   Su macOS e Linux Hermes avvia lo script direttamente, quindi rendilo eseguibile: `chmod +x <percorso>/scripts/quotient.py`. Hermes ti chiede una volta di approvare ogni hook nuovo.

Da lì in poi Hermes dà a Claude il protocollo del preventivo e i limiti veri a ogni messaggio, misura i lavori con preventivo da `CHOICE:` a `JOB: CLOSE` (il costo e il tempo di lavoro), e propone `/compress` quando una chat è diventata così lunga che ogni passo è soprattutto rilettura (al massimo due volte per chat, a un giorno di distanza). Quotient legge i contatori dei token di Hermes dal suo archivio locale, in sola lettura: numeri, modello e titolo della chat. Non legge mai i tuoi messaggi; in una risposta con un preventivo legge anche quello che ha scritto Hermes e le scelte della sua finestra, solo per controllare che ogni livello abbia il tempo e le quote (dalla 1.1.5 anche i messaggi della risposta prima dell'ultimo). Sul piano contano solo le chat con Claude. Dalla 1.1.4 conta anche le chiamate di Hermes in sottofondo (come `background_review`), che Hermes tiene fuori dai totali delle sue chat: sui dati dell'autore erano circa il 9% del consumo di Hermes. `quotient.py hermes` mostra i numeri di Hermes; `config hermes false` spegne tutto questo. Le rate girano comunque con Claude Code.

**I lavori di Claude Code avviati da Hermes (facoltativo).** Un lavoro in Hermes spesso fa fare una parte a Claude Code (`claude -p`, direttamente o da uno script), e i contatori di Hermes non li vedono. Per contarli nel lavoro, metti `"claude_runs": 1` in `~/.quotient/config.json`. Se Claude Code ha il plugin di Quotient (dalla 1.1.4), basta questo; se non ce l'ha, aggiungi questo hook SessionStart in `~/.claude/settings.json` di Claude Code:

```json
"hooks": {
  "SessionStart": [
    {"hooks": [{"type": "command", "command": "python",
                "args": ["<percorso>/scripts/quotient.py", "claude-link"], "timeout": 10}]}
  ]
}
```

Hermes dà a ogni programma che avvia il numero della sua chat (`HERMES_SESSION_ID`). L'hook scrive una riga per ogni sessione di Claude Code in `~/.quotient/claude-links.jsonl`: quale chat di Hermes l'ha avviata, o nessuna. Quando un lavoro si chiude, Quotient aggiunge quello che le sessioni avviate da quella chat hanno speso mentre il lavoro era aperto (compresi i loro aiutanti), e il resoconto dice quanta parte del costo erano; il fattore impara dal totale, quindi il protocollo del preventivo chiede di mettere quei lavori nella stima. Le rate restano fuori, perché si misurano da sole; le attività pianificate e le sessioni che apri tu non contano mai. Con `"claude_runs_marker": "<testo>"` contano anche le sessioni `claude -p` che l'hook non ha mai visto (di prima, o con i tuoi hook spenti) quando il loro primo prompt comincia con quel testo.

**Quali lavori insegnano il fattore, e i preventivi medi (facoltativo).** I lavori piccoli sono rumore per il fattore, e un lavoro che sembra fare milioni di token pesati in pochi minuti è un errore di misura. In `~/.quotient/config.json`: `"learn_min_raw": <n>` lascia fuori i lavori in chat con un preventivo sotto n token pesati (le rate contano sempre); `"learn_max_speed": <n>` lascia fuori i lavori andati più veloci di n token pesati al secondo (un ritmo normale è circa 1.000); `"learn_mid_min": <n>` dà ai lavori in chat con un preventivo da n fino a `learn_min_raw` un fattore loro, usato per ogni preventivo sotto `learn_min_raw`; da `learn_min_raw` in su la stima si corregge a scaglioni, come una tassa: il primo `learn_min_raw` con quel fattore e il resto con quello principale, così a `learn_min_raw` non c'è un salto e un livello più grande esce sempre più grande (con i numeri dell'autore 1,1 milioni diventa 1,85 milioni e 1,6 milioni 2,36 milioni; prima della 1.1.7 uscivano tutti e due 1,75 milioni). Sono tutti e tre spenti (0) per default; l'autore usa 1.000.000, 3.000 e 500.000.

**Una chat compressa a metà di un lavoro.** Da lì in poi ogni passo rilegge meno di quello che la chat conteneva: Quotient conta questo (Hermes risposta per risposta, Claude Code chiamata per chiamata). `fix list` trova i lavori misurati prima che si contasse così, e `fix chat <lavoro>` li ricalcola (prima fa una copia; `fix undo` torna indietro).

## Come va un lavoro grande

1. Chiedi una cosa grande, oppure dici «è un lavoro grosso».
2. Claude non comincia. Stima il lavoro di ogni livello e dice di che tipo è (codice, scrittura, ricerca o altro: ogni tipo impara la sua correzione), e il resto lo calcola Quotient (`quote-table`): per ogni livello il lavoro, la rilettura della chat, il totale, il tempo previsto e la parte delle 5 ore e della settimana, con quello che resterebbe. Claude mostra quella tabella così com'è, poi si apre una finestra con due domande:
   - **Livello**: quanti livelli dipende dalla grandezza del lavoro. Fino a circa 300.000 token pesati un livello; fino a 1 milione due (buono, massimo); fino a 5 milioni tre (essenziale, buono, massimo); oltre, quattro (essenziale, buono, completo, massimo). Le grandezze si possono cambiare (`config levels.two 2000000`).
   - **Ritmo**: al massimo 4 scelte. Con uno o due livelli: tutto oggi, a parte adesso, 2 o 3 giorni. Con tre: tutto oggi, a parte adesso, 3 o 5 giorni. Con quattro: tutto oggi e piani da 3, 5 o 7 giorni (niente «a parte»: una sessione sola arriverebbe al limite delle 5 ore). Quando la chat è lunga, «in una chat nuova» viene dopo «tutto oggi» e l'ultima scelta esce. Ogni piano dice la quantità al giorno, l'ora (le 03:00 se non ne scegli un'altra, `config rate.time 02:00`), quanto dura ogni rata e la sua parte dei limiti.
   - La finestra aggiunge da sola un **campo libero** (Altro). Per il livello, scrivi una scelta tua, per esempio «il buono, più le prove del massimo»: Claude la stima e il lavoro si misura contro quella stima. Per il ritmo, scrivi quanti giorni, quanto al giorno e a che ora, per esempio «5 giorni alle 2:00» o «50.000 al giorno».
   Se un preventivo ti arriva senza il tempo o le parti dei limiti di un livello, Quotient se ne accorge alla fine della risposta, e al tuo messaggio dopo Claude te lo dice e ti ridà il preventivo completo.
3. Se scegli **tutto oggi**, Claude fa il lavoro. Quotient misura quanto è costato davvero e quanto è durato, e Claude te lo dice al tuo messaggio dopo. Se mentre il lavoro va scrivi di altro, Claude risponde e quella risposta si conta a parte: alla fine hai lavoro, messaggi di mezzo e totale. Scrivere durante il lavoro aggiunge al suo costo, e Claude lo dice dopo la scelta. Passato il primo milione di token pesati, se il ritmo del lavoro dice che il resto costerà più del 30% in più o in meno del preventivo, Claude ti mostra una volta un preventivo nuovo del resto (costo, tempo, parte dei limiti) e ti chiede se continuare come previsto, continuare con un livello più piccolo, o fermarti.
4. Se scegli **a parte, adesso**, il lavoro parte subito come una rata sola in una sessione separata di Claude Code, e il suo resoconto torna nella chat quando finisce. La sua misura è pulita e la chat non lo rilegge, ma mentre lavora non ci puoi parlare: il compito va scritto bene, non fa domande a metà, e un comando che chiede un permesso lo può fermare. Anche da Hermes, gira con Claude Code.
5. Se scegli **le rate**, una seconda finestra ti chiede quando parte la prima e, se il ritmo non l'ha già detto, a che ora partono le altre.

Le stime non sono garantite: all'inizio possono sbagliare parecchio, e si avvicinano al vero a ogni lavoro finito. Se una risposta costa più della soglia e non ha avuto un preventivo, Quotient te lo dice una volta, in una riga, e la conta nel resoconto.

I costi sono in *token pesati*: token di ingresso equivalenti, con le proporzioni dei prezzi delle API di Anthropic (ingresso 1, scrittura in cache 1,25, o 2 per la cache di un'ora, lettura dalla cache 0,1, uscita 5).

## Comandi

Nella chat:

| Comando | Cosa fa |
|---|---|
| `/token-quotient:setup` | configura Quotient, o cambia le sue impostazioni |
| `/token-quotient:report` | stime contro costi veri, i tuoi limiti, le settimane; `/token-quotient:report page` lo apre come pagina con i grafici |
| `/token-quotient:rate <lavoro>` | dividi un lavoro grande in rate |
| `/token-quotient:share [on\|off]` | la media condivisa: cosa parte esattamente, e accenderla o spegnerla |
| `/token-quotient:help` | tutti i comandi, con quello che fanno |

Gli altri comandi li usa Claude per te quando scegli nelle finestre.

<details>
<summary>Comandi da terminale</summary>

Si lanciano come `python scripts/quotient.py <comando>` dalla cartella del plugin o da una copia clonata di questo progetto.

| Comando | Cosa fa |
|---|---|
| `report [--html]` | il resoconto (`--html`: una pagina con i grafici, aperta nel browser) |
| `setup --threshold N --reserve N --lang it\|en --after sleep\|hibernate\|nothing` | salva le impostazioni (anche `--wake yes\|no` e `--share yes\|no`) |
| `setup --compact keep\|auto\|<token>` | chat lunghe: tenerle come sono, o farle compattare da sole a una grandezza |
| `config [chiave [valore]]` | mostra tutte le impostazioni, o ne cambia una |
| `share status\|on\|off\|send` | la condivisione, da terminale (`send`: manda subito le righe in attesa) |
| `export` | la riga esatta che la condivisione manda per ogni lavoro finito |
| `quote-table --raw essential=N good=N max=N [--kind rate] [--type code\|writing\|research\|other] [--lang it\|en]` | il preventivo calcolato da Quotient: ogni numero di ogni livello (tempo, parte delle 5 ore e della settimana) e le scelte del ritmo; Claude lo lancia e ne copia la tabella |
| `fix [list]`, `fix merge <a> <b>`, `fix exclude <lavoro> [--why ...]`, `fix chat <lavoro>`, `fix undo` | la riparazione guidata: cosa non torna nelle misure; riunire un lavoro contato in due pezzi; togliere dal fattore una misura sbagliata; ricalcolare la parte della chat di un lavoro la cui chat è stata compressa mentre girava; annullare l'ultima riparazione. Prima viene fatta una copia di `jobs.jsonl` e niente si cancella |
| `timer start --raw N [--level L]`, `timer show`, `timer stop` | il cronometro di un lavoro con preventivo: lo fa partire Claude quando comincia il lavoro; `stop` nasconde la finestra fino al lavoro dopo |
| `backfill-time` | ricava dai registri il tempo dei lavori misurati prima della 1.1.0 (Quotient lo fa da sola una volta) |
| `setup-statusline [--write]` | mostra i limiti del piano nella riga di stato |
| `plan-changed [--undo] [--plan pro\|max5\|max20\|other\|unknown]` | hai cambiato abbonamento: Quotient reimpara da adesso quanto valgono i tuoi limiti (`--undo`: annulla l'ultimo cambio; `--plan`: il piano nuovo) |
| `telemetry [status\|on\|off] [--write]` | la telemetria di Claude Code come seconda misura, tenuta su questo PC: `on` stampa le impostazioni, `--write` le scrive in `~/.claude/settings.json` (prima una copia) |
| `hermes` | le chat di Hermes Agent: legge subito i suoi contatori dei token |
| `tick` | legge subito i contatori di Hermes e i limiti del piano (per un'attività pianificata) |
| `rate new <lavoro> --dir <cartella> --task-file <file> --quote N (--days N \| --daily N \| --pace "5 giorni alle 2:00") [--at HH:MM] [--template book\|research\|code-review] [--type code\|writing\|research\|other]` | crea un lavoro a rate (`--pace`: le tue parole, con i giorni, la quantità al giorno e l'ora) |
| `rate templates` | i modi di lavorare pronti: libro, ricerca, revisione di codice |
| `rate apart <lavoro> --dir <cartella> --task-file <file> --quote N [--type ...]` | fa un lavoro a parte, adesso: una rata sola in una sessione separata, che parte subito; il suo resoconto torna nella chat |
| `rate run <lavoro> [--force]` | fa partire una rata adesso (`--force`: anche se oggi ne è già partita una) |
| `rate once <lavoro> [--time HH:MM]` | una rata a quell'ora (domani se l'ora è passata; senza `--time`, l'ora del lavoro); sveglia il PC |
| `rate schedule <lavoro> [--time HH:MM] [--force]` | una rata ogni giorno a quell'ora (senza `--time`: l'ora del lavoro, se no le 03:00); sveglia il PC |
| `rate after <lavoro> sleep\|hibernate\|nothing` | cosa fa il PC dopo ogni rata, se nessuno lo usa |
| `rate here <lavoro>` | il resoconto di ogni rata arriva in questa chat |
| `rate week` | tutti i lavori aperti contro quello che resta della settimana |
| `rate set <lavoro> --daily N --per-day N --days N` | cambia un lavoro: grandezza di ogni rata, quante al giorno, quante in tutto |
| `rate pause <lavoro>`, `rate resume <lavoro>` | mette in pausa un lavoro, o lo fa ripartire |
| `rate stop <lavoro>` | ferma un lavoro e toglie le sue partenze programmate |
| `rate status [lavoro]` | rate fatte e token pesati spesi |
| `rate check [--live]` | una rata programmata può svegliare questo PC, e Claude Code ha il login fatto? (`--live`: una chiamata vera, pochi centesimi) |

</details>

## Come funzionano le rate

Lasci il PC in sospensione o in ibernazione, come fai sempre. Ogni rata poi va così:

1. **All'ora che hai scelto** (per esempio le 3 di notte), Windows sveglia il PC.
2. **Quotient avvia Claude Code** in sottofondo, senza aprire l'app. Claude legge il lavoro e una breve nota su dove si era fermato l'ultima volta.
3. **Claude lavora sul pezzo successivo** finché arriva alla quantità di quel giorno. Poi scrive dove si è fermato e si ferma in ordine.
4. **Quando nessuno sta usando il PC** (tastiera e mouse fermi da 10 minuti), Quotient lo rimette in sospensione, o in ibernazione se hai scelto così, chiunque l'abbia acceso. Prima arriva una notifica: se muovi il mouse entro 2 minuti, il PC resta acceso. Se lo stai usando, Quotient aspetta che smetti, fino a 6 ore.
5. **Il giorno dopo, alla stessa ora, ricomincia**, finché il lavoro è finito. Poi l'orario si cancella da solo.

Quando torni, Windows ha mostrato una notifica per ogni rata, che resta nel centro notifiche; con un clic si apre una pagina con il resoconto di quella rata (resta nella cartella del lavoro, in `resoconti`). Il resoconto completo ti aspetta nella chat in cui hai creato il lavoro e compare al tuo primo messaggio lì: quale rata, quando, quanto è costata rispetto alla quantità del giorno e alla settimana, cosa ha fatto, cosa manca e quando parte la prossima. Le altre chat te lo dicono una volta sola, e una seconda volta non prima di un giorno dopo; poi tacciono. Se vuoi i resoconti in un'altra chat, chiedilo a Claude lì (`rate here <lavoro>`).

Da sapere:

- Se preferisci che Quotient non tocchi mai il PC, lo scegli nella configurazione: le rate allora partono solo con il PC già acceso.
- Un timer può svegliare un PC in sospensione o in ibernazione, non uno spento del tutto. Se il PC era spento, la rata parte appena lo accendi.
- Windows deve permettere i timer di riattivazione. `rate check` ti dice se è così, e come attivarli.
- Se usi l'app desktop di Claude, fai una volta il login di Claude Code in un terminale (`claude auth login`): le rate girano fuori dall'app. Quel login può scadere: finché c'è un lavoro a rate aperto, Quotient lo controlla ogni 6 ore sui tuoi messaggi (senza costi) e te lo dice in chat, così lo rinnovi prima della notte. `rate check --live` fa una chiamata vera con il modello più piccolo per esserne sicuri (pochi centesimi). Una rata che si ferma per il login non spende niente, e la sua notifica dice cosa fare.
- Puoi far partire una rata in più lo stesso giorno, se accetti che consumi altro limite di quel giorno.
- Se alla fine di una rata il ritmo delle rate dice che il resto costerà più del 30% sopra il piano, la notifica e il resoconto danno i numeri nuovi (quanto resta, quante rate ancora, parte della settimana, tempo) e chiedono se continuare, fare rate più grandi, o fermarsi.
- L'ultima parte del tetto di ogni rata (l'8%, `config rate.save_percent`) è tenuta per salvare: lì Quotient rifiuta quello che comincia lavoro nuovo (aiutanti, ricerche sul web, comandi) e lascia passare Write ed Edit, così la rata e i suoi aiutanti salvano quello che hanno trovato. Le rate salvano man mano, e i loro aiutanti scrivono i risultati su file. Se una si ferma lo stesso, la sua consegna elenca i file dei suoi aiutanti e cosa hanno fatto, così la rata dopo li riprende invece di rifarli.
- Il risveglio e la sospensione funzionano su Windows. Su macOS e Linux Quotient ti dà la riga per programmarlo tu.

## Più nel dettaglio

### La settimana: tutti i lavori insieme

Due o tre lavori possono stare ognuno nella settimana e non starci insieme. Quotient somma tutte le rate previste fino all'azzeramento del limite settimanale e tiene una riserva per il tuo uso normale (il 20%, se non la cambi). Se il piano non ci sta, una finestra ti chiede quali lavori tenere, rallentare o mettere in pausa. Una rata non entra mai nella riserva: si accorcia, o aspetta.

### I tuoi limiti

Quotient registra quanto hai usato del limite delle 5 ore e di quello settimanale e quando si azzerano, e può mostrarlo nella riga di stato di Claude Code (`setup-statusline --write`):

```
Quotient · 5 ore: usato 31%, resta 69%, si azzera 19:30 · settimana: usato 6%, resta 94%, si azzera lun 12 07:00
```

Prende questi numeri da quello che Claude Code passa alla riga di stato, e anche dal comando `/usage` di Claude Code stesso, fatto girare in sottofondo senza spendere token (al massimo ogni 10 minuti; si spegne con `config limits.live false`). Così i limiti ci sono anche nell'app desktop di Claude, dove la riga di stato non c'è. `tick` li legge subito, per un'attività pianificata.

Col tempo stima anche quanti token vale l'1% di ogni limite, così un preventivo può dire «questo prende circa l'8% della tua settimana». Anthropic non pubblica i limiti in token, quindi è una stima, con il suo margine.

**Imparati per il tuo piano.** Ogni utente impara quanto valgono i propri limiti, sul proprio PC, dalle proprie letture: Pro, Max e gli altri piani hanno limiti diversi, e nessuna grandezza viene presunta o condivisa. I modelli più pesanti (Opus più di Sonnet) consumano i limiti più in fretta per gli stessi token, quindi la stima si muove anche con i modelli che usi.

**La settimana controllata con le 5 ore (1.1.2).** La settimana sale lentamente, quindi la sua stima ha pochi punti. Però le due percentuali salgono con lo stesso uso: dentro una stessa finestra di 5 ore e una stessa settimana, Quotient mette accanto di quanti punti sono salite le 5 ore e di quanti la settimana. Quel rapporto, per quanto vale l'1% delle 5 ore (che ha molti punti), è una seconda stima della settimana. Il resoconto le mostra una accanto all'altra e dice quando sono lontane più di 1,5 volte (`config ratio.factor`). Quando la stima propria della settimana ha meno di 3 punti e il rapporto li ha, al suo posto si usa il rapporto, e il resoconto lo dice. Le percentuali sono numeri interi, quindi anche il rapporto ha il suo margine.

**Se cambi piano (1.1.2).** Quotient calcola quanto vale ogni finestra. Quando le ultime tre finestre di 5 ore, in più di un giorno, sono tutte lontane più di 1,6 volte dalle precedenti nella stessa direzione (`config plan.factor`), e la settimana nello stesso tempo pure, lo prende per un cambio di piano: dall'inizio di quelle finestre impara solo dalle letture nuove, scrive il cambio in `plan-changes.jsonl`, e Claude te lo dice una volta: il tuo limite sembra cambiato, forse hai cambiato abbonamento, Quotient riparte a impararlo. Un giorno di molto uso fuori da Quotient (claude.ai, il telefono) fa sembrare il limite più piccolo per un po': per questo non bastano una finestra lontana, né un giorno solo; anche giorni con un modello più pesante possono sembrare un piano più piccolo. Puoi anche dirlo tu: `plan-changed` riparte a impararlo da adesso (finché la settimana non ha i suoi punti, si stima dal rapporto con le 5 ore, e il resoconto lo dice), e `plan-changed --undo` annulla l'ultimo cambio se non c'era.

### Il tempo di un lavoro

Un preventivo dice anche quanto dovrebbe durare ogni livello. Quotient misura il **tempo di lavoro** di ogni lavoro con preventivo: il tempo in cui Claude lavora, senza i tuoi turni (dalla fine di una risposta al tuo messaggio dopo) e senza l'attesa della finestra di scelta. Dai tuoi ultimi 20 lavori finiti impara quanti minuti servono per un milione di token pesati di lavoro (la mediana), a parte per le rate, e il tempo previsto di un livello è il suo lavoro corretto per quel numero. Come il fattore di correzione, si avvicina al vero a ogni lavoro. I lavori misurati prima della 1.1.0 ricevono il loro tempo una volta sola dai registri: la trascrizione della chat, gli orari dei messaggi di Hermes, l'inizio e la fine delle rate.

Nelle parole del suo primo utente, durante due rate: «so quanto ci mette, quindi posso staccarmi dal computer».

Claude segna l'inizio del lavoro subito dopo la scelta (`timer start`). Dopo il primo milione di token pesati (`config requote.after`), a ogni tuo messaggio Quotient guarda anche il ritmo del lavoro stesso, e Claude scrive una riga `PROGRESS: <n>%`. Quando il resto secondo quella riga si allontana dal resto del preventivo di più del 30% (`config requote.percent`), Quotient fa un preventivo nuovo, una volta per lavoro, e Claude te lo mostra al tuo messaggio dopo. Il lavoro lo tiene, e alla fine la riga di chiusura dice quanto si è avvicinato al costo vero: il resoconto elenca questi preventivi nuovi, così vedi se valgono qualcosa.

Il tempo sta nella riga di stato di Claude Code. Esiste anche una piccola finestra con il cronometro, spenta di serie (`config timer.window true`; serve tkinter di Python). Al tuo messaggio dopo Claude ti dice il costo e il tempo veri del lavoro contro quelli previsti. Il resoconto e la notifica di ogni rata dicono quanto ha lavorato, e `rate new` dice quanto dovrebbe durare ogni rata.

### Lavoro e rilettura: perché una chat lunga costa di più

A ogni passo (ogni chiamata al modello) Claude rilegge tutto quello che la chat contiene: il sistema, gli strumenti, le tue regole, la conversazione fin lì. Ogni token riletto costa poco (un decimo di uno nuovo, grazie alla cache), ma si somma. In una chat che parte da 165.000 token, ogni passo costa circa 16.500 token pesati prima ancora di lavorare; un lavoro da 100 passi, circa 1,65 milioni. Un modello che stima un lavoro pensa al lavoro, non a questo.

Per questo Quotient divide in due ogni lavoro che misura:

- **lavoro**: i passi del lavoro stesso. La stima riguarda questo, e la correzione si impara da qui.
- **rilettura**: quello che la chat conteneva già quando il lavoro è cominciato, riletto a ogni passo. Quotient la misura, e in un preventivo la aggiunge dalla grandezza della chat adesso e dai passi che il lavoro richiederà.

Un caso vero, 6 ottobre 2026: un lavoro è costato 4,67 milioni di token pesati, di cui 2,82 milioni di lavoro e 1,85 milioni per rileggere i 165.000 token con cui la chat era partita, in 107 passi.

Quando una chat è diventata lunga, la finestra propone anche di fare il lavoro **in una chat nuova**, e dice quanto si risparmia. Apri una chat nuova e chiedi di continuare: Quotient dice alla chat nuova che c'è un lavoro che aspetta, e lo misura lì.

### Chat lunghe: tenerle, o farle compattare da sole

Un plugin non può lanciare `/compact`, ma Claude Code sa riassumere da solo una chat quando arriva a una certa grandezza. Nella configurazione scegli una di tre:

- **Tieni la chat com'è** (di serie). Quotient non tocca la compattazione; quando una chat è diventata lunga, la finestra propone una chat nuova.
- **Falla compattare da sola alla grandezza che consiglia Quotient**: dove rileggere la chat a ogni passo costa circa il doppio del lavoro di un passo, calcolato sui tuoi numeri (circa 600.000 token all'inizio).
- **A una grandezza che scegli tu**, da 100.000 a 1.000.000 di token.

Per le ultime due, Quotient scrive `autoCompactWindow` in `~/.claude/settings.json`, e riprende il suo valore se torni alla prima (se prima c'era un valore tuo, lo rimette). Un riassunto perde qualche dettaglio: quando la chat si avvicina alla grandezza, Quotient dice una volta a Claude di salvare nei file quello che non si deve perdere. Ogni compattazione viene misurata, e il resoconto dice quanto ha fatto risparmiare. La cambi quando vuoi con `/token-quotient:setup` o nelle impostazioni del plugin.

### Tipi di lavoro, cambi intorno a Claude, e riparazioni (1.1.4)

- **Tipi di lavoro.** Codice, scrittura e ricerca sul web sbagliano in modo diverso: il 15 ottobre 2026 un controllo dei fatti di un libro con ricerche sul web è stato stimato 1,6 milioni di token pesati ed è costato 4,4 milioni. La riga QUOTE porta un tipo (`kind=code|writing|research|other`). Un tipo usa un fattore suo quando ha 3 lavori finiti (`config type_min_jobs`), prima quello generale. Il resoconto mostra il fattore di ogni tipo con quanti lavori ha. I lavori di prima della 1.1.4 contano come `other`.
- **Cambi intorno a Claude.** Ogni lavoro finito e ogni rata tengono i nomi di quello che c'era intorno: i plugin attivi di Claude Code, i server MCP e gli hook, e quelli di Hermes (solo i nomi: mai una riga di comando, un'impostazione o un segreto). Quando cambiano, Claude te lo dice una volta, e il resoconto mostra separati i lavori prima e dopo il cambio (fattore, e costo di 1 milione di token pesati di lavoro). Quando dopo il cambio ci sono 3 lavori finiti, contano doppio nel fattore (`config env.min_jobs`, `env.weight`).
- **Lavoro fatto altrove.** Ogni lavoro e ogni rata registrano quanto hanno speso le altre chat (Claude Code, rate, Hermes) mentre girava. Quando sono almeno 50.000 token pesati e il 5% del lavoro, la riga di chiusura e il resoconto della rata lo dicono: non è nel costo del lavoro, ma è nei tuoi limiti.
- **Riparazioni.** `fix list` mostra cosa non torna: un lavoro piccolo finito al massimo 30 minuti prima che ne cominciasse un altro della stessa chat (probabilmente un lavoro contato in due pezzi), le misure che non tornano con la settimana, e i lavori la cui chat è stata compressa mentre giravano, misurati prima che si contasse. `fix merge` riunisce due lavori, `fix exclude` toglie un lavoro dal fattore, `fix chat` ricalcola la parte della chat di un lavoro, `fix undo` annulla l'ultima riparazione. Ognuna copia prima `jobs.jsonl` (in `~/.quotient/fix/`), tiene quello che toglie in `jobs-excluded.jsonl`, e scrive il fattore prima e dopo in `fix.jsonl`. Claude propone il comando quando Quotient trova un problema, e lo lancia solo con il tuo sì.

### Seconde misure, il tuo piano, e il lavoro a pacchetti (1.1.6)

- **La telemetria di Claude Code** (spenta di serie). `telemetry on` stampa le righe per il blocco `env` di `~/.claude/settings.json`; `telemetry on --write` le scrive lì dopo una copia del file. Claude Code manda allora i suoi contatori di token e costi a un piccolo ricevitore su questo PC (`127.0.0.1:4318`), che tiene solo numeri in `~/.quotient/otel.jsonl` e si ferma da solo dopo 2 ore senza dati. Ogni lavoro e ogni rata finiti si mettono a confronto: quando le due misure differiscono di più del 25%, Claude te lo dice una volta, e il resoconto mostra il confronto e le chiamate di contorno (titoli, riassunti) che vede solo la telemetria. Niente cambia da solo.
- **I costi che calcolano gli altri.** La stima dei costi di Hermes, il costo di ogni rata secondo Claude Code e, con la riga di stato accesa, il costo della sessione si mettono contro i token pesati nel resoconto, con i prezzi che ne risultano. Sui dati dell'autore una lettura della cache costa 0,05 volte l'ingresso, non lo 0,1 con cui pesa Quotient: il resoconto lo mostra, e `config weights.cache_read 0.05` è una tua scelta.
- **I limiti letti ogni minuto durante un lavoro** (`config limits.job_every`, in sottofondo): più punti, quindi la grandezza del tuo limite si impara in meno usi. Le percentuali sono numeri interi (controllato su 254 letture), quindi ogni finestra tiene un margine di un punto.
- **Il tuo piano.** La finestra delle impostazioni lo chiede (Pro, Max 5x, Max 20x, altro, non so; `setup --plan`, `plan-changed --plan`). Finché le tue letture non bastano, Quotient parte dalla grandezza condivisa dell'1% della settimana del tuo piano, detta come stima con il suo margine.
- **Pacchetti.** Dopo ogni milione di lavoro l'agente scrive `PROGRESS: n%`; tutto il lavoro è allora il costo fatto diviso l'avanzamento (il tempo allo stesso modo), con un margine che si stringe a ogni pacchetto. Ogni rata è un pacchetto. Quando un lavoro si chiude, Quotient tiene quanto sbagliavano le righe PROGRESS, e diventa il margine dei lavori dopo.

## Privacy

Tutto quello che Quotient registra resta sul tuo computer, in `~/.quotient/` (o in `QUOTIENT_HOME`). Dalle trascrizioni di Claude Code legge dei numeri: i token di ogni chiamata, le righe per la macchina che scrive Claude e i nomi degli strumenti usati. In una risposta con un preventivo legge anche quello che ha scritto Claude e le scelte della finestra, solo per controllare che ogni livello abbia il tempo e le quote (1.1.3). Nessun testo delle tue chat viene mai mandato da nessuna parte.

Una sola cosa esce dal tuo computer, e la puoi spegnere: dopo ogni lavoro finito, una riga di numeri per la media condivisa, esattamente questa:

```json
{"v":1,"q":"1.1.7","family":"opus","estimate":225000,"actual":259000,"plan":"max5","per_point":3220000}
```

- `plan` solo se hai scelto il tuo piano; `per_point` (quanti token pesati tiene l'1% della tua settimana, 3 cifre) solo quando Quotient l'ha imparato dalle tue letture.
- Niente date, orari, nomi, testi, percorsi, codici di sessione o di persona. Il servizio che raccoglie le righe ([codice in `server/`](server/)) non tiene gli indirizzi IP.
- La spegni con `/token-quotient:share off`, con l'impostazione del plugin *Condividi numeri anonimi*, oppure con `QUOTIENT_SHARE=0`. Anche da spenta ricevi la media condivisa. `/token-quotient:share` ti mostra esattamente cosa parte e quante righe aspettano.
- Quotient inoltre scarica la media condivisa una volta al giorno, e legge l'uso del tuo piano da Anthropic con il login di Claude Code (dettagli qui sotto).

Tutto nel dettaglio: [PRIVACY.md](PRIVACY.md).

<details>
<summary>Cosa viene condiviso, nel dettaglio</summary>

Ogni copia di Quotient impara dai suoi errori, ma chi comincia non ne ha ancora. Allora le copie mettono insieme i loro numeri. La riga contiene il formato, la versione di Quotient, la famiglia del modello (opus, sonnet, haiku, fable o altro), la stima grezza e il costo vero del lavoro in token pesati (dalla 0.9.5 senza la rilettura della chat, che la stima non riguarda), arrotondati a 3 cifre; dalla 1.1.6 anche il tuo piano, se l'hai scelto, e la grandezza dell'1% della tua settimana imparata sul tuo PC, così chi comincia con lo stesso piano parte dalla media di quel piano. Parte all'inizio della chat successiva, mai a metà di una risposta, e niente parte prima che Claude Code ti abbia mostrato un messaggio che lo dice.

- Il servizio non tiene gli indirizzi IP: il suo codice non li legge e il registro delle richieste è spento.
- Al massimo una volta a settimana, dopo almeno 20 lavori nuovi e mai sotto i 30 in tutto, pubblica la media in un progetto tutto suo, [quotient-data](https://github.com/Korvonordico/quotient-data) (la chiave del servizio può scrivere solo lì, mai in questo programma). Ogni copia di Quotient scarica quel file una volta al giorno e lo usa solo fra x0,25 e x4: chiunque può mandare numeri, quindi è una media «al meglio».
- La finestra del primo uso ti chiede se partecipi (di serie sì), e puoi cambiarlo quando vuoi.

</details>

<details>
<summary>Tutto quello che Quotient fa partire, manda e scarica</summary>

- **Sul tuo computer, sempre**: il suo programma in Python, tramite `sh`, all'inizio di ogni chat, a ogni messaggio, alla fine di ogni risposta, prima di una compattazione e prima di ogni strumento dentro una rata. Legge le trascrizioni delle tue chat che tiene Claude Code per dei numeri: i token di ogni chiamata, le righe per la macchina che scrive Claude, e quali strumenti Claude ha usato (per misurare il costo e il peso di Quotient stesso); in una risposta con un preventivo, anche quello che ha scritto Claude e le scelte della finestra, per controllare che ogni livello abbia il tempo e le quote. Alla fine di una rata che si è fermata con degli aiutanti, legge anche la breve descrizione di ogni aiutante e cerca il suo messaggio di rifiuto nelle loro trascrizioni, per elencarli nella consegna del lavoro. Nessun testo di quelle chat viene mai mandato da nessuna parte.
- **Scrive** solo in `~/.quotient/` (o in `QUOTIENT_HOME`), più una pagina con il resoconto di ogni rata nella cartella del lavoro. Le due eccezioni toccano `~/.claude/settings.json`, e solo quando le scegli tu: `setup-statusline --write` ci mette la riga di stato, e la scelta «compatta» per le chat lunghe ci scrive `autoCompactWindow` (che riprende quando torni a «tieni»).
- **Per le rate, solo dopo che le hai scelte nella finestra**: attività dell'Utilità di pianificazione di Windows (`schtasks`) che partono all'ora che hai scelto e, se lo permetti, svegliano il PC; Claude Code stesso (`claude -p`) nella cartella del lavoro, con la modalità di permessi `acceptEdits`, senza richieste di permesso, e solo con gli strumenti che permetti in `rate.extra_args`; PowerShell per la notifica e per leggere quando parte la prossima rata; la sospensione o l'ibernazione dopo, se l'hai scelto e nessuno sta usando il PC. `rate check` legge (non cambia mai) l'impostazione dei timer di riattivazione con `powercfg`.
- **Usa il comando `/usage` di Claude Code** per leggere l'uso del tuo piano: risponde Claude Code stesso, sul tuo computer, con il suo login, e Quotient tiene solo le percentuali e gli orari di azzeramento. Al massimo ogni 10 minuti (ogni minuto mentre è aperto un lavoro o una rata), sempre in sottofondo, così nessun messaggio la aspetta (dalla 1.1.7), senza spendere token; Quotient non legge mai il tuo login. Si spegne con `config limits.live false`.
- **La telemetria di Claude Code, solo se la accendi** (`telemetry on`): un ricevitore suo su `127.0.0.1` (porta 4318, solo questo PC) tiene i numeri dei contatori di token e costi di Claude Code in `~/.quotient/otel.jsonl` e butta tutto il resto (e-mail, codici dell'account). `telemetry on --write` e `telemetry off --write` cambiano il blocco `env` di `~/.claude/settings.json`, dopo averne fatto una copia.
- **La riga di stato**, se l'hai messa, tiene anche il costo della sessione che le dà Claude Code (`statusline-cost.jsonl`, solo numeri).
- **Con Hermes Agent** legge l'archivio locale delle sessioni di Hermes, in sola lettura: contatori dei token (anche quelli delle sue chiamate in sottofondo), modello e titolo della chat, e, per il tempo di lavoro di un lavoro con preventivo, quando è stato scritto ogni messaggio e da chi; in una risposta con un preventivo, anche quello che ha scritto Hermes e le scelte della sua finestra clarify, solo per controllare il preventivo (1.1.5). Non legge mai i tuoi messaggi.
- **I nomi intorno a un lavoro** (1.1.4): alla fine di ogni lavoro e di ogni rata legge le impostazioni di Claude Code (`settings.json`, `settings.local.json`, `~/.claude.json`, il `.mcp.json` della cartella) e il `config.yaml` di Hermes per i nomi dei plugin attivi, dei server MCP e degli script lanciati dagli hook, e la cache che usa Hermes. Tiene solo i nomi, in `~/.quotient/env.jsonl`; mai una riga di comando, un'impostazione o un segreto, e non manda niente.
- **La finestra del cronometro**, solo se la accendi (`config timer.window true`): una sua piccola finestra (tkinter di Python) che legge solo `~/.quotient/timer.json`.
- **Manda**, se la condivisione è accesa: una riga di numeri per ogni lavoro finito a `https://quotient-share.korvonordico.workers.dev`.
- **Scarica**, una volta al giorno: `https://raw.githubusercontent.com/Korvonordico/quotient-data/main/average.json`, oppure `/v1/average` del servizio quando GitHub non risponde. Tutti e due sono dell'autore.
- **La pagina con i grafici** è un file, `~/.quotient/report.html`, aperto nel tuo browser; non carica niente da internet.

</details>

## Come controlliamo le misure

La correzione impara dalle misure: se le misure sono sbagliate, impara la cosa sbagliata. Ecco come Quotient le controlla, e cosa non è ancora dimostrato.

- **Prove automatiche.** 334 prove girano a ogni cambiamento, su Windows e su Ubuntu con Python 3.9 e 3.13, su chat inventate di cui si conoscono in anticipo i costi: ogni chiamata contata una volta, la parte della chat, il tempo di lavoro, i lavori che passano da una chat all'altra, le rate, Hermes.
- **Errori trovati e corretti.** Nella 1.0.0 i lavori misurati in Hermes si sono rivelati 57 pezzi di 4 lavori veri: l'agente riscriveva il preventivo a ogni messaggio, e ogni copia apriva un lavoro nuovo. Il fattore di correzione era sceso a x0,14. La causa è corretta; i pezzi già fatti non sono stati riparati in automatico. Il 15/10/2026 un pezzo di un lavoro è stato trovato contato a parte, ed è stato rimesso a mano; dalla 1.1.4 Quotient trova da sola questi casi e propone `fix`.
- **Le misure contro la settimana (1.1.1).** Anthropic mostra la parte del limite settimanale usata, e Quotient stima quanti token pesati vale l'1%. Ogni lavoro finito e ogni rata vengono messi accanto a quanto è salita la settimana nello stesso tempo. Se i due sono lontani più di 3 volte (`config check.factor`) e non c'era nessun altro lavoro in corso, Claude ti dice una volta che la misura di quel lavoro non torna con la settimana, e il resoconto la elenca. Quotient non cambia niente da solo. I lavori sotto i 4 punti della settimana non si giudicano, perché le percentuali sono numeri interi. Anche le altre chat, e l'uso che Quotient non vede (claude.ai, il telefono), muovono la settimana: un avviso è un indizio da controllare, non una prova.
- **La settimana contro le 5 ore (1.1.2).** Quanto vale la settimana si stima in due modi: dai token pesati misurati contro la sua salita, e dal rapporto fra le salite delle 5 ore e della settimana, per quanto valgono le 5 ore. Sulle letture dell'autore dal 5 al 15 ottobre 2026 le due sono uscite uguali (distanti x1,00: 8,7 punti delle 5 ore per 1 punto della settimana, da 84 punti della settimana in 24 finestre). Il resoconto le mostra tutte e due, e dice quando si separano.
- **Hermes contro Claude Code (1.1.4).** Dal 10 ottobre 2026 quanto vale l'1% delle 5 ore, imparato sul PC dell'autore, era circa la metà di prima, e l'autore era passato soprattutto a Hermes. Su una copia dei dati: nelle finestre di 5 ore con solo Claude Code (tutte prima del 10/10) l'1% valeva da 650.000 a 840.000 token pesati; in quelle con solo Hermes (dopo) quasi sempre da 350.000 a 450.000; ma dopo il 10/10 anche le finestre con quasi solo Claude Code valevano poco, da 250.000 a 290.000. Quindi il calo non è di Hermes, e la sua causa non si conosce (un cambio dei limiti, o un uso che Quotient non vede). Non era nemmeno la cache: Hermes scrive cache da 5 minuti, come le conta Quotient. Un buco vero è stato trovato: Hermes tiene le sue chiamate in sottofondo fuori dai totali delle sue chat, l'8,8% del suo uso in quei giorni, quindi il costo letto da Hermes era circa il 10% più basso del vero. Quotient le conta dalla 1.1.4, e la parte del resoconto su Hermes dice quanto hanno pesato sulla settimana.
- **Altre misure accanto a quelle di Quotient (1.1.6).** Sui dati dell'autore (55 chat di Hermes, 37 rate con il costo dato da Claude Code) i prezzi veri tornano con i pesi di Quotient tranne uno: una lettura dalla cache costa 0,05 volte l'input, non 0,1, quindi i lavori con molta rilettura pesano un po' più di quanto costano. I pesi sono rimasti come sono; il resoconto mostra i prezzi che ne escono. Le altre chiamate di Hermes (approvazioni dei comandi, compressioni, titoli, guardia web) non sono registrate da nessuna parte: circa il 2% del suo uso dal 10/10, troppo poco per spiegare il calo qui sopra. Le percentuali dei limiti sono numeri interi (254 letture): niente decimali da usare.
- **Non ancora dimostrato.** I numeri vengono da pochi lavori, e il tempo di un lavoro da un solo utente. Se i preventivi continuano ad avvicinarsi, e quanto funziona il tempo previsto per altre persone e altri tipi di lavoro, è ancora da vedere. Il resoconto mostra gli errori come sono, così puoi giudicare.

## Limiti noti

- Le prime stime saranno poco precise. Uno studio del 2026 ha chiesto a dei modelli di IA di prevedere il proprio costo prima di lavori di programmazione: otto modelli, correlazione con il costo vero al massimo 0,39, e stime sistematicamente troppo basse ([Bai e altri, arXiv:2604.22750](https://arxiv.org/abs/2604.22750)). Quotient non rende il modello più bravo a indovinare: misura l'errore e corregge la stima dopo.
- Dipende dal fatto che Claude segua le regole che Quotient gli dà. Se un preventivo salta, quel lavoro non viene misurato (una risposta grande senza preventivo viene contata e detta una volta); una risposta su altro senza la sua riga `ASIDE` conta come lavoro.
- Anche Quotient ha un peso: le sue regole all'inizio di una chat (circa 2.800 token) e una riga a ogni messaggio (circa 110 token in una chat lunga, circa 180 mentre è aperto un lavoro), che restano nella chat e vengono rilette. Quotient misura questo peso e lo mostra nel resoconto, con i token contati dai caratteri (una stima).
- La parte di rilettura di un preventivo presume che la cache funzioni. Dopo una pausa più lunga di quanto dura la cache, la chat viene scritta di nuovo a un prezzo più alto: questo si misura dopo, non si prevede.
- Quanto Quotient fa risparmiare non si può misurare, perché un lavoro non fatto non ha un costo. Il resoconto dà una stima (per esempio quanto hanno evitato le scelte sotto il massimo) e dice che è una stima.
- Il tempo di lavoro lascia fuori i tuoi turni e la finestra di scelta, non le altre attese dentro una risposta (una richiesta di permesso, un comando che aspetta il tuo ok): quelle contano come lavoro. Il tempo previsto è preciso quanto la stima dei token da cui viene, e i primi sono poco precisi.
- Anthropic potrebbe aggiungere una funzione simile dentro Claude Code. Andrebbe bene così.

<details>
<summary>Dettagli tecnici</summary>

**L'unità.** I costi sono in token pesati: token di ingresso equivalenti, con le proporzioni dei prezzi delle API di Anthropic (ingresso 1, scrittura in cache 1,25 per 5 minuti o 2 per un'ora, lettura dalla cache 0,1, uscita 5). In una prova dal vivo il costo in dollari segnato da Claude Code era esattamente i token pesati per il prezzo di ingresso del modello.

**Come si aggancia.** All'inizio di una chat Quotient dà a Claude le sue regole una volta sola (circa 9.900 caratteri, più o meno 2.800 token); a ogni messaggio, una riga corta (circa 390 caratteri in una chat lunga, più o meno 110 token, con i limiti, il fattore e la CHAT PART: quanto aggiunge rileggere questa chat; circa 630 caratteri mentre è aperto un lavoro). Dalla 1.1.7 la riga porta solo quello che cambia da un messaggio all'altro: le regole restano nel protocollo, e il resto lo calcola `quote-table`. Claude scrive delle righe per la macchina (`QUOTE:`, `CHOICE:`, `PACE:` con `today`, `apart`, `new chat` o un piano, `JOB: CONTINUES`, `ASIDE` per una risposta su altro, `JOB: RESUME|CLOSE|DROP <codice>` per un lavoro di un'altra chat, `LIMITS:`) nell'ultimo messaggio di una risposta; Quotient le legge alla fine della risposta, sommando il suo costo e contando ogni chiamata una volta sola.

**Lavoro e rilettura, esattamente.** Il testo che una chiamata manda al modello viene letto prima dalla cache, poi scritto nella cache, poi mandato come ingresso normale. Per ogni chiamata, la parte che la chat conteneva quando il lavoro è cominciato (dalla posizione 0 alla grandezza della prima chiamata del lavoro) si paga con quei pesi: è la rilettura; il resto del costo è il lavoro. Una chiamata dopo una compattazione, che è più corta, non aggiunge chat vecchia. I lavori misurati prima della 0.9.5 ricevono la loro divisione una volta sola dalla trascrizione della loro chat, se esiste ancora. I passi che un preventivo richiederà sono il suo lavoro corretto diviso il lavoro per passo imparato dai lavori finiti (30.000 token pesati finché non ce ne sono 3).

**Le rate.** Ognuna è un'esecuzione senza finestra (`claude -p`) nella cartella del lavoro, avviata dall'Utilità di pianificazione di Windows tramite un piccolo lanciatore in `~/.quotient`, così continua a funzionare dopo gli aggiornamenti del plugin. Un hook rifiuta ogni strumento tranne l'aggiornamento della consegna quando quello che è stato speso più i due passi successivi (la grandezza delle ultime chiamate, al massimo il 40% del tetto) arriverebbe al tetto del giorno, così i passi che chiudono la rata ci stanno dentro; prima, nell'ultimo 8% del tetto, rifiuta solo gli strumenti che cominciano lavoro nuovo (passano Write, Edit, MultiEdit, NotebookEdit, TodoWrite e un here-document scritto in un file), e uno strumento di un aiutante conta tutta la rata. Alla fine, se la rata si è fermata con degli aiutanti, le loro trascrizioni vengono elencate nella consegna con quante ricerche, pagine e letture ha fatto ognuno. `rate apart` è `rate new` con una rata sola e tutto il preventivo corretto come tetto, fatta partire subito in sottofondo, a parte dalla chat. Ogni rata tiene nella consegna una riga `PROGRESS: <n>%`; da lì Quotient dice quanto manca e quante rate. Il tetto del giorno comprende la rilettura dell'inizio di ogni rata, imparata dalle rate prima. Due rate dello stesso lavoro non partono mai insieme. Il lavoro ricorda la chat che l'ha creato (Claude Code passa il codice della chat ai comandi; se non lo fa, Quotient lo prende alla fine della risposta). La notifica usa il sistema di notifiche di Windows tramite PowerShell (su macOS `osascript`, su Linux `notify-send`) e non scrive file; `config rate.notify false` la spegne.

**Il tempo.** Il tempo di lavoro di un turno è la somma degli intervalli fra le sue voci una dopo l'altra (la trascrizione di Claude Code, o gli orari dei messaggi nell'archivio di Hermes), tranne l'intervallo prima di un tuo messaggio e quello prima della risposta alla finestra di scelta (`AskUserQuestion`, o `clarify` di Hermes). Un lavoro somma i suoi turni; il primo conta da `timer start` se Claude l'ha lanciato, se no dall'inizio del turno. Una rata lavora da sola, quindi il suo tempo è tutta la sua durata. Il tempo previsto è il lavoro corretto per la mediana dei minuti per milione di token pesati di lavoro degli ultimi 20 lavori dello stesso tipo (chat o rate) con il tempo misurato, e si mostra da quando ce ne sono 3. Gli hook tengono `~/.quotient/timer.json` (va, in pausa al tuo turno, finito); la finestra lo legge ogni secondo e scrive un segnale di vita, così se ne apre una sola.

**Chat lunghe.** Un plugin non può lanciare `/compact` (gli hook possono solo bloccare o guardare una compattazione), quindi la scelta diventa l'impostazione di Claude Code `autoCompactWindow`; la variabile `CLAUDE_CODE_AUTO_COMPACT_WINDOW`, se la imposti tu, vince su di lei. Un hook `PreCompact` annota la grandezza della chat prima del riassunto, e la fine della risposta dopo annota quella che resta; il risparmio è quella differenza, al prezzo della cache, a ogni chiamata successiva di quella chat (`compactions.jsonl`).

**I tuoi dati.** Tutto sta in `~/.quotient/` (o in `QUOTIENT_HOME`). `export` scrive le righe esatte che la condivisione manda. Le righe in attesa sono in `share-outbox.jsonl`; la media scaricata è `average.json`; i lavori aperti in una chat sono in `chat-jobs.json` (dimenticati dopo 7 giorni); le misure messe contro la settimana sono in `checks.jsonl`; i cambi di piano sono in `plan-changes.jsonl`; i nomi intorno a ogni lavoro sono in `env.jsonl` e i loro cambi in `env-changes.jsonl`; le riparazioni sono in `fix.jsonl`, con le copie fatte prima di ognuna in `fix/` e i lavori tolti in `jobs-excluded.jsonl`; la pagina con i grafici è `report.html`.

**La media condivisa.** Finché non hai 5 lavori tuoi, la media condivisa conta come 5 lavori al suo fattore (quello della tua famiglia di modello se ne ha almeno 5, se no quello di tutti), accanto ai tuoi. Dal quinto lavoro tuo in poi contano solo i tuoi.

**Prove.** `python -m unittest discover -s tests` (Quotient, senza internet) e `node --test server/test/stats.test.mjs` (i numeri del servizio). GitHub Actions le lancia a ogni push e pull request: le prove in Python su Windows e su Ubuntu con Python 3.9 e 3.13, quelle del servizio su Ubuntu.

</details>

## Domande frequenti

**Funziona con altre IA?**
Quotient è fatto per Claude Code: usa gli hook e le trascrizioni di Claude Code e i limiti del piano di Anthropic. Funziona anche dentro Hermes Agent quando Hermes usa Claude con il tuo login di Claude; lì conta solo le chat con Claude, perché gli altri fornitori non consumano il tuo piano. Altri assistenti non sono supportati.

**È uno strumento ufficiale di Anthropic?**
No. Quotient è un progetto open source indipendente di Francesco Candela. Non è affiliato ad Anthropic né approvato da Anthropic, e nemmeno da Nous Research, che fa Hermes Agent.

**E se Anthropic cambia i limiti?**
Le percentuali usate e gli orari di azzeramento arrivano da Anthropic a ogni lettura, quindi restano giusti, e Quotient non presume mai quanti token valga un limite. La stima di quanto vale l'1% la impara dalle letture che ha registrato: quando le ultime finestre si spostano tutte lontano nella stessa direzione, riparte a impararla da quelle, come dopo un cambio di piano (vedi [I tuoi limiti](#i-tuoi-limiti)); un cambio più piccolo sposta la stima piano piano, man mano che arrivano letture nuove. Se cambia la richiesta che c'è dietro `/usage`, la lettura diretta smette di funzionare finché Quotient non viene aggiornato, e restano le letture dalla riga di stato. Se cambiano le proporzioni dei prezzi delle API, i pesi sono impostazioni (per esempio `config weights.output 5`).

**Quanto sono precisi i preventivi?**
All'inizio poco. Ogni preventivo nuovo viene moltiplicato per un fattore di correzione: il rapporto mediano fra costo vero e stima negli ultimi 20 lavori finiti. Le rate hanno un fattore tutto loro, imparato solo dalle rate quando ce ne sono almeno 5. Finché non hai 5 lavori, la media condivisa conta come 5 lavori accanto ai tuoi. La parte del preventivo che viene dal rileggere la chat si calcola sui passi che i tuoi lavori hanno fatto davvero (Quotient misura quanti passi servono per ogni milione di token pesati di lavoro), non a occhio. `/token-quotient:report` mostra l'errore tipico prima della correzione e quello recente con la correzione, così vedi se si sta avvicinando. Il tempo previsto funziona allo stesso modo: i minuti per milione di token pesati di lavoro dei tuoi ultimi 20 lavori, per la stima corretta.

**Quotient consuma token anche lui?**
Sì, un poco: circa 2.800 token di regole all'inizio di una chat e una riga di circa 110 token a ogni messaggio in una chat lunga (circa 180 mentre è aperto un lavoro). Restano nella chat e vengono rilette, quindi Quotient le misura e le mostra nel resoconto.

**Funziona su macOS e Linux?**
Preventivi, misure, limiti e resoconto funzionano dove girano Claude Code, Python 3.8+ e `sh`. Svegliare il PC e rimetterlo a dormire funziona solo su Windows; su macOS e Linux Quotient ti dà la riga per programmare le rate tu, e le notifiche usano `osascript` o `notify-send`. Le prove automatiche girano su Windows e su Ubuntu.

## Roadmap

Le idee allo studio sono in [ROADMAP.md](ROADMAP.md). La prima, un preventivo anche del tempo con un cronometro dal vivo e un tempo che impara, è arrivata nella 1.1.0.

## Contribuire

Segnalazioni di errori, preventivi andati lontano dal vero e pull request sono benvenuti: vedi [CONTRIBUTING.md](CONTRIBUTING.md) (in inglese). Le prove si lanciano con `python -m unittest discover -s tests`, senza installare pacchetti. Chi partecipa segue il [codice di comportamento](CODE_OF_CONDUCT.md). I problemi di sicurezza si segnalano in privato, come spiegato in [SECURITY.md](SECURITY.md). I cambiamenti fra una versione e l'altra sono in [CHANGELOG.md](CHANGELOG.md).

## Sostieni il progetto

Quotient è gratuito, con licenza MIT. Se ti fa risparmiare una settimana di limiti:

- metti una stella al progetto, e parlane a chi sbatte sempre contro i limiti;
- apri una issue quando un preventivo è andato lontano dal vero: sono i casi veri a migliorarlo;
- sostieni il lavoro: GitHub Sponsors <!-- TODO: add link --> · Ko-fi <!-- TODO: add link -->

## Autore

Francesco Candela (Korvonordico). L'idea, la soglia, l'imparare dagli errori, le rate e il bilancio della settimana sono sue; il codice è scritto insieme a Claude.

## Licenza

[MIT](LICENSE)
