// The numbers part of the shared-average service: what a submitted job may contain,
// and how the average is computed. No I/O here, so it can be tested on its own.

export const FAMILIES = ["opus", "sonnet", "haiku", "fable", "other"];
export const FIELDS = ["v", "q", "family", "estimate", "actual"];
// 1.1.6: two optional fields. `plan` only when the user chose it in Quotient's settings; `per_point` is how many
// weighted tokens 1% of the week held on that user's PC, rounded to 3 significant digits. 1.1.7: `per_point_5h`, the same
// for the 5-hour window.
export const OPTIONAL = ["plan", "per_point", "per_point_5h"];
export const PLANS = ["pro", "max5", "max20", "other"];
export const MIN_PER_POINT = 10000;
export const MAX_PER_POINT = 1000000000;
// 1.1.7: the 5 hours hold about a tenth of the week (the author's PC: 409k weighted tokens in 1% against 3.58M), so a
// tenth of the week's range: wide enough for any plan, narrow enough to refuse what cannot be a real size.
export const MIN_PER_POINT_5H = 1000;
export const MAX_PER_POINT_5H = 100000000;
// The plausible range of each size, by field.
const RANGES = { per_point: [MIN_PER_POINT, MAX_PER_POINT], per_point_5h: [MIN_PER_POINT_5H, MAX_PER_POINT_5H] };
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

// A submitted job: these five fields, and from 1.1.6 at most the optional ones (plan, per_point; 1.1.7 per_point_5h);
// numbers in a plausible range, nothing else. Returns the row to store (the optional ones null when not sent), or null.
export function validate(text) {
  if (typeof text !== "string" || text.length === 0 || text.length > MAX_BODY) return null;
  let body;
  try {
    body = JSON.parse(text);
  } catch {
    return null;
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) return null;
  const keys = Object.keys(body);
  if (!FIELDS.every((k) => keys.includes(k))) return null;
  if (!keys.every((k) => FIELDS.includes(k) || OPTIONAL.includes(k))) return null;
  if (body.v !== 1) return null;
  if (typeof body.q !== "string" || !VERSION_RE.test(body.q)) return null;
  if (!FAMILIES.includes(body.family)) return null;
  for (const k of ["estimate", "actual"]) {
    const n = body[k];
    if (!Number.isInteger(n) || n < MIN_TOKENS || n > MAX_TOKENS) return null;
  }
  const ratio = body.actual / body.estimate;
  if (!(ratio >= MIN_RATIO && ratio <= MAX_RATIO)) return null;
  if ("plan" in body && !PLANS.includes(body.plan)) return null;
  for (const [k, [min, max]] of Object.entries(RANGES)) {
    if (!(k in body)) continue;
    const n = body[k];
    if (!Number.isInteger(n) || n < min || n > max) return null;
  }
  return {
    family: body.family, version: body.q, estimate: body.estimate, actual: body.actual,
    plan: "plan" in body ? body.plan : null, per_point: "per_point" in body ? body.per_point : null,
    per_point_5h: "per_point_5h" in body ? body.per_point_5h : null,
  };
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

// 3 significant digits, as Quotient rounds the numbers it sends.
const round3 = (x) => {
  const n = Math.round(x);
  const step = 10 ** Math.max(0, String(Math.abs(n)).length - 3);
  return Math.round(n / step) * step;
};

// 1.1.6: how many weighted tokens 1% of the week holds for one plan: the median of the jobs that sent it (each job
// carries its user's learned value), with the middle half; null below MIN_PUBLISH jobs. Values far from the rest are
// dropped as in summarize. 1.1.7: field "per_point_5h" does the same for the 5 hours, with the same rules.
export function summarizePlan(rows, field = "per_point") {
  const [min, max] = RANGES[field];
  const logs = rows
    .map((r) => r[field])
    .filter((n) => Number.isInteger(n) && n >= min && n <= max)
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
    per_point: round3(Math.exp(medianOf(kept))),
    p25: round3(Math.exp(quantile(kept, 0.25))),
    p75: round3(Math.exp(quantile(kept, 0.75))),
  };
}

export const PLAN_METHOD =
  "per plan (only from jobs whose users chose their plan): the median of the weighted tokens 1% of the week held on " +
  "their PCs, on a log scale, after the same trimming; rounded to 3 significant digits, from 30 jobs.";
export const PLAN_METHOD_5H =
  "From 1.1.7 the same for the 5-hour window, on its own (jobs_5h, per_point_5h, p25_5h, p75_5h): the median of the " +
  "weighted tokens 1% of the 5 hours held, from the jobs that sent it, from 30 jobs.";

// The file Quotient reads. byFamily: {family: rows}, all: rows, byPlan (1.1.6): {plan: rows with per_point}, byPlan5h
// (1.1.7): {plan: rows with per_point_5h}. Null when there is not enough to publish. `plans` is there only when a plan
// has enough jobs, so older copies read it as before; the 5 hours go in keys of their own (jobs_5h, per_point_5h, p25_5h,
// p75_5h), which a 1.1.6 copy does not read, and each window is published only when it has its 30 jobs: with no 5-hour
// numbers the file is the same as 1.1.6's.
export function buildAverage(byFamily, all, day, byPlan = {}, byPlan5h = {}) {
  const overall = summarize(all);
  if (!overall) return null;
  const families = {};
  for (const f of FAMILIES) {
    const s = summarize(byFamily[f] || []);
    if (s) families[f] = s;
  }
  const plans = {};
  let week = false;
  let five = false;
  for (const p of PLANS) {
    const s = summarizePlan(byPlan[p] || []);
    const s5 = summarizePlan(byPlan5h[p] || [], "per_point_5h");
    if (s) {
      plans[p] = s;
      week = true;
    }
    if (s5) {
      plans[p] = { ...(plans[p] || {}), jobs_5h: s5.jobs, per_point_5h: s5.per_point, p25_5h: s5.p25, p75_5h: s5.p75 };
      five = true;
    }
  }
  const avg = { schema: 1, updated: day, method: METHOD, all: overall, families };
  if (Object.keys(plans).length) {
    avg.plans = plans;
    avg.method = [METHOD, week ? PLAN_METHOD : "", five ? PLAN_METHOD_5H : ""].filter(Boolean).join(" ");
  }
  return avg;
}

// Whether a new average may replace the last published one: a big jump needs many new jobs,
// so a burst of false numbers cannot swing it.
export function mayReplace(previous, next, newJobs) {
  if (!next) return false;
  if (!previous || !previous.all) return true;
  const jump = Math.abs(Math.log(next.all.factor / previous.all.factor));
  return jump <= Math.log(MAX_JUMP) || newJobs >= JUMP_JOBS;
}
