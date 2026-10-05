// The numbers part of the shared-average service: what a submitted job may contain,
// and how the average is computed. No I/O here, so it can be tested on its own.

export const FAMILIES = ["opus", "sonnet", "haiku", "fable", "other"];
export const FIELDS = ["v", "q", "family", "estimate", "actual"];
export const MIN_TOKENS = 1000;
export const MAX_TOKENS = 100000000;
// A real job is rarely 10 times off either way; wider values are refused (they could only poison).
export const MIN_RATIO = 0.1;
export const MAX_RATIO = 10;
export const MAX_BODY = 512;
// Nothing is published below this many jobs, in all and for each family: with few jobs the
// median is one of them, and a single job could be read in the file.
export const MIN_PUBLISH = 30;
// How many of the most recent jobs the average looks at.
export const WINDOW_FAMILY = 500;
export const WINDOW_ALL = 2000;
// A new average that moves more than this from the last published one needs many new jobs.
export const MAX_JUMP = 1.25;
export const JUMP_JOBS = 100;

const VERSION_RE = /^\d{1,3}\.\d{1,3}\.\d{1,3}$/;

// A submitted job: exactly these five fields, numbers in a plausible range, nothing else.
// Returns the row to store, or null.
export function validate(text) {
  if (typeof text !== "string" || text.length === 0 || text.length > MAX_BODY) return null;
  let body;
  try {
    body = JSON.parse(text);
  } catch {
    return null;
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) return null;
  const keys = Object.keys(body).sort();
  if (keys.length !== FIELDS.length || keys.join() !== [...FIELDS].sort().join()) return null;
  if (body.v !== 1) return null;
  if (typeof body.q !== "string" || !VERSION_RE.test(body.q)) return null;
  if (!FAMILIES.includes(body.family)) return null;
  for (const k of ["estimate", "actual"]) {
    const n = body[k];
    if (!Number.isInteger(n) || n < MIN_TOKENS || n > MAX_TOKENS) return null;
  }
  const ratio = body.actual / body.estimate;
  if (!(ratio >= MIN_RATIO && ratio <= MAX_RATIO)) return null;
  return { family: body.family, version: body.q, estimate: body.estimate, actual: body.actual };
}

function medianOf(sorted) {
  const n = sorted.length;
  if (!n) return null;
  const mid = Math.floor(n / 2);
  return n % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function quantile(sorted, q) {
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

// Two decimals: a correction factor needs no more, and more would describe single jobs.
const round2 = (x) => Math.round(x * 100) / 100;

// The typical real/estimate ratio of a set of jobs, or null below MIN_PUBLISH jobs. Ratios are
// compared on a log scale, so "twice too high" and "twice too low" weigh the same; jobs far from
// the rest (more than 3 robust standard deviations, never less than x1.5) are dropped first.
export function summarize(rows) {
  const logs = rows
    .map((r) => r.actual / r.estimate)
    .filter((r) => r >= MIN_RATIO && r <= MAX_RATIO)
    .map(Math.log)
    .sort((a, b) => a - b);
  if (logs.length < MIN_PUBLISH) return null;
  const med = medianOf(logs);
  const mad = medianOf(logs.map((x) => Math.abs(x - med)).sort((a, b) => a - b));
  const limit = Math.max(3 * 1.4826 * mad, Math.log(1.5));
  const kept = logs.filter((x) => Math.abs(x - med) <= limit);
  if (kept.length < MIN_PUBLISH) return null;
  return {
    jobs: logs.length,
    factor: round2(Math.exp(medianOf(kept))),
    p25: round2(Math.exp(quantile(kept, 0.25))),
    p75: round2(Math.exp(quantile(kept, 0.75))),
  };
}

export const METHOD =
  "factor = median of real cost / raw estimate over the most recent jobs (500 per model family, 2000 in all), " +
  "on a log scale, after dropping jobs more than 3 robust standard deviations (MAD) away from the median, " +
  "never closer than x1.5; rounded to 2 decimals. Nothing is published below 30 jobs, in all or for a family. " +
  "The file changes at most once a week and only after at least 20 new jobs, so someone who only watches it " +
  "cannot tell a single job apart. It is a best-effort average: anyone can send numbers, so it is bounded and " +
  "every copy of Quotient accepts it only between x0.25 and x4.";

// The file Quotient reads. byFamily: {family: rows}, all: rows. Null when there is not enough to publish.
export function buildAverage(byFamily, all, day) {
  const overall = summarize(all);
  if (!overall) return null;
  const families = {};
  for (const f of FAMILIES) {
    const s = summarize(byFamily[f] || []);
    if (s) families[f] = s;
  }
  return { schema: 1, updated: day, method: METHOD, all: overall, families };
}

// Whether a new average may replace the last published one: a big jump needs many new jobs,
// so a burst of false numbers cannot swing it.
export function mayReplace(previous, next, newJobs) {
  if (!next) return false;
  if (!previous || !previous.all) return true;
  const jump = Math.abs(Math.log(next.all.factor / previous.all.factor));
  return jump <= Math.log(MAX_JUMP) || newJobs >= JUMP_JOBS;
}
