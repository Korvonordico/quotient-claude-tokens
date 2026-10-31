"""1.2.2: an installment's start (rate.start_fixed, rate.min_cap_starts). Each installment is a new Claude Code session
whose first call writes its start (system, tools, rules) to the cache, about 100k wt before any work: quotes and caps
count it once per installment, and a cap too small to get past it is raised (19/10/2026: a 99k cap, 139k spent just
starting, nothing done). Run: python -m unittest discover tests"""

import os
import unittest
from unittest import mock

from q_patch import patch_q

from test_quotient import Base, pv, usage

NEW = {"start_fixed": 1, "min_cap_starts": 1.5}


class V122(Base):
    def setUp(self):
        super().setUp()
        on = mock.patch.dict(pv.DEFAULTS["rate"], NEW)
        on.start()
        self.addCleanup(on.stop)
        pv.store(("chat", "installment_start"), 50000)   # the tests' settings start from 0

    def add_runs(self, rows, job="other"):
        folder = pv.rate_dir(job)
        os.makedirs(folder, exist_ok=True)
        for i, r in enumerate(rows):
            pv.append_jsonl(os.path.join(folder, "runs.jsonl"), dict({"started": "2026-10-19T1%d:00:00" % i}, **r))

    def new_job(self, name="post", **kw):
        args = mock.Mock(dir=self.dir, task="write the post", task_file=None, days=None, daily=None, quote=None,
                         model=None, after="nothing", template=None, pace=None, at=None, type=None, apart=False,
                         session=None)
        args.name = name
        for k, v in kw.items():
            setattr(args, k, v)
        said = self.run_hook(lambda: pv.rate_new(args), {})
        return pv.load_json(os.path.join(pv.rate_dir(name), "job.json"), None), said


class TestDefaults(Base):
    def test_shipped_defaults(self):
        # Base patches them for the older tests: read the module's own values from a fresh import of the source
        import importlib.util
        spec = importlib.util.spec_from_file_location("q122", pv.q_settings.__file__)
        fresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fresh)
        for key, value in NEW.items():
            self.assertEqual(fresh.DEFAULTS["rate"][key], value, key)


class TestStartCost(V122):
    def test_the_start_of_one_run(self):
        cfg = pv.config()
        self.assertEqual(pv.run_start_cost(cfg, {"start_wt": 90000, "chat": 1, "fresh": 1, "calls": 9}), 90000)
        # before 1.2.2: the re-reading of the start minus reading it from the cache at each later call
        self.assertAlmostEqual(pv.run_start_cost(cfg, {"chat": 122000, "fresh": 66000, "calls": 4}), 102200)
        self.assertIsNone(pv.run_start_cost(cfg, {"chat": 122000}))

    def test_learned_from_the_runs_or_the_settings(self):
        cfg = pv.config()
        self.assertEqual(pv.installment_start_cost(cfg), 50000 * 2.0)   # the start written to the one-hour cache
        self.add_runs([{"wt": 312000, "chat": 121000, "start_wt": 90000},
                       {"wt": 600000, "chat": 200000, "start_wt": 110000}])
        self.assertEqual(pv.installment_start_cost(pv.config()), 100000)
        off = pv.config()
        off["rate"] = dict(off["rate"], start_fixed=0)
        self.assertEqual(pv.installment_start_cost(off), 0)
        self.assertEqual(pv.cap_floor(pv.config()), 1.5 * 110000)   # the largest recent start, for a cold one

    def test_the_share_leaves_the_start_out(self):
        self.add_runs([{"wt": 312000, "chat": 121000, "start_wt": 100000},
                       {"wt": 600000, "chat": 200000, "start_wt": 100000}])
        self.assertAlmostEqual(pv.installment_overhead(pv.config()), (21000 / 191000 + 100000 / 400000) / 2)
        off = pv.config()
        off["rate"] = dict(off["rate"], start_fixed=0)
        self.assertAlmostEqual(pv.installment_overhead(off), (121000 / 191000 + 200000 / 400000) / 2)


class TestQuotes(V122):
    def test_a_quote_counts_one_start(self):
        nums = pv.quote_numbers(pv.config(), {"good": 120000}, "rate")
        row = nums["rows"][0]
        self.assertEqual(nums["start"], 100000)
        self.assertAlmostEqual(row["chat"], row["work"] * nums["overhead"] + 100000)
        self.assertAlmostEqual(row["total"], row["work"] + row["chat"])

    def test_each_day_pays_its_own_start(self):
        cfg = pv.config()
        rows = pv.quote_numbers(cfg, {"good": 1200000}, "rate")["rows"]
        option = next(o for o in pv.pace_options(cfg, {"good": 1200000}, 1, "rate") if o.get("days") == 2)
        self.assertAlmostEqual(option["daily"][0][1], (rows[0]["total"] - 100000) / 2 + 100000)

    def test_the_table_says_it(self):
        text = pv.quote_table(pv.config(), {"good": 120000}, "rate", lang="it")
        self.assertIn("Partenza e rilettura delle rate", text)
        self.assertIn("solo per partire", text)


class TestCaps(V122):
    def test_the_cap_pays_the_start(self):
        job, _ = self.new_job(quote=120000, days=1)
        share = job["overhead_at_quote"]
        self.assertEqual(job["start_at_quote"], 100000)
        self.assertAlmostEqual(job["daily_cap"], 120000 * job["factor_at_quote"] * (1 + share) + 100000, delta=200)

    def test_a_cap_too_small_to_start_is_raised(self):
        job, said = self.new_job(daily=99000)
        self.assertEqual(job["daily_cap"], 150000)
        self.assertIn("Cap raised", said)
        args = mock.Mock(daily=120000, per_day=None, days=None)
        args.name = "post"
        said = self.run_hook(lambda: pv.rate_set(args), {})
        self.assertEqual(pv.load_json(os.path.join(pv.rate_dir("post"), "job.json"), None)["daily_cap"], 150000)
        self.assertIn("Cap raised", said)

    def test_the_time_of_an_installment_leaves_the_start_out(self):
        job = {"daily_cap": 250000, "start_at_quote": 100000, "overhead_at_quote": 0.5}
        with patch_q(pv, "minutes_per_million", return_value=(10.0, 3)):
            self.assertAlmostEqual(pv.installment_seconds(pv.config(), job), 60.0)

    def test_a_week_too_full_to_start_skips_the_installment(self):
        self.new_job(daily=300000)
        args = mock.Mock(force=True, woke=None)
        args.name = "post"
        with patch_q(pv, "find_claude", return_value="claude"), \
                patch_q(pv, "week_room", return_value=120000), \
                patch_q(pv, "subprocess") as sub:
            said = self.run_hook(lambda: pv.run_installment(args), {})
        self.assertIn("skipped", said)
        self.assertFalse(sub.run.called or sub.Popen.called)
        self.assertEqual(pv.load_json(os.path.join(pv.rate_dir("post"), "job.json"), None)["last_skip"]["room"],
                         120000)


class TestReserve(V122):
    """19/10/2026: the reserve that closes an installment counted the first call's start as a step, and a 155k
    installment refused its first read after the start alone (103k)."""

    def test_the_start_is_not_a_step(self):
        cfg = pv.config()
        first = usage(inp=8, write=54000, read=12000, output=500, write_1h=54000)
        self.assertGreater(pv.step_weight(first, cfg), 100000)
        self.assertAlmostEqual(pv.step_weight(first, cfg, first=True), 66008 * 0.1 + 500 * 5)
        off = dict(cfg, rate=dict(cfg["rate"], start_fixed=0))
        self.assertEqual(pv.step_weight(first, off, first=True), pv.step_weight(first, off))

    def test_a_read_after_the_start_passes(self):
        self.new_job(daily=155000)
        self.t.user("installment")
        self.t.call("c0", usage(inp=8, write=54000, read=12000, output=500, write_1h=54000), tools=1)   # ~113k wt
        self.t.tool_result()
        with mock.patch.dict(os.environ, {"QUOTIENT_JOB": "post"}):
            said = self.run_hook(pv.hook_pretool, {"transcript_path": self.t.path, "tool_name": "Read",
                                                   "tool_input": {"file_path": "README.md"}})
        self.assertEqual(said, "")


if __name__ == "__main__":
    unittest.main()
