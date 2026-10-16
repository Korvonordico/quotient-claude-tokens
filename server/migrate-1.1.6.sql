-- 1.1.6: the plan (only if the user chose it) and the size of 1% of the week, for a database made before 1.1.6.
-- Run once, before deploying the 1.1.6 worker:
--   cd server && npx wrangler d1 execute quotient-share --remote --file migrate-1.1.6.sql
-- Old rows keep NULL in both: they still count in the averages by family as before.
ALTER TABLE jobs ADD COLUMN plan TEXT;
ALTER TABLE jobs ADD COLUMN per_point INTEGER;
CREATE INDEX IF NOT EXISTS jobs_plan ON jobs (plan, id);
