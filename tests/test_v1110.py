"""1.1.10: the ceiling of each window in the line, "81% left (~26M of ~32M wt)" (limits.show_top, on).
Run: python -m unittest discover tests"""

import unittest
from unittest import mock

from test_quotient import Base, pv


class TestCeiling(Base):
    def setUp(self):
        super().setUp()
        on = mock.patch.dict(pv.DEFAULTS["limits"], {"show_top": 1})
        on.start()
        self.addCleanup(on.stop)
        now = int(pv.time.time())
        pv.record_limits({"five_hour": 19, "five_hour_resets": now + 3600,
                          "seven_day": 5, "seven_day_resets": now + 6 * 86400}, "usage")

    def test_the_line_says_left_of_the_ceiling(self):
        sizes = {"five_hour": 320000, "seven_day": 2.91e6}
        self.assertIn("81% left (~26M of ~32M wt)", pv.limits_line("en", sizes=sizes))
        line = pv.limits_line("it", sizes=sizes)
        self.assertIn("resta 81% (~26M su ~32M wt)", line)
        self.assertIn("resta 95% (~276M su ~291M wt)", line)

    def test_off(self):
        pv.store(("limits", "show_top"), 0)
        self.assertIn("81% left (~26M wt)", pv.limits_line("en", sizes={"five_hour": 320000}))

    def test_small_numbers(self):
        self.assertEqual(pv.left_text(4.51e6, "it", 9e6), "~4,5M su ~9,0M wt")
        self.assertEqual(pv.left_text(0, "en", 3.2e7), "0 of ~32M wt")
        self.assertEqual(pv.VERSION, "1.1.10")


if __name__ == "__main__":
    unittest.main()
