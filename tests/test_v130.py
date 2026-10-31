"""1.3.0: the 5-hour window says when it would run out at the pace used so far (limits.pace)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from quotient_lib import q_limits as L  # noqa: E402


class TestRunOut(unittest.TestCase):
    def setUp(self):
        self.reset = 1_000_000 + L.FIVE_HOURS  # window started at 1_000_000

    def w(self, used, hours_in):
        return {"used": used, "resets": self.reset, "epoch": 1_000_000 + hours_in * 3600}

    def test_fast_pace_runs_out_before_reset(self):
        end = L.run_out_at("five_hour", self.w(80, 2))  # 80% in 2 h -> 100% at 2.5 h
        self.assertAlmostEqual(end, 1_000_000 + 2.5 * 3600, delta=1)

    def test_slow_pace_says_nothing(self):
        self.assertIsNone(L.run_out_at("five_hour", self.w(52, 4)))  # -> 65% at reset

    def test_too_early_says_nothing(self):
        self.assertIsNone(L.run_out_at("five_hour", self.w(5, 0.05)))

    def test_min_used_is_a_setting(self):
        self.assertIsNotNone(L.run_out_at("five_hour", self.w(5, 0.05), min_used=1))

    def test_week_and_missing_reset_say_nothing(self):
        self.assertIsNone(L.run_out_at("seven_day", self.w(80, 2)))
        self.assertIsNone(L.run_out_at("five_hour", {"used": 80, "resets": None, "epoch": 5}))

    def test_full_says_nothing(self):
        self.assertIsNone(L.run_out_at("five_hour", self.w(100, 2)))

    def line(self, pace):
        latest = {"five_hour": self.w(80, 2)}
        with mock.patch.object(L, "latest_limits", return_value=latest), \
                mock.patch.object(L, "cfg_limits", return_value={"pace": pace, "show_top": 1}), \
                mock.patch.object(L.time, "time", return_value=1_000_000 + 2 * 3600):
            return L.limits_line("it", sizes={})

    def test_line_says_it_and_can_be_turned_off(self):
        self.assertIn("a questo ritmo finisce verso", self.line(1))
        self.assertNotIn("ritmo", self.line(0))


if __name__ == "__main__":
    unittest.main()
