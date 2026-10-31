"""hermes branch: which finished jobs teach the correction factor (Francesco, 15/10/2026)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import quotient as q  # noqa: E402
import hermes_hooks as h  # noqa: E402


def job(raw, work, seconds, session="20261015_000000_aaaaaa"):
    return {"raw_estimate": raw, "work": work, "actual": work, "chat": 0, "seconds": seconds, "session": session}


class Teaches(unittest.TestCase):
    cfg = {"learn_min_raw": 1000000, "learn_max_speed": 3000}

    def test_small_chat_job_left_out(self):
        self.assertFalse(q.teaches(job(300000, 600000, 900), self.cfg))

    def test_small_installment_counts(self):
        self.assertTrue(q.teaches(job(300000, 600000, 900, session="rate:libro-1"), self.cfg))

    def test_impossible_speed_left_out(self):
        self.assertFalse(q.teaches(job(2000000, 6000000, 222), self.cfg))

    def test_normal_big_job_counts(self):
        self.assertTrue(q.teaches(job(2000000, 3000000, 3000), self.cfg))

    def test_off_by_default(self):
        self.assertTrue(q.teaches(job(100000, 6000000, 10), {}))


if __name__ == "__main__":
    unittest.main()


class MidBand(unittest.TestCase):
    cfg = {"learn_min_raw": 1000000, "learn_mid_min": 500000}

    def test_band(self):
        self.assertTrue(q.mid_band(self.cfg, 500000))
        self.assertTrue(q.mid_band(self.cfg, 999999))
        self.assertFalse(q.mid_band(self.cfg, 1000000))
        self.assertFalse(q.mid_band(self.cfg, 499999))
        self.assertFalse(q.mid_band({}, 700000))

    def test_factor_for(self):
        src = {"factor": 1.05, "factor_mid": 1.8}
        self.assertEqual(q.factor_for(self.cfg, 700000, src), 1.8)
        # 1.1.7: from 1M up to learn_blend_raw (3.4M by default) a straight line from 1M x1.8 to 3.4M x1.05
        self.assertAlmostEqual(q.factor_for(self.cfg, 2000000, src),
                               (1800000 + 1000000 * (3400000 * 1.05 - 1800000) / 2400000) / 2000000.0)
        self.assertEqual(q.factor_for(self.cfg, 3400000, src), 1.05)
        self.assertEqual(q.factor_for(self.cfg, 700000, {"factor": 1.05}), 1.05)


def line(raw):
    """1.1.7: corrected from 1M x1.84 to 3.4M x1.02 along a straight line."""
    return 1840000 + (raw - 1000000) * (3400000 * 1.02 - 1840000) / 2400000.0


class MidBandSteady(unittest.TestCase):
    cfg = {"learn_min_raw": 1000000, "learn_mid_min": 500000}
    src = {"factor": 1.02, "factor_mid": 1.84}

    def test_small_quotes_take_the_medium_factor(self):
        self.assertEqual(q.factor_for(self.cfg, 300000, self.src), 1.84)

    def test_from_one_million_never_below_the_band(self):
        self.assertAlmostEqual(1000000 * q.factor_for(self.cfg, 1000000, self.src), 1840000, delta=1)
        # 1.1.7: a straight line from 1M x1.84 to 3.4M x1.02 (before: 1.84M flat up to 1.8M)
        self.assertAlmostEqual(1500000 * q.factor_for(self.cfg, 1500000, self.src), line(1500000), delta=1)
        self.assertAlmostEqual(3000000 * q.factor_for(self.cfg, 3000000, self.src), line(3000000), delta=1)
        self.assertEqual(q.factor_for(self.cfg, 5000000, self.src), 1.02)

    def test_a_bigger_quote_is_never_corrected_smaller(self):
        raws = sorted(list(range(100000, 4000001, 50000)) + [499999, 999999])
        corrected = [round(r * q.factor_for(self.cfg, r, self.src)) for r in raws]
        self.assertEqual(corrected, sorted(corrected))

    def test_hermes_jobs_use_it(self):
        orig = q.q_learning.learning, q.q_learning.mid_factor
        q.q_learning.learning = lambda cfg, kind="chat", wtype=None: {"factor": 1.02}
        q.q_learning.mid_factor = lambda cfg: 1.84
        try:
            self.assertEqual(h.job_factor(q, self.cfg, 700000), 1.84)
            self.assertAlmostEqual(h.job_factor(q, self.cfg, 3000000), line(3000000) / 3000000.0)
        finally:
            q.q_learning.learning, q.q_learning.mid_factor = orig

    def test_quote_table_uses_it(self):
        orig = q.q_learning.learning, q.q_learning.mid_factor
        q.q_learning.learning = lambda cfg, kind="chat", wtype=None: {"factor": 1.02}
        q.q_learning.mid_factor = lambda cfg: 1.84
        try:
            rows = q.quote_numbers(dict(q.config(), **self.cfg), {"good": 900000, "max": 2000000})["rows"]
        finally:
            q.q_learning.learning, q.q_learning.mid_factor = orig
        self.assertAlmostEqual(rows[0]["work"], 900000 * 1.84)
        self.assertAlmostEqual(rows[1]["work"], line(2000000))   # 1.1.7: along the line
