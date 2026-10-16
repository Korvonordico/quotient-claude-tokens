"""v118: installments can learn their factor from all your jobs (learn_rate_all, off by default).
Run: python -m unittest discover tests"""

import os
import unittest
from unittest import mock

from test_quotient import Base, pv


class TestRateAll(Base):
    """16/10/2026, a walk-forward test on the author's 51 jobs: learned from all the jobs (chat jobs and installments)
    instead of the installments alone, the installments' typical miss went from 48% to 34%; nothing better was found
    for the chat jobs, whose factor does not change."""

    def add(self, session, raw, work, **extra):
        pv.append_jsonl(os.path.join(pv.home(), "jobs.jsonl"),
                        dict({"session": session, "raw_estimate": raw, "actual": work, "chat": 0, "work": work,
                              "finished": "2026-10-16T12:00:00+02:00"}, **extra))

    def setUp(self):
        super().setUp()
        pv.store(("learn_min_raw",), 1000000)
        pv.store(("learn_max_speed",), 3000)
        for i in range(5):
            self.add("rate:book%d" % i, 2000000, 1000000, seconds=2000)        # installments: x0.5
        for i in range(2):
            self.add("chat-big%d" % i, 2000000, 4000000, seconds=4000)         # chat jobs from 1M up: x2
        for i in range(4):
            self.add("chat-small%d" % i, 200000, 800000, seconds=100)          # small and too fast: x4, they teach nothing

    def test_off_by_default(self):
        self.assertEqual(pv.DEFAULTS["learn_rate_all"], 0)
        learned = pv.learning(pv.config(), "rate")
        self.assertAlmostEqual(learned["factor"], 0.5)                          # the installments alone
        self.assertFalse(learned["all"])
        self.assertEqual(learned["kind_jobs"], 5)

    def test_on_the_installments_learn_from_every_job(self):
        pv.store(("learn_rate_all",), 1)
        learned = pv.learning(pv.config(), "rate")
        # 11 jobs: x0.5 five times, x2 twice, x4 four times; the median is the 6th: x2. The small and fast chat jobs
        # count too: without them (the 7 jobs that teach) the median would be x0.5
        self.assertAlmostEqual(learned["factor"], 2.0)
        self.assertTrue(learned["all"])
        self.assertEqual(learned["kind_jobs"], 11)

    def test_the_chat_factor_does_not_change(self):
        cfg = pv.config()
        before = pv.learning(cfg)["factor"], pv.chat_factor(cfg, 1500000), pv.chat_factor(cfg, 600000)
        pv.store(("learn_rate_all",), 1)
        cfg = pv.config()
        self.assertEqual((pv.learning(cfg)["factor"], pv.chat_factor(cfg, 1500000), pv.chat_factor(cfg, 600000)), before)
        self.assertFalse(pv.learning(cfg)["all"])

    def test_the_last_history_window_jobs(self):
        pv.store(("learn_rate_all",), 1)
        pv.store(("history_window",), 3)
        for i in range(3):
            self.add("chat-late%d" % i, 1000000, 3000000, seconds=3000)        # the last three: x3
        self.assertAlmostEqual(pv.learning(pv.config(), "rate")["factor"], 3.0)

    def test_the_types_are_left_out(self):
        for i in range(3):
            self.add("rate:code%d" % i, 1000000, 3000000, seconds=3000, type="code")   # three code installments: x3
        cfg = pv.config()
        typed = pv.learning(cfg, "rate", "code")
        self.assertTrue(typed["typed"])
        self.assertAlmostEqual(typed["factor"], 3.0)
        pv.store(("learn_rate_all",), 1)
        learned = pv.learning(pv.config(), "rate", "code")
        self.assertFalse(learned["typed"])
        self.assertEqual(learned["type_jobs"], 0)
        # 14 jobs: x0.5 five times, x2 twice, x3 three times, x4 four times: the median of the 7th and 8th, x2 and x3
        self.assertAlmostEqual(learned["factor"], 6 ** 0.5)

    def test_each_job_before_is_corrected_the_same_way(self):
        # the report's rows: each installment corrected with the factor of all the jobs before it
        self.add("rate:last", 1000000, 1000000, seconds=1000)
        pv.store(("learn_rate_all",), 1)
        row = pv.learning(pv.config(), "rate")["rows"][-1]
        self.assertAlmostEqual(row["factor_before"], 2.0)
        self.assertAlmostEqual(row["corrected"], 2000000)
        pv.store(("learn_rate_all",), 0)
        self.assertAlmostEqual(pv.learning(pv.config(), "rate")["rows"][-1]["factor_before"], 0.5)

    def test_the_rate_plan_uses_it(self):
        pv.store(("learn_rate_all",), 1)
        nums = pv.quote_numbers(pv.config(), {"max": 1000000}, "rate")
        self.assertAlmostEqual(nums["rows"][0]["work"], 2000000, delta=1)

    def test_the_quote_and_the_report_say_it(self):
        pv.store(("learn_rate_all",), 1)
        cfg = pv.config()
        it = pv.quote_table(cfg, {"good": 1000000, "max": 2000000}, kind="rate", lang="it")
        self.assertIn("x2.00, da 11 lavori, chat e rate", it)
        en = pv.quote_table(cfg, {"good": 1000000, "max": 2000000}, kind="rate", lang="en")
        self.assertIn("from 11 jobs, chat jobs and installments", en)
        said = self.run_hook(lambda: pv.report(mock.Mock(html=False)), {})
        self.assertIn("Installments learn from all your jobs (learn_rate_all): x2.00 (from the last 11)", said)
        pv.store(("learn_rate_all",), 0)
        self.assertIn("da 5 lavori a rate", pv.quote_table(pv.config(), {"good": 1000000, "max": 2000000},
                                                           kind="rate", lang="it"))


if __name__ == "__main__":
    unittest.main()
