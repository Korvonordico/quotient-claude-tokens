-- The service's database (Cloudflare D1). No dates of jobs, no addresses, no identities.

-- One row per finished job: only the numbers a copy of Quotient sends. The id only keeps the
-- order of arrival, so the average can look at the most recent jobs; the version is kept so that
-- the numbers of a faulty Quotient version could be dropped. Only the most recent 5,000 are kept.
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  family TEXT NOT NULL,
  version TEXT NOT NULL,
  estimate INTEGER NOT NULL,
  actual INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_family ON jobs (family, id);

-- Two global arrival counters, for everybody together, used only to refuse floods: one row for
-- the current minute and one for the current day, overwritten when the minute or the day changes.
-- No history of arrival times is kept.
CREATE TABLE IF NOT EXISTS counters (
  kind TEXT PRIMARY KEY,
  at INTEGER NOT NULL,
  n INTEGER NOT NULL
);

-- The last average and where it got to.
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
