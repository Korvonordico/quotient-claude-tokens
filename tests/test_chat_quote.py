"""Improvement 4: fairer quotes for jobs done in a chat (Francesco, 31/10/2026, measured on version 1.2.8: 1.17M wt
against 222k quoted). The chat part counts the steps of the jobs measured, and the factor goes halfway to that of all
the chat jobs; both off by default, kept only because they beat the old way in a backtest. And the fallback of the
one-line quote on Hermes (small_quote_line).
Run: python -m unittest discover tests"""

import importlib.util
import json
import os
import time
from unittest import mock

import unittest

from test_v116 import Cli, pv

import hermes_hooks as hh
import hermes_source as hs


def job(raw, work, calls=None, source="hermes", n=0, turns=3):
    row = {"raw_estimate": raw, "actual": work, "work": work, "chat": 0, "session": "hermes:s%d" % n, "turns": turns,
           "started": "2026-10-%02dT10:00:00+01:00" % (n + 1), "finished": "2026-10-%02dT11:00:00+01:00" % (n + 1),
           "factor_used": 1.0, "options": {"good": raw}, "choice": "good"}
    if source:
        row["source"] = source
    if calls:
        row["calls"] = calls
    return row


class ChatQuote(Cli):
    def add(self, *rows):
        with open(os.path.join(pv.home(), "jobs.jsonl"), "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    def on(self, steps=1, own=1):
        pv.store(("chat", "steps_history"), steps)
        pv.store(("chat", "own_factor_mix"), own)
        return pv.config()


class TestDefaults(ChatQuote):
    def test_off_by_default_and_the_quote_is_as_before(self):
        cfg = pv.config()
        self.assertEqual(cfg["chat"]["steps_history"], 0)
        self.assertEqual(cfg["chat"]["own_factor_mix"], 0)
        self.assertIsNone(pv.chat_steps(cfg, 100000, 7))
        self.assertIsNone(pv.own_chat_factor(cfg))
        self.add(*[job(400000, 900000, 24, n=i) for i in range(6)])
        row = pv.quote_numbers(cfg, {"good": 400000}, "chat", 100000)["rows"][0]
        self.assertNotIn("steps", row)
        self.assertNotIn("prudent", row)


class TestSteps(ChatQuote):
    def test_the_median_of_the_same_size_and_origin(self):
        self.add(job(100000, 300000, 20, n=0), job(200000, 300000, 24, n=1), job(300000, 300000, 30, n=2),
                 job(700000, 800000, 90, n=3), job(100000, 300000, 200, source=None, n=4))
        cfg = self.on(own=0)
        self.assertEqual(pv.chat_steps(cfg, 400000, 7, "hermes"), (24, False))
        self.assertEqual(pv.chat_steps(cfg, 400000, 7, "claude"), (15, True))

    def test_few_jobs_a_prudent_estimate_that_never_lowers_the_usual_steps(self):
        self.add(job(100000, 300000, 20, n=0))
        cfg = self.on(own=0)
        self.assertEqual(pv.chat_steps(cfg, 400000, 7, "hermes"), (15, True))
        self.assertEqual(pv.chat_steps(cfg, 400000, 40, "hermes"), (40, True))

    def test_the_quote_counts_them_and_says_when_it_is_prudent(self):
        self.add(*[job(300000, 500000, 24, n=i) for i in range(3)])
        cfg = self.on(own=0)
        with mock.patch.dict(os.environ, {"HERMES_SESSION_ID": "x"}):
            row = pv.quote_numbers(cfg, {"good": 400000}, "chat", 100000)["rows"][0]
            self.assertEqual((row["steps"], row["prudent"]), (24, False))
            self.assertEqual(row["chat"], 24 * 100000 * 0.1)
            table = pv.quote_table(cfg, {"good": 400000}, "chat", 100000, None, None, "it")
            self.assertNotIn("stima prudente", table)
            # a size with no job measured yet
            table = pv.quote_table(cfg, {"good": 2000000}, "chat", 100000, None, None, "it")
            self.assertIn("stima prudente", table)
            self.assertIn("almeno", table)
            self.assertIn("prudent estimate", pv.quote_table(cfg, {"good": 2000000}, "chat", 100000, None, None, "en"))

    def test_installments_do_not_change(self):
        self.add(*[job(300000, 500000, 24, n=i) for i in range(3)])
        before = pv.quote_numbers(pv.config(), {"good": 400000}, "rate", 100000)["rows"][0]["chat"]
        after = pv.quote_numbers(self.on(), {"good": 400000}, "rate", 100000)["rows"][0]["chat"]
        self.assertEqual(before, after)


class TestOwnFactor(ChatQuote):
    def test_it_needs_enough_jobs_of_the_origin(self):
        cfg = self.on(steps=0)
        self.add(*[job(100000, 300000, n=i) for i in range(pv.DEFAULTS["min_jobs"] - 1)])
        self.assertIsNone(pv.own_chat_factor(cfg, "hermes"))
        self.add(job(100000, 300000, n=9))
        self.assertAlmostEqual(pv.own_chat_factor(cfg, "hermes"), 3.0, places=3)
        self.assertIsNone(pv.own_chat_factor(cfg, "claude"))

    def test_it_learns_from_all_the_chat_jobs_not_the_installments(self):
        cfg = self.on(steps=0)
        self.add(*[job(100000, 300000, n=i, turns=9) for i in range(5)])
        self.add(dict(job(100000, 9000000, n=7), session="rate:x"))
        self.assertAlmostEqual(pv.own_chat_factor(cfg, "hermes"), 3.0, places=3)

    def test_halfway_on_a_log_scale(self):
        cfg = self.on(steps=0)
        self.assertAlmostEqual(pv.factor_for(cfg, 100000, {"factor": 0.5, "factor_own": 2.0}), 1.0)
        self.assertEqual(pv.factor_for(cfg, 100000, {"factor": 0.5}), 0.5)

    def test_the_quote_and_a_hermes_job_use_it_and_say_it(self):
        self.add(*[job(100000, 300000, n=i) for i in range(5)])
        off = pv.config()
        usual = pv.chat_factor(off, 100000, None, "hermes")
        cfg = self.on(steps=0)
        mixed = hh.job_factor(pv, cfg, 100000)
        self.assertAlmostEqual(mixed, (usual * 3.0) ** 0.5, places=3)
        with mock.patch.dict(os.environ, {"HERMES_SESSION_ID": "x"}):
            self.assertAlmostEqual(pv.quote_numbers(cfg, {"good": 100000}, "chat", 1000)["rows"][0]["factor"], mixed, places=3)
            self.assertIn("a metà strada con x3.00", pv.quote_table(cfg, {"good": 100000}, "chat", 1000, None, None, "it"))

    def test_a_snapshot_from_before_has_no_mix(self):
        cfg = self.on(steps=0)
        self.add(*[job(100000, 300000, n=i) for i in range(5)])
        self.assertEqual(pv.factor_for(cfg, 100000, {"factor": 0.5, "factor_mid": None}), 0.5)


class TestSmallQuoteOnHermes(ChatQuote):
    def turn(self, text, sid="s1"):
        totals = {k: 1000 for k in hs.COUNTERS}
        totals["aux"] = {k: 0 for k in hs.COUNTERS}
        with mock.patch.object(hh, "_counters", return_value=(totals, 5)), \
                mock.patch.object(hs, "active_seconds", return_value=10), \
                mock.patch.object(hs, "reply_texts", return_value=[]), \
                mock.patch.object(pv, "limits_soon"), mock.patch.object(pv, "timer_put"), \
                mock.patch.object(pv, "quote_gaps", return_value=None):
            return hh.post_llm_call(pv, {"session_id": sid, "extra": {"assistant_response": text}})

    def state(self, sid="s1"):
        return pv.load_json(os.path.join(pv.home(), "hermes-jobs.json"), {}).get(sid) or {}

    def test_with_the_key_on_the_job_line_alone_measures_a_one_line_quote(self):
        pv.store(("small_quote_line",), 1)
        self.turn("QUOTE: good=100000\nTYPE: code")
        self.assertEqual(self.state()["quote"]["options"], {"good": 100000})
        closed = self.turn("Fatto.\nJOB: CLOSE")
        self.assertTrue(closed["closed"])
        self.assertEqual(closed["closed"]["raw_estimate"], 100000)
        self.assertEqual(closed["closed"]["choice"], "good")

    def test_it_can_go_on_after_the_reply(self):
        pv.store(("small_quote_line",), 1)
        self.turn("QUOTE: good=100000")
        self.turn("Ancora qualcosa.\nJOB: CONTINUES")
        self.assertEqual(self.state()["job"]["raw_estimate"], 100000)

    def test_off_nothing_is_measured(self):
        self.turn("QUOTE: good=100000")
        self.assertEqual(self.turn("Fatto.\nJOB: CLOSE"), {})
        self.assertIsNone(self.state().get("job"))

    def test_many_levels_still_need_a_choice(self):
        pv.store(("small_quote_line",), 1)
        self.turn("QUOTE: good=100000 max=200000")
        self.assertEqual(self.turn("Fatto.\nJOB: CLOSE"), {})


if __name__ == "__main__":
    unittest.main()
