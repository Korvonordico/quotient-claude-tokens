-- 1.1.7: the size of 1% of the 5 hours (per_point_5h), for a database made before 1.1.7 (after migrate-1.1.6.sql).
-- Run once, before deploying the 1.1.7 worker:
--   cd server && npx wrangler d1 execute quotient-share --remote --file migrate-1.1.7.sql
-- Old rows keep NULL: they still count as before, by family and in the week's size by plan.
ALTER TABLE jobs ADD COLUMN per_point_5h INTEGER;
