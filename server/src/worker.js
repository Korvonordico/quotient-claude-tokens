// Quotient's shared-average service (a Cloudflare Worker).
//
// It receives one line of numbers per finished job, keeps no address, no date and no
// identity, and at most once a week publishes the average in its own public repository
// (Korvonordico/quotient-data, average.json), where every copy of Quotient reads it.
//
// Routes:
//   POST /v1/jobs     one job: {"v":1,"q":"0.9.0","family":"opus","estimate":225000,"actual":259000}
//   GET  /v1/average  the last published average (the same file as on GitHub)
//   GET  /            what this service keeps and how the average is made
//
// This code never reads the client's address or any header other than the body size,
// and request logging is off (observability.enabled = false in wrangler.toml).

import { validate, buildAverage, mayReplace, FAMILIES, WINDOW_FAMILY, WINDOW_ALL, MAX_BODY, METHOD } from "./stats.js";

// Written here, not in variables, so that no setting can make the service write anywhere else.
const GITHUB_REPO = "Korvonordico/quotient-data";
const GITHUB_PATH = "average.json";
const GITHUB_BRANCH = "main";
const REPO_URL = "https://github.com/Korvonordico/quotient-claude-tokens";
const DATA_URL = "https://github.com/Korvonordico/quotient-data";
// At least this many new jobs, and this many days, between two publications.
const MIN_NEW = 20;
const MIN_DAYS = 7;
const KEEP_ROWS = 5000;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    try {
      if (url.pathname === "/v1/jobs") {
        if (request.method !== "POST") return text("POST only\n", 405);
        const res = await receive(request, env);
        if (res.status === 204) ctx.waitUntil(daily(env, "arrival").catch(() => null));
        return res;
      }
      if (url.pathname === "/v1/average" && request.method === "GET") {
        const avg = await getMeta(env, "average");
        return new Response(avg || "{}\n", {
          headers: { "content-type": "application/json; charset=utf-8", "cache-control": "public, max-age=300" },
        });
      }
      if (url.pathname === "/" && request.method === "GET") return await page(env);
      return text("not found\n", 404);
    } catch (e) {
      // Only the error's own message, never the request: seen live with `wrangler tail`, not stored.
      console.error("quotient-share error: " + String((e && e.message) || e));
      return text("error\n", 500);
    }
  },

  async scheduled(event, env, ctx) {
    ctx.waitUntil(daily(env, "cron"));
  },
};

function text(body, status) {
  return new Response(body, { status, headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" } });
}

// The body, read up to MAX_BODY + 1 bytes whatever the declared length; null if longer.
async function readBody(request) {
  if (!request.body) return "";
  const reader = request.body.getReader();
  const chunks = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_BODY) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  const all = new Uint8Array(size);
  let at = 0;
  for (const c of chunks) {
    all.set(c, at);
    at += c.byteLength;
  }
  return new TextDecoder().decode(all);
}

// One counter row per kind (the current minute, the current day), overwritten when the period
// changes. When the cap is reached the update does not happen, so a flood writes nothing.
const BUMP =
  "INSERT INTO counters (kind, at, n) VALUES (?1, ?2, 1) ON CONFLICT (kind) DO UPDATE SET " +
  "n = CASE WHEN counters.at = excluded.at THEN counters.n + 1 ELSE 1 END, at = excluded.at " +
  "WHERE counters.at <> excluded.at OR counters.n < ?3 RETURNING n";

async function bump(env, kind, at, cap) {
  const row = await env.DB.prepare(BUMP).bind(kind, at, cap).first();
  return Boolean(row);
}

async function receive(request, env) {
  if (Number(request.headers.get("content-length") || 0) > MAX_BODY) return text("too big\n", 413);
  const body = await readBody(request);
  if (body === null) return text("too big\n", 413);
  const row = validate(body);
  if (!row) return text("only the five numbers fields are accepted\n", 400);

  // Global caps, the same for everybody: they count arrivals, not who sends them.
  const perMinute = Number(env.PER_MINUTE) || 20;
  const perDay = Number(env.PER_DAY) || 300;
  const minute = Math.floor(Date.now() / 60000);
  if (!(await bump(env, "minute", minute, perMinute))) return text("busy, try later\n", 429);
  if (!(await bump(env, "day", Math.floor(minute / 1440), perDay))) return text("busy, try tomorrow\n", 429);

  await env.DB.prepare("INSERT INTO jobs (family, version, estimate, actual) VALUES (?1, ?2, ?3, ?4)")
    .bind(row.family, row.version, row.estimate, row.actual)
    .run();
  return new Response(null, { status: 204, headers: { "cache-control": "no-store" } });
}

async function getMeta(env, key) {
  const row = await env.DB.prepare("SELECT value FROM meta WHERE key = ?1").bind(key).first();
  return row ? row.value : null;
}

function setMeta(env, key, value) {
  return env.DB.prepare("INSERT INTO meta (key, value) VALUES (?1, ?2) ON CONFLICT (key) DO UPDATE SET value = ?2")
    .bind(key, String(value));
}

// The daily work: by the timer, or when a job arrives (then at most once an hour, so the
// average does not depend on the timer alone). Keeps only the most recent rows; after at
// least MIN_NEW new jobs and MIN_DAYS days, computes the average and publishes it.
export async function daily(env, source) {
  const hour = Math.floor(Date.now() / 3600000);
  const day = Math.floor(hour / 24);
  if (source === "cron") {
    await setMeta(env, "last_cron", new Date().toISOString().slice(0, 10)).run();
  } else if (Number((await getMeta(env, "last_run")) || -1) === hour) {
    return "ran this hour";
  }
  await setMeta(env, "last_run", hour).run();

  await env.DB.prepare(
    "DELETE FROM jobs WHERE id <= (SELECT id FROM jobs ORDER BY id DESC LIMIT 1 OFFSET ?1)").bind(KEEP_ROWS).run();

  const lastId = Number((await getMeta(env, "last_id")) || 0);
  const lastDay = Number((await getMeta(env, "last_day")) || 0);
  const top = await env.DB.prepare("SELECT MAX(id) AS id FROM jobs").first();
  const maxId = (top && top.id) || 0;

  if (maxId - lastId >= MIN_NEW && day - lastDay >= MIN_DAYS) {
    const byFamily = {};
    for (const f of FAMILIES) {
      const { results } = await env.DB.prepare(
        "SELECT estimate, actual FROM jobs WHERE family = ?1 AND id <= ?2 ORDER BY id DESC LIMIT ?3")
        .bind(f, maxId, WINDOW_FAMILY).all();
      byFamily[f] = results;
    }
    const { results: all } = await env.DB.prepare(
      "SELECT estimate, actual FROM jobs WHERE id <= ?1 ORDER BY id DESC LIMIT ?2")
      .bind(maxId, WINDOW_ALL).all();
    const next = buildAverage(byFamily, all, new Date().toISOString().slice(0, 10));
    const prevRaw = await getMeta(env, "average");
    const previous = prevRaw ? JSON.parse(prevRaw) : null;
    if (!next) return "not enough jobs yet";
    if (!mayReplace(previous, next, maxId - lastId)) {
      await setMeta(env, "held", "jump too big for the number of new jobs").run();
      return "held";
    }
    const json = JSON.stringify(next, null, 1) + "\n";
    await env.DB.batch([setMeta(env, "average", json), setMeta(env, "last_id", maxId),
      setMeta(env, "last_day", day), setMeta(env, "pending_publish", 1), setMeta(env, "held", "")]);
    return await publish(env, json);
  }
  if ((await getMeta(env, "pending_publish")) === "1") {
    const json = await getMeta(env, "average");
    if (json) return await publish(env, json);
  }
  return "nothing new";
}

async function publish(env, json) {
  if (!env.GITHUB_TOKEN) return "no GitHub token: average kept here only";
  const api = `https://api.github.com/repos/${GITHUB_REPO}/contents/${GITHUB_PATH}`;
  const headers = {
    authorization: `Bearer ${env.GITHUB_TOKEN}`,
    accept: "application/vnd.github+json",
    "x-github-api-version": "2022-11-28",
    "user-agent": "quotient-share",
  };
  const current = await fetch(`${api}?ref=${GITHUB_BRANCH}`, { headers });
  let sha;
  if (current.ok) {
    const info = await current.json();
    sha = info.sha;
    if (decodeBase64(info.content || "") === json) {
      await setMeta(env, "pending_publish", 0).run();
      return "already published";
    }
  } else if (current.status !== 404) {
    return `GitHub read failed: ${current.status}`;
  }
  const avg = JSON.parse(json);
  const put = await fetch(api, {
    method: "PUT",
    headers: { ...headers, "content-type": "application/json" },
    body: JSON.stringify({
      message: `Shared average: ${avg.all.jobs} jobs`,
      content: encodeBase64(json),
      branch: GITHUB_BRANCH,
      ...(sha ? { sha } : {}),
    }),
  });
  if (!put.ok) return `GitHub write failed: ${put.status}`;
  await setMeta(env, "pending_publish", 0).run();
  return "published";
}

function encodeBase64(s) {
  const bytes = new TextEncoder().encode(s);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

function decodeBase64(s) {
  const bin = atob(s.replace(/\s/g, ""));
  const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
}

async function page(env) {
  const raw = await getMeta(env, "average");
  let avg = null;
  try {
    avg = raw ? JSON.parse(raw) : null;
  } catch {
    avg = null;
  }
  const rows = avg
    ? [["all", avg.all], ...Object.entries(avg.families || {})]
        .filter(([, s]) => s)
        .map(([f, s]) => `<tr><td>${escapeHtml(f)}</td><td>${Number(s.jobs)}</td><td>x${Number(s.factor)}</td><td>x${Number(s.p25)} – x${Number(s.p75)}</td></tr>`)
        .join("")
    : "";
  const table = avg
    ? `<p>Last average: ${escapeHtml(avg.updated)}.</p><table><tr><th>Model family</th><th>Jobs</th><th>Factor</th><th>Middle half</th></tr>${rows}</table>`
    : "<p>No average yet: the first one is published after 30 jobs.</p>";
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quotient shared average</title>
<style>body{font:16px/1.5 system-ui,sans-serif;max-width:46rem;margin:2rem auto;padding:0 1rem;color:#222;background:#fff}
code,pre{background:#f3f3f3;border-radius:4px;padding:.1rem .3rem}pre{padding:.6rem;overflow:auto}
table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:.3rem .6rem;text-align:left}
@media (prefers-color-scheme:dark){body{color:#ddd;background:#161616}code,pre{background:#262626}td,th{border-color:#444}}</style></head><body>
<h1>Quotient shared average</h1>
<p><a href="${REPO_URL}">Quotient</a> estimates the token cost of a Claude Code job before it starts. Each copy learns from its own errors; this service lets new users start from everyone's real numbers instead of from zero.</p>
<h2>What it receives</h2>
<p>One line per finished job, exactly like this:</p>
<pre>{"v":1,"q":"0.9.0","family":"opus","estimate":225000,"actual":259000}</pre>
<p>Format version, Quotient version, model family (opus, sonnet, haiku, fable, other), the raw estimate and the real cost in weighted tokens, rounded to 3 significant digits. Anything else is refused.</p>
<h2>What it never keeps</h2>
<p>No IP address, no date or time of a job, no names, text, paths, session or user ids. The code does not read the sender's address, and request logs are turned off. Two arrival counters (this minute, this day) refuse floods and are overwritten, so no history of arrival times is kept. Cloudflare, which runs this service, carries the connection like any network and keeps automatic backups of the database: see <a href="https://www.cloudflare.com/privacypolicy/">its privacy policy</a>.</p>
<h2>How the average is made</h2>
<p>${escapeHtml(METHOD)}</p>
${table}
<p>The same file is published in its own repository, <a href="${DATA_URL}">quotient-data</a> (<a href="${DATA_URL}/blob/main/average.json">average.json</a>, with its history): the service's key can write only there, never in Quotient's code. The code of this service is in <a href="${REPO_URL}/tree/main/server">server/</a>. Sharing can be turned off in Quotient (<code>/quotient:share off</code>); people who turn it off still get the average. Details: <a href="${REPO_URL}/blob/main/PRIVACY.md">PRIVACY.md</a>.</p>
</body></html>`;
  return new Response(html, { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "public, max-age=300" } });
}
