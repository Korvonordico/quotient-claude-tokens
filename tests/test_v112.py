"""1.1.2: the ratio between the 5 hours and the week (a second estimate of the week), and a change of subscription.
Run: python -m unittest discover tests"""

import os
from unittest import mock

from q_patch import patch_q

from test_quotient import Base, pv

DAY = 86400


def iso(epoch):
    return pv.datetime.fromtimestamp(epoch).astimezone().isoformat(timespec="seconds")


class LimitsBase(Base):
    """Fake readings of the limits: each 5-hour window has a reading at its start, one an hour later, and a measured turn
    in between. All in one week; the week does not rise between the windows."""

    def setUp(self):
        super().setUp()
        self.morning = int(pv.datetime.now().replace(hour=10, minute=0, second=0, microsecond=0).timestamp())
        self.week_resets = self.morning + DAY + 3600
        self.week = 0

    def read(self, at, five, week, five_resets):
        pv.append_jsonl(pv.limits_path(), {"ts": "x", "epoch": at, "five_hour": five, "five_hour_resets": five_resets,
                                           "seven_day": week, "seven_day_resets": self.week_resets})

    def turn(self, at, wt):
        pv.append_jsonl(os.path.join(pv.home(), "turns.jsonl"), {"ts": iso(at), "wt": wt})

    def window(self, start, five, week, wt):
        resets = start + 5 * 3600
        self.read(start, 1, self.week, resets)
        self.turn(start + 1800, wt)
        self.week += week
        self.read(start + 3600, 1 + five, self.week, resets)

    def prompt(self):
        return self.run_hook(pv.hook_prompt, {"session_id": "s1", "transcript_path": self.t.path})


class TestWindowRatio(LimitsBase):
    """Francesco's idea: the two percentages rise with the same use, so the points of the 5 hours for 1 point of the week,
    times the size of 1% of the 5 hours, give the week a second estimate."""

    def three_windows(self):
        self.window(self.morning - 3 * DAY, 10, 2, 1000000)   # 1% of the 5 hours = 100k wt in all three
        self.window(self.morning - 2 * DAY, 12, 1, 1200000)
        self.window(self.morning - DAY, 8, 1, 800000)

    def test_the_ratio_and_its_margin(self):
        self.three_windows()
        self.read(self.morning - DAY + 7200, 9, self.week, self.morning - DAY + 5 * 3600)   # no rise: it changes nothing
        r = pv.window_ratio()
        self.assertEqual((r["ratio"], r["five_points"], r["week_points"], r["windows"]), (7.5, 30, 4, 3))
        margin = 2 * (3 / 6.0) ** 0.5     # whole percentages: the rounding partly cancels over the windows
        self.assertAlmostEqual(r["low"], (30 - margin) / (4 + margin))
        self.assertAlmostEqual(r["high"], (30 + margin) / (4 - margin))
        self.assertIsNone(pv.window_ratio(since=self.morning))   # nothing after this morning

    def test_the_report_sets_the_two_estimates_side_by_side(self):
        self.three_windows()
        report = self.run_hook(pv.report, {})
        self.assertIn("The whole week holds about 75.00M wt", report)
        self.assertIn("From the 5 hours: 7.5 points of the 5 hours for 1 point of the week", report)
        self.assertIn("so the week holds about 75.00M wt", report)
        self.assertIn("The two estimates of the week agree (x1.00 apart).", report)

    def test_estimates_far_apart_are_told(self):
        self.three_windows()
        self.turn(self.morning - 2 * DAY - 6 * 3600, 6000000)   # measured between the windows: only the week sees it
        report = self.run_hook(pv.report, {})
        self.assertIn("The whole week holds about 225.00M wt", report)
        self.assertIn("so the week holds about 75.00M wt", report)
        self.assertIn("do NOT agree: x3.00 apart, more than x1.5", report)

    def test_the_ratio_takes_the_place_of_a_week_with_too_few_points(self):
        self.three_windows()
        real = pv.capacity
        with patch_q(pv, "capacity", side_effect=lambda w, since=None, turns=None:
                               None if w == "seven_day" else real(w, since, turns)):
            c = pv.week_capacity()
            self.assertEqual((c["source"], round(c["per_point"])), ("ratio", 750000))
            self.assertIn("from the 5-hour/week ratio, the week's own estimate has too few points", self.prompt())
            report = self.run_hook(pv.report, {})
        self.assertIn("The week's own estimate has fewer than 3 points: the one from the 5 hours is used in its place.",
                      report)
        self.assertEqual(pv.week_plan(pv.config())["per_point"], 750000)

    def test_no_ratio_without_readings_of_both(self):
        self.assertIsNone(pv.window_ratio())
        self.assertIsNone(pv.week_capacity())
        self.assertIn("The ratio between the 5 hours and the week is not measured yet", self.run_hook(pv.report, {}))


class TestPlanChange(LimitsBase):
    """A change of subscription: the windows of the old plan must not stay mixed in for long, and a day of much use
    outside Quotient (claude.ai, the phone) must not look like one."""

    def old(self):
        for k in range(4):   # four days, 1% of the 5 hours = 100k wt, 1% of the week = 500k wt
            self.window(self.morning - (6 - k) * DAY, 10, 2, 1000000)

    def new(self, per_point, week, starts=None):
        for start in starts or (self.morning - 2 * DAY, self.morning - 2 * DAY + 6 * 3600, self.morning - DAY):
            self.window(start, 10, week, 10 * per_point)

    def test_a_bigger_limit_is_found_told_once_and_learned_again(self):
        self.old()
        self.new(300000, 2)     # 1% of the 5 hours x3, and the week in the same time x3
        row = pv.plan_detect()
        self.assertEqual((row["direction"], row["five_hour"], row["week"], row["epoch"]),
                         ("bigger", [3.0, 3.0, 3.0], 3.0, self.morning - 2 * DAY))
        self.assertEqual(pv.plan_since(), self.morning - 2 * DAY)
        self.assertEqual(pv.capacity("five_hour")["per_point"], 300000)      # only the windows after the change
        self.assertEqual(round(pv.capacity("five_hour", since=0)["per_point"]), 185714)   # 13M wt for 70 points
        first = self.prompt()
        self.assertIn("PLAN: the plan limit looks bigger than before", first)
        self.assertIn("x3.0/3.0/3.0", first)
        self.assertIn("maybe they changed subscription: Quotient starts learning it again", first)
        self.assertNotIn("claude.ai", first)
        self.assertNotIn("PLAN:", self.prompt())   # told once
        self.assertIn("(a change of plan Quotient found; plan-changed --undo takes it back)", self.run_hook(pv.report, {}))
        # the user did not change plan: taken back, and the same windows are not judged again
        self.run_hook(lambda: pv.main(["plan-changed", "--undo"]), {})
        self.assertEqual(pv.plan_since(), 0)
        self.assertIsNone(pv.plan_detect())

    def test_a_smaller_limit_must_show_in_the_week_too(self):
        self.old()
        self.new(50000, 1)      # the 5 hours look x0.5, but the week in the same time holds as before
        self.assertIsNone(pv.plan_detect())
        self.assertNotIn("PLAN:", self.prompt())

    def test_a_smaller_limit_seen_by_both(self):
        self.old()
        self.new(50000, 3)      # the 5 hours x0.5 and the week x0.33
        first = self.prompt()
        self.assertIn("PLAN: the plan limit looks smaller than before", first)
        self.assertIn("or used Claude a lot where Quotient cannot see (claude.ai, the phone)", first)
        self.assertEqual([r["source"] for r in pv.read_jsonl(pv.plan_changes_path())], ["detected"])

    def test_one_day_of_far_windows_is_not_enough(self):
        self.old()
        day = self.morning - DAY
        self.new(300000, 2, starts=(day - 4 * 3600, day + 5400, day + 7 * 3600))   # 06:00, 11:30, 17:00 of one day
        self.assertIsNone(pv.plan_detect())
        pv.store(("plan", "days"), 1)    # it was the one day that held it back
        self.assertEqual(pv.plan_detect()["direction"], "bigger")

    def test_not_all_in_the_same_direction(self):
        self.old()
        self.new(300000, 2, starts=(self.morning - 2 * DAY, self.morning - 2 * DAY + 6 * 3600))
        self.window(self.morning - DAY, 10, 2, 1000000)    # the last window is like the old ones
        self.assertIsNone(pv.plan_detect())

    def test_too_few_windows_to_judge(self):
        self.window(self.morning - 3 * DAY, 10, 2, 1000000)
        self.new(300000, 2)
        self.assertIsNone(pv.plan_detect())

    def test_told_by_hand_and_taken_back(self):
        said = self.run_hook(lambda: pv.cmd_plan_changed(mock.Mock(undo=True)), {})
        self.assertIn("No change of plan to take back.", said)
        said = self.run_hook(lambda: pv.main(["plan-changed"]), {})
        self.assertIn("learns the size of your limit again, from the readings after now only", said)
        self.assertAlmostEqual(pv.plan_since(), pv.time.time(), delta=5)
        self.assertNotIn("PLAN:", self.prompt())     # the user said it: nothing to tell
        self.assertIn("taken back", self.run_hook(lambda: pv.cmd_plan_changed(mock.Mock(undo=True)), {}))
        self.assertEqual(pv.plan_since(), 0)
        self.assertIn("plan-changed [--undo]", self.run_hook(pv.cmd_commands, {}))

    def test_after_a_change_by_hand_the_week_uses_the_ratio_of_before(self):
        self.window(self.morning - 3 * DAY, 10, 2, 1000000)
        self.window(self.morning - 2 * DAY, 12, 1, 1200000)
        self.window(self.morning - DAY, 8, 1, 800000)
        pv.append_jsonl(pv.plan_changes_path(), {"ts": "x", "epoch": self.morning - DAY + 5 * 3600, "source": "user"})
        self.window(self.morning - DAY + 6 * 3600, 10, 1, 3000000)   # the new plan: 1% of the 5 hours = 300k
        self.assertIsNone(pv.capacity("seven_day"))                   # 1 point of the week since the change
        c = pv.week_capacity()
        self.assertEqual((c["source"], c["ratio"]["ratio"], round(c["per_point"])), ("ratio-before", 8.0, 2400000))
        self.assertIn("from the 5-hour/week ratio of before the change of plan", self.prompt())
        report = self.run_hook(pv.report, {})
        self.assertIn("(a change of plan you told)", report)
        self.assertIn("with the ratio of before the change of plan", report)

    def test_a_change_found_in_a_scheduled_prompt_waits_for_the_user(self):
        pv.store(("rate", "prompt_prefix"), "[AUTO]")
        self.old()
        self.new(300000, 2)
        said = self.run_hook(pv.hook_prompt, {"session_id": "s1", "transcript_path": self.t.path, "prompt": "[AUTO] go"})
        self.assertNotIn("PLAN:", said)
        self.assertEqual(len(pv.read_jsonl(pv.plan_changes_path())), 1)   # found already
        self.assertIn("PLAN: the plan limit looks bigger", self.prompt())


if __name__ == "__main__":
    import unittest
    unittest.main()
