"""Improvements 8, 10, 11: what the same job would cost on a cheaper model; a budget for the normal chats; an
installment that goes round in circles stops by itself (Francesco, 30/10/2026). All off by default.
Run: python -m unittest discover tests"""

import io
import json
import os
import sys
import time
from unittest import mock

import unittest

from test_v116 import Cli, pv

import savings
import hermes_hooks as hh


class WhatIf(Cli):
    def on(self, **more):
        pv.store(("whatif", "enabled"), 1)
        for k, v in more.items():
            pv.store(("whatif", k), v)
        return pv.config()

    def test_off_by_default(self):
        cfg = pv.config()
        self.assertEqual(cfg["whatif"]["enabled"], 0)
        self.assertEqual(savings.what_if(pv, cfg, 1000000, "opus", "en"), "")
        self.assertNotIn("instead of", pv.quote_table(cfg, {"good": 1000000}, "chat", 1000, None, None, "en"))

    def test_the_price_ratio_stated_as_an_estimate(self):
        cfg = self.on()
        text = savings.what_if(pv, cfg, 1000000, "opus", "en")
        self.assertIn("With Sonnet instead of Opus", text)
        self.assertIn("50%", text)
        self.assertIn("500k", text.replace(",", ""))
        self.assertIn("an estimate", text)
        self.assertIn("work worse", text)
        self.assertIn("una stima", savings.what_if(pv, cfg, 1000000, "opus", "it"))

    def test_nothing_when_it_is_not_cheaper_or_unknown(self):
        cfg = self.on()
        self.assertEqual(savings.what_if(pv, cfg, 1000, "sonnet", "en"), "")
        self.assertEqual(savings.what_if(pv, cfg, 1000, "haiku", "en"), "")
        self.assertEqual(savings.what_if(pv, cfg, 1000, "other", "en"), "")
        self.assertEqual(savings.what_if(pv, cfg, 0, "opus", "en"), "")

    def test_another_model_as_a_setting(self):
        cfg = self.on(model="haiku")
        self.assertIn("12%", savings.what_if(pv, cfg, 1000000, "opus", "en").replace("13%", "12%"))

    def test_the_table_counts_first(self):
        cfg = self.on()
        with mock.patch.object(pv, "model_price", lambda m: {"input": 1e-6} if m and "sonnet" in m else None):
            self.assertIn("25%", savings.what_if(pv, cfg, 1000000, "opus", "en"))

    def test_in_the_quote_and_at_the_close(self):
        cfg = self.on()
        self.assertIn("With Sonnet instead of Opus", pv.quote_table(cfg, {"good": 1000000}, "chat", 1000, None, None, "en"))
        row = {"choice": "good", "actual": 1000000, "raw_estimate": 900000, "factor_used": 1.0, "family": "opus", "chat": 0, "work": 1000000}
        self.assertIn("With Sonnet", pv.closed_note(row, cfg))
        self.assertNotIn("With Sonnet", pv.closed_note(row, pv.DEFAULTS and dict(cfg, whatif={"enabled": 0})))


class Budget(Cli):
    def read(self, used, epoch, resets=1793595600.0):
        with open(pv.limits_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps({"epoch": epoch, "source": "usage", "seven_day": used, "seven_day_resets": resets}) + "\n")

    def noon(self):
        t = time.localtime()
        return time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 12, 0, 0, 0, 0, -1))

    def set(self, day=0, week=0, stop=0):
        pv.store(("budget", "day_percent"), day)
        pv.store(("budget", "week_percent"), week)
        pv.store(("budget", "stop"), stop)
        return pv.config()

    def day(self, *used_today, yesterday=30.0):
        noon = self.noon()
        self.read(yesterday, noon - 20 * 3600)
        for i, u in enumerate(used_today):
            self.read(u, noon - 3600 + i)

    def test_off_by_default(self):
        cfg = pv.config()
        self.assertEqual((cfg["budget"]["day_percent"], cfg["budget"]["week_percent"], cfg["budget"]["stop"]), (0, 0, 0))
        self.day(99.0)
        self.assertEqual(savings.budget_check(pv, cfg, "x", self.noon()), (None, ""))

    def test_the_day_counts_from_midnight_and_the_week_as_it_is(self):
        self.day(33.0)
        cfg = self.set(day=5, week=50)
        numbers = {b["kind"]: b for b in savings.budget_numbers(pv, cfg, self.noon())}
        self.assertEqual((numbers["day"]["used"], numbers["day"]["share"]), (3.0, 60.0))
        self.assertEqual((numbers["week"]["used"], numbers["week"]["share"]), (33.0, 66.0))

    def test_a_week_that_starts_again_today_counts_from_zero(self):
        noon = self.noon()
        self.read(90.0, noon - 20 * 3600, resets=noon - 3600)
        self.read(2.0, noon - 60, resets=noon + 7 * 86400)
        cfg = self.set(day=5)
        self.assertEqual(savings.budget_numbers(pv, cfg, noon)[0]["used"], 2.0)

    def test_each_step_is_told_once(self):
        self.day(32.5)
        cfg = self.set(day=5)
        _, note = savings.budget_check(pv, cfg, "x", self.noon())
        self.assertIn("BUDGET", note)
        self.assertIn("50%", note)
        self.assertEqual(savings.budget_check(pv, cfg, "x", self.noon()), (None, ""))
        self.read(34.0, self.noon() - 10)
        _, note = savings.budget_check(pv, cfg, "x", self.noon())
        self.assertIn("80%", note)

    def test_past_it_nothing_stops_without_the_key(self):
        self.day(40.0)
        blocked, note = savings.budget_check(pv, self.set(day=5), "x", self.noon())
        self.assertIsNone(blocked)
        self.assertIn("200%", note)

    def test_the_real_stop_and_the_way_out(self):
        self.day(40.0)
        cfg = self.set(day=5, stop=1)
        blocked, _ = savings.budget_check(pv, cfg, "x", self.noon())
        self.assertIn("BUDGET OK", blocked)
        self.assertIn(savings.budget_check(pv, cfg, "go on", self.noon())[0], (blocked,))
        self.assertIsNone(savings.budget_check(pv, cfg, "BUDGET OK, vai", self.noon())[0])
        self.assertIsNone(savings.budget_check(pv, cfg, "again", self.noon())[0])

    def test_the_prompt_hook_refuses_the_message(self):
        self.day(40.0)
        self.set(day=5, stop=1)
        stdin = io.TextIOWrapper(io.BytesIO(json.dumps({"session_id": "c", "prompt": "fai"}).encode("utf-8")), encoding="utf-8")
        real_now = self.noon()
        stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        with mock.patch.object(sys, "stdin", stdin), mock.patch.object(sys, "stdout", stdout), \
                mock.patch.object(time, "time", return_value=real_now), mock.patch.object(pv, "limits_soon"):
            pv.hook_prompt()
            stdout.flush()
        said = json.loads(stdout.buffer.getvalue().decode("utf-8"))
        self.assertEqual(said["decision"], "block")
        self.assertIn("BUDGET OK", said["reason"])

    def test_a_scheduled_prompt_is_not_refused(self):
        self.day(40.0)
        self.set(day=5, stop=1)
        pv.store(("rate", "prompt_prefix"), "[AUTO]")
        stdin = io.TextIOWrapper(io.BytesIO(json.dumps({"session_id": "c", "prompt": "[AUTO] fai"}).encode("utf-8")), encoding="utf-8")
        stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        with mock.patch.object(sys, "stdin", stdin), mock.patch.object(sys, "stdout", stdout), mock.patch.object(pv, "limits_soon"):
            pv.hook_prompt()
            stdout.flush()
        self.assertNotIn('"decision"', stdout.buffer.getvalue().decode("utf-8"))

    def test_no_readings_no_budget(self):
        self.assertEqual(savings.budget_check(pv, self.set(day=5, stop=1), "x"), (None, ""))

    def test_the_command(self):
        self.assertIn("budget", self.cli("budget").lower())
        self.day(33.0)
        self.set(week=50)
        self.assertIn("33.0%", self.cli("budget"))


def tool_call(key, tool_id, name, given):
    return {"type": "assistant", "requestId": key, "message": {"usage": {"input_tokens": 1, "output_tokens": 1},
            "content": [{"type": "tool_use", "id": tool_id, "name": name, "input": given}]}}


def tool_result(tool_id, text, error=False):
    block = {"type": "tool_result", "tool_use_id": tool_id, "content": text}
    if error:
        block["is_error"] = True
    return {"type": "user", "message": {"content": [block]}}


class Loops(Cli):
    def setUp(self):
        super().setUp()
        pv.store(("rate", "loop_stop"), 3)
        self.cfg = pv.config()
        self.name = "lavoro"
        os.makedirs(pv.rate_dir(self.name))
        self.handoff = os.path.join(pv.rate_dir(self.name), "HANDOFF.md")
        with open(self.handoff, "w", encoding="utf-8") as f:
            f.write("PROGRESS: 10%\n")

    def data(self, name="Bash", given=None, use="now"):
        return {"session_id": "s", "tool_name": name, "tool_input": given if given is not None else {"command": "make"},
                "tool_use_id": use}

    def repeated(self, n, given=None):
        entries = []
        for i in range(n):
            entries += [tool_call("k%d" % i, "t%d" % i, "Bash", given or {"command": "make"}), tool_result("t%d" % i, "ok")]
        return entries

    def test_off_by_default(self):
        self.assertEqual(pv.DEFAULTS["rate"]["loop_stop"], 0)
        self.assertIsNone(savings.loop_check(pv, self.name, self.data(), self.repeated(9), dict(self.cfg, rate={"loop_stop": 0})))

    def test_the_same_call_in_a_row(self):
        self.assertIsNone(savings.loop_found(pv, self.repeated(1), self.data(), 3))
        self.assertIn("same call of Bash 3 times", savings.loop_found(pv, self.repeated(2), self.data(), 3))

    def test_the_call_already_in_the_transcript_is_not_counted_twice(self):
        entries = self.repeated(2)
        self.assertIsNone(savings.loop_found(pv, entries, self.data(use="t1"), 3))

    def test_anything_in_between_breaks_it(self):
        entries = self.repeated(2) + [tool_call("e", "e1", "Edit", {"file_path": "a"}), tool_result("e1", "ok")]
        self.assertIsNone(savings.loop_found(pv, entries, self.data(), 3))

    def test_the_same_error_from_different_commands(self):
        entries = []
        for i in range(3):
            entries += [tool_call("k%d" % i, "t%d" % i, "Bash", {"command": "try %d" % i}),
                        tool_result("t%d" % i, "boom: no such file", error=True)]
        self.assertIn("same error 3 times", savings.loop_found(pv, entries, self.data(given={"command": "other"}), 3))

    def test_different_errors_are_no_loop(self):
        entries = []
        for i in range(3):
            entries += [tool_call("k%d" % i, "t%d" % i, "Bash", {"command": "try %d" % i}),
                        tool_result("t%d" % i, "boom %d" % i, error=True)]
        self.assertIsNone(savings.loop_found(pv, entries, self.data(given={"command": "other"}), 3))

    def test_it_stops_and_writes_in_the_handoff_and_only_the_handoff_passes(self):
        data = self.data()
        reason = savings.loop_check(pv, self.name, data, self.repeated(2), self.cfg)
        self.assertIn("round in circles", reason)
        with open(self.handoff, encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith("PROGRESS: 10%"))
        self.assertIn("STUCK", text)
        self.assertEqual(text.count("STUCK"), 1)
        # another command is refused too, and the note is not written twice
        self.assertTrue(savings.loop_check(pv, self.name, self.data(given={"command": "ls"}, use="x"), [], self.cfg))
        with open(self.handoff, encoding="utf-8") as f:
            self.assertEqual(f.read().count("STUCK"), 1)
        self.assertIsNone(savings.loop_check(pv, self.name, self.data("Edit", {"file_path": self.handoff}, "y"), [], self.cfg))
        self.assertTrue(savings.loop_check(pv, self.name, self.data("Edit", {"file_path": "other.md"}, "z"), [], self.cfg))

    def test_a_new_run_starts_free(self):
        savings.loop_check(pv, self.name, self.data(), self.repeated(2), self.cfg)
        self.assertIsNone(savings.loop_check(pv, self.name, dict(self.data(), session_id="new"), [], self.cfg))


if __name__ == "__main__":
    unittest.main()
