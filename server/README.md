# Quotient shared-average service

A small [Cloudflare Worker](https://developers.cloudflare.com/workers/) that collects the numbers of finished Quotient jobs, with no identity, and publishes their average as `average.json` in a separate repository, [Korvonordico/quotient-data](https://github.com/Korvonordico/quotient-data). It is separate so that the service's GitHub key can write only that file's repository, never Quotient's code (a GitHub token cannot be limited to one file).

Everything it receives, keeps and publishes is described in [PRIVACY.md](../PRIVACY.md). This folder is public so that anyone can check it.

## What it does

| Route | What |
|---|---|
| `POST /v1/jobs` | one finished job: `{"v":1,"q":"0.9.0","family":"opus","estimate":225000,"actual":259000}`. Exactly these five fields, numbers in a plausible range; anything else gets `400`. Global caps (20 a minute, 300 a day, for everybody together) answer `429`; a full cap writes nothing. |
| `GET /v1/average` | the last published average, the same file as `average.json` in quotient-data |
| `GET /` | a short page: what is kept, how the average is made, the current numbers |

Once a day (03:17 UTC), and when a job arrives (at most once an hour), it keeps only the most recent 5,000 lines and, **only after at least 20 new jobs and 7 days since the last one, with at least 30 jobs in all**, computes a new average and commits it to `average.json` in quotient-data through the GitHub API. A new average that jumps more than 25% needs at least 100 new jobs. Someone who only watches the file cannot tell a single job apart; someone who sends false lines could learn roughly on which side of the average one job falls.

The average: for each model family and for all jobs together, the median of real cost / raw estimate on a log scale, after dropping jobs more than 3 robust standard deviations (MAD) away, never closer than x1.5, rounded to 2 decimals. A family is listed on its own from 30 jobs. See `src/stats.js`.

## What it never keeps

No IP address, no dates or times, no names, text, paths, session or user ids. The code never reads the sender's address, and Workers request logs are turned off in `wrangler.toml` (`observability.enabled = false`; Cloudflare turns them on by default for new Workers).

## Deploy your own

Needs a free Cloudflare account and Node.js.

```sh
cd server
npx wrangler login
npx wrangler d1 create quotient-share          # put the id it prints in wrangler.toml
npx wrangler d1 execute quotient-share --remote --file schema.sql
npx wrangler secret put GITHUB_TOKEN           # fine-grained token: Contents read and write, the data repository only
npx wrangler deploy
```

Then set Quotient's endpoint: `quotient config share.endpoint https://quotient-share.<your-subdomain>.workers.dev`.

## Test

```sh
node --test server/test/stats.test.mjs         # the numbers: what is accepted, how the average is made
cd server && npx wrangler dev --local --test-scheduled   # the whole service on your PC, with a local database
```
