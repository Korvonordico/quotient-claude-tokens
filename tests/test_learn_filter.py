"""1.1.3: which finished jobs teach the correction factor (Francesco, 15/10/2026)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import quotient as q  # noqa: E402


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
        self.assertEqual(q.factor_for(self.cfg, 2000000, src), 1.05)
        self.assertEqual(q.factor_for(self.cfg, 700000, {"factor": 1.05}), 1.05)
