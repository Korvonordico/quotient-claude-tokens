"""1.1.9: the chat factor learns from the clean jobs only (learn_clean_only), new users start from the factor of the
49 clean jobs of docs/evidence (start_factor 0.58), and a task added to a job gets a quote of its own
(requote_on_addition, now on). Run: python -m unittest discover tests"""

import math
import os
import unittest
from unittest import mock

from test_quotient import Base, pv

NEW = {"learn_clean_only": 1, "start_factor": 0.58, "requote_on_addition": 1, "clean_max_turns": 1,
       "writing_wt_per_word": 27, "start_factors": {"code": 0.70, "research": 0.35, "writing": 1.0, "other": 0.40}}


class V119(Base):
    def setUp(self):
        super().setUp()
        on = mock.patch.dict(pv.DEFAULTS, NEW)   # the defaults of 1.1.9 (Base keeps the older tests on 1.1.8's)
        on.start()
        self.addCleanup(on.stop)

    def add(self, session, raw, work, **extra):
        pv.append_jsonl(os.path.join(pv.home(), "jobs.jsonl"),
                        dict({"session": session, "raw_estimate": raw, "actual": work, "chat": 0, "work": work,
                              "finished": "2026-10-19T12:00:00+02:00"}, **extra))


class TestDefaults(Base):
    def test_shipped_defaults(self):
        # Base patches them for the older tests: read the module's own values from a fresh import of the source
        import importlib.util
        spec = importlib.util.spec_from_file_location("q119", pv.__file__)
        fresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fresh)
        for key, value in NEW.items():
            self.assertEqual(fresh.DEFAULTS[key], value, key)
        self.assertRegex(fresh.VERSION, r"^d+.d+.d+$")


class TestCleanJobs(V119):
    """19/10/2026, the author's jobs: a clean job cost x0.56 its raw quote, a job with messages during the work x1.49."""

    def test_is_clean(self):
        cfg = pv.config()
        self.assertTrue(pv.is_clean({"session": "c", "turns": 1}, cfg))
        self.assertTrue(pv.is_clean({"session": "c"}, cfg))                # older jobs without turns
        self.assertFalse(pv.is_clean({"session": "c", "turns": 2}, cfg))
        self.assertFalse(pv.is_clean({"session": "rate:x", "turns": 1}, cfg))   # an installment's turns are its runs

    def test_the_factor_learns_from_the_clean_jobs_only(self):
        for i in range(5):
            self.add("clean%d" % i, 1000000, 500000, turns=1)        # x0.5
            self.add("added%d" % i, 1000000, 2000000, turns=3)       # x2: the user added tasks halfway
        self.assertAlmostEqual(pv.learning(pv.config())["factor"], 0.5, places=3)
        old = dict(pv.config(), learn_clean_only=0, start_factor=0)
        self.assertGreater(pv.learning(old)["factor"], 0.9)          # 1.1.8 learned the mix

    def test_a_new_user_starts_from_the_evidence(self):
        self.assertAlmostEqual(pv.learning(pv.config())["factor"], 0.58, places=3)
        self.assertEqual(pv.learning(pv.config())["start_rows"], 5)

    def test_the_start_fills_the_gap_until_min_jobs_clean_jobs(self):
        for i in range(2):
            self.add("clean%d" % i, 1000000, 400000, turns=1)        # x0.4
        learned = pv.learning(pv.config())
        self.assertEqual(learned["start_rows"], 3)                   # 2 own + 3 rows at x0.58: the median is x0.58
        self.assertAlmostEqual(learned["factor"], 0.58, places=3)
        for i in range(3):
            self.add("more%d" % i, 1000000, 400000, turns=1)
        learned = pv.learning(pv.config())
        self.assertEqual(learned["start_rows"], 0)
        self.assertAlmostEqual(learned["factor"], 0.4, places=3)

    def test_installments_do_not_change(self):
        for i in range(5):
            self.add("rate:r%d" % i, 1000000, 1500000, turns=3)
            self.add("added%d" % i, 1000000, 2000000, turns=3)
        on = pv.learning(pv.config(), "rate")["factor"]
        off = pv.learning(dict(pv.config(), learn_clean_only=0, start_factor=0), "rate")["factor"]
        self.assertAlmostEqual(on, off)

    def test_start_factor_off_uses_the_shared_average_as_before(self):
        cfg = dict(pv.config(), start_factor=0)
        self.assertEqual(pv.learning(cfg)["start_rows"], 0)
        self.assertAlmostEqual(pv.learning(cfg)["factor"], 1.0)      # no shared average in the tests


class TestAdditionsOn(V119):
    def test_the_protocol_says_additions(self):
        self.assertIn("ADDITIONS:", pv.protocol(pv.config(), 1.0))



class TestStartByType(V119):
    """19/10/2026: 64 clean jobs (docs/evidence and 15 new ones through the API): code x0.70, research x0.34, texts
    with the rule for texts about right, all x0.59."""

    def test_each_type_starts_from_its_own(self):
        cfg = pv.config()
        for wtype, factor in (("code", 0.70), ("research", 0.35), ("writing", 1.0), ("other", 0.40)):
            learned = pv.learning(cfg, "chat", wtype)
            self.assertAlmostEqual(learned["factor"], factor, places=3, msg=wtype)
            self.assertTrue(learned["typed"])
        self.assertAlmostEqual(pv.learning(cfg)["factor"], 0.58, places=3)       # no type: the general start

    def test_a_type_learns_its_own_jobs(self):
        for i in range(5):
            self.add("r%d" % i, 1000000, 200000, turns=1, type="research")    # x0.2
            self.add("c%d" % i, 1000000, 900000, turns=1, type="code")        # x0.9
        cfg = pv.config()
        self.assertAlmostEqual(pv.learning(cfg, "chat", "research")["factor"], 0.2, places=3)
        self.assertAlmostEqual(pv.learning(cfg, "chat", "code")["factor"], 0.9, places=3)

    def test_two_jobs_of_a_type_and_three_start_rows(self):
        for i in range(2):
            self.add("r%d" % i, 1000000, 200000, turns=1, type="research")
        learned = pv.learning(pv.config(), "chat", "research")
        self.assertEqual(learned["start_rows"], 3)
        self.assertAlmostEqual(learned["factor"], 0.35, places=3)             # 0.2, 0.2, 0.35, 0.35, 0.35

    def test_the_rule_for_texts_is_on(self):
        text = pv.protocol(pv.config(), 1.0)
        self.assertIn("TEXTS (kind=writing): count about 27 wt per word", text)


if __name__ == "__main__":
    unittest.main()
