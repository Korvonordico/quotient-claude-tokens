"""1.1.7: no hook waits for a reading of the limits (they are read in the background, with or without a job), a
shorter line at each message, and the medium band in brackets (a bigger level always comes out bigger).
Run: python -m unittest discover tests"""

import os
import re
from unittest import mock

import unittest

from test_quotient import Base, pv, usage
import hermes_hooks as h
import hermes_source as hs


def zero_counters(sid):
    total = {k: 0 for k in hs.COUNTERS}
    total["aux"] = {k: 0 for k in hs.COUNTERS}
    return total, 0


class TestBrackets(unittest.TestCase):
    """16/10/2026: good 1.1M and max 1.6M were both corrected to 1.75M."""
    cfg = {"learn_min_raw": 1000000, "learn_mid_min": 500000}
    src = {"factor": 1.0165, "factor_mid": 1.7476}    # the author's, 16/10/2026

    def corrected(self, raw, src=None):
        return raw * pv.factor_for(self.cfg, raw, src or self.src)

    def test_good_and_max_come_out_different_and_rising(self):
        good, top = self.corrected(1100000), self.corrected(1600000)
        self.assertLess(good, top)
        self.assertAlmostEqual(good, 1747600 + 101650, delta=1)       # the first million at x1.7476, the rest x1.0165
        self.assertAlmostEqual(top, 1747600 + 609900, delta=1)

    def test_continuous_at_one_million(self):
        self.assertAlmostEqual(self.corrected(1000000), self.corrected(999999), delta=3)
        self.assertGreater(self.corrected(1000001), self.corrected(1000000))
        self.assertGreater(self.corrected(1000000), self.corrected(999999))

    def test_always_rising_whichever_factor_is_larger(self):
        raws = sorted(list(range(400000, 5000001, 10000)) + [999999, 1000001])
        for src in (self.src, {"factor": 2.0, "factor_mid": 1.2}, {"factor": 1.0, "factor_mid": 1.0}):
            values = [self.corrected(r, src) for r in raws]
            for a, b in zip(values, values[1:]):
                self.assertLess(a, b, src)
            self.assertAlmostEqual(self.corrected(1000000, src), 1000000 * src["factor_mid"], delta=1)

    def test_far_above_the_factor_takes_over(self):
        self.assertAlmostEqual(pv.factor_for(self.cfg, 100000000, self.src), 1.0165 + 0.7311 / 100, places=6)

    def test_off_without_the_band(self):
        self.assertEqual(pv.factor_for({}, 1100000, self.src), 1.0165)
        self.assertEqual(pv.factor_for(self.cfg, 1100000, {"factor": 1.0165}), 1.0165)


class TestBracketsShown(Base):
    def setUp(self):
        super().setUp()
        pv.store(("learn_min_raw",), 1000000)
        pv.store(("learn_mid_min",), 500000)
        patcher = mock.patch.object(pv, "mid_factor", return_value=1.75)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_protocol_and_quote_table_say_brackets(self):
        cfg = pv.config()
        text = pv.protocol(cfg, 1.0)
        self.assertIn("in brackets: up to 1.00M at x1.75 and the rest at the factor", text)
        self.assertNotIn("never under", text)
        table = pv.quote_table(cfg, {"good": 1100000, "max": 1600000}, lang="it")
        self.assertIn("1,85 milioni", table)                      # 1.75M + 0.1M
        self.assertIn("2,35 milioni", table)                      # 1.75M + 0.6M
        self.assertIn("sopra, fino a 1,00 milioni x1.75 e il resto x1.00", table)
        self.assertNotIn("mai meno", table)
        table = pv.quote_table(cfg, {"good": 1100000, "max": 1600000}, lang="en")
        self.assertIn("above it, up to 1.00 million x1.75 and the rest x1.00", table)


class TestLimitsInTheBackground(Base):
    """16/10/2026: in Hermes the message waited about 4 s for `claude -p /usage` every 10 minutes, and 14 times in four
    days the hook reached its 20 s limit and the message went without its line."""

    def setUp(self):
        super().setUp()
        live = mock.patch.dict(os.environ, {"QUOTIENT_LIMITS_LIVE": "1"})
        live.start()
        self.addCleanup(live.stop)
        import limits_usage
        self.limits_usage = limits_usage
        self.fetch = mock.patch.object(limits_usage, "fetch", side_effect=AssertionError("a hook waited for /usage")).start()
        self.started = mock.patch.object(pv, "start_detached", return_value=True).start()
        self.addCleanup(mock.patch.stopall)

    def hermes(self, sid="c1"):
        with mock.patch.object(h, "_counters", zero_counters):
            return h.pre_llm_call(pv, {"session_id": sid})["context"]

    def test_hermes_without_a_job_never_waits(self):
        self.hermes()
        self.hermes()
        h.post_llm_call(pv, {"session_id": "c1", "extra": {"assistant_response": "Hello."}})
        self.fetch.assert_not_called()
        self.assertEqual(self.started.call_count, 1)                 # once per interval, before it writes anything
        self.assertEqual(self.started.call_args.args[0], ["limits-read", "--every", "600"])

    def test_hermes_with_a_job_reads_every_minute_in_the_background(self):
        pv.save_json(os.path.join(pv.home(), "hermes-jobs.json"), {"c1": {"told": True, "job": {
            "session": "c1", "choice": "good", "raw_estimate": 100000, "factor": 1.0,
            "start": {k: 0 for k in hs.COUNTERS}, "start_calls": 0, "ctx": 0}}})
        self.hermes()
        self.fetch.assert_not_called()
        self.assertEqual(self.started.call_args.args[0], ["limits-read"])

    def test_claude_code_hooks_never_wait(self):
        self.t.user("hi")
        self.t.call("a", usage(output=10), texts=["Hello."])
        self.run_hook(pv.hook_session, {"session_id": "s1"})
        self.run_hook(pv.hook_prompt, {"session_id": "s1", "transcript_path": self.t.path})
        self.stop()
        pv.save_json(pv.session_path("s2"), {"job": {"choice": "good", "raw_estimate": 100000, "actual": 5000,
                                                       "chat": 0, "factor_used": 1.0}})
        self.run_hook(pv.hook_prompt, {"session_id": "s2", "transcript_path": self.t.path})
        self.fetch.assert_not_called()

    def test_a_job_waiting_for_its_check_reads_in_the_background(self):
        with mock.patch.object(pv, "check_spans", return_value=[("k1", 0, 0, 0, 0, True)]), \
                mock.patch.object(pv, "measure_checks"):
            pv.check_alert(pv.config())
        self.fetch.assert_not_called()
        self.assertEqual(self.started.call_args.args[0], ["limits-read", "--every", "600"])

    def test_once_per_interval_until_the_process_writes(self):
        cfg = pv.config()
        self.assertTrue(pv.limits_soon(cfg, 600))
        self.assertFalse(pv.limits_soon(cfg, 600))                   # it has not written yet: not a second one
        self.assertFalse(pv.limits_soon(cfg))                        # nor at the pace of a job
        path = os.path.join(pv.home(), "limits-state.json")
        state = pv.load_json(path, {})
        state["started"] -= 601
        pv.save_json(path, state)
        self.assertTrue(pv.limits_soon(cfg, 600))                    # nothing came in 10 minutes: once more
        self.assertEqual(self.started.call_count, 2)

    def test_the_process_apart_reads_even_right_after_it_was_started(self):
        self.assertTrue(pv.limits_soon(pv.config(), 600))
        with mock.patch.object(self.limits_usage, "fetch", return_value={"five_hour": 12, "seven_day": 4}) as fetch, \
                mock.patch.object(pv, "find_claude", return_value="claude"):
            pv.main(["limits-read", "--every", "600"])
            pv.main(["limits-read", "--every", "600"])               # read a moment ago: not again
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(pv.latest_limits()["five_hour"]["used"], 12)
        self.assertIn("started", pv.load_json(os.path.join(pv.home(), "limits-state.json"), {}))   # kept by the reading
        self.assertFalse(pv.limits_soon(pv.config(), 600))


class TestShorterLine(Base):
    def test_hermes_keeps_the_measures_and_drops_the_rest(self):
        with mock.patch.object(h, "_counters", zero_counters):
            h.pre_llm_call(pv, {"session_id": "c1"})                 # the protocol, once
            line = h.pre_llm_call(pv, {"session_id": "c1"})["context"]
        for kept in ("[Quotient %s]" % pv.VERSION, "limits not read", "factor x1.00", "(installments x1.00)",
                     "CHAT PART: each step re-reads about"):
            self.assertIn(kept, line)
        for gone in ("threshold", "quotes under", "steps per 1M", "per 1M wt of work", "Big job", "QUOTE / CHOICE"):
            self.assertNotIn(gone, line)
        self.assertLess(len(line), 200)

    def test_claude_code_keeps_the_measures_and_drops_the_rest(self):
        self.t.user("hello")
        self.t.call("a", usage(write=10000, output=10))
        self.t.user("more")
        self.t.call("b", usage(read=300000, output=10))
        line = self.run_hook(pv.hook_prompt, {"session_id": "s1", "transcript_path": self.t.path})
        for kept in ("[Quotient %s]" % pv.VERSION, "factor x1", "Plan limits", "CHAT PART", "300k tokens", "+100%",
                     "new chat"):
            self.assertIn(kept, line)
        for gone in ("Threshold", "Quote rules", "typical miss", "steps per 1M", "Working time", "Quote the WORK"):
            self.assertNotIn(gone, line)

    def test_the_size_of_one_percent_without_its_margin(self):
        now = int(pv.time.time())
        resets = now + 86400
        pv.append_jsonl(pv.limits_path(), {"ts": "x", "epoch": now - 3000, "seven_day": 10, "seven_day_resets": resets})
        pv.append_jsonl(pv.limits_path(), {"ts": "x", "epoch": now - 10, "seven_day": 15, "seven_day_resets": resets})
        moment = pv.datetime.fromtimestamp(now - 1000).astimezone().isoformat()
        pv.append_jsonl(os.path.join(pv.home(), "turns.jsonl"), {"ts": moment, "wt": 500000})
        line = self.run_hook(pv.hook_prompt, {"session_id": "s1", "transcript_path": self.t.path})
        self.assertIn("1% of the week ~100k wt.", line)
        self.assertNotIn("between", line)

    def test_claude_code_aside_at_the_first_message_and_after_an_aside(self):
        def prompt():
            return self.run_hook(pv.hook_prompt, {"session_id": "s1", "transcript_path": self.t.path})
        self.t.user("big job")
        self.t.call("q", usage(output=100), texts=["QUOTE: essential=100k good=200k max=400k"])
        self.stop()
        self.t.user("good")
        self.t.call("w1", usage(output=1000), texts=["CHOICE: good\nPACE: today", "Part one.\nJOB: CONTINUES"])
        self.stop()
        first = prompt()
        self.assertIn("end the reply with the line ASIDE", first)
        self.assertIn("JOB: CONTINUES", first)
        self.t.user("go on")
        self.t.call("w2", usage(output=400), texts=["Part two.\nJOB: CONTINUES"])
        self.stop()
        second = prompt()
        self.assertNotIn("end the reply with the line ASIDE", second)
        self.assertIn("Open job (level 'good'", second)
        self.assertIn("JOB: CONTINUES", second)    # without it the job would close: said at every message
        self.assertLess(len(second), len(first))
        self.t.user("by the way, the weather?")
        self.t.call("a1", usage(output=600), texts=["Sunny.\n\nASIDE"])
        self.stop()
        self.assertIn("end the reply with the line ASIDE", prompt())   # again after a reply counted apart
        self.t.user("go on")
        self.t.call("w3", usage(output=400), texts=["Done.\nJOB: CONTINUES"])
        self.stop()
        self.assertNotIn("end the reply with the line ASIDE", prompt())

    def test_hermes_aside_at_the_first_message_and_after_an_aside(self):
        pv.save_json(os.path.join(pv.home(), "hermes-jobs.json"), {"c1": {"told": True, "job": {
            "session": "c1", "choice": "good", "raw_estimate": 100000, "factor": 1.0,
            "start": {k: 0 for k in hs.COUNTERS}, "start_calls": 0, "ctx": 0}}})

        def prompt():
            with mock.patch.object(h, "_counters", zero_counters):
                return h.pre_llm_call(pv, {"session_id": "c1"})["context"]
        first = prompt()
        self.assertIn("end the reply with the line ASIDE", first)
        self.assertIn("Open job: good", first)
        second = prompt()
        self.assertNotIn("end the reply with the line ASIDE", second)
        self.assertIn("Open job: good", second)
        self.assertLess(len(second), len(first))
        with mock.patch.object(h, "_counters", zero_counters):
            h.post_llm_call(pv, {"session_id": "c1", "extra": {"assistant_response": "Sunny.\n\nASIDE"}})
        self.assertIn("end the reply with the line ASIDE", prompt())   # again after a reply counted apart


class TestDocs(unittest.TestCase):
    """The 1.1.6 merge left `@@TESTCOUNT@@` in the README instead of the number of tests."""
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

    def read(self, rel):
        with open(os.path.join(self.root, rel), encoding="utf-8") as f:
            return f.read()

    def test_no_placeholder_and_the_version_everywhere(self):
        for rel in ("README.md", "README.it.md", "PRIVACY.md", "docs/index.html"):
            self.assertNotIn("@@", self.read(rel), rel)
        self.assertIn("version %s ·" % pv.VERSION, self.read("docs/index.html"))
        self.assertIn("## [%s] - " % pv.VERSION, self.read("CHANGELOG.md"))
        for rel in ("README.md", "README.it.md", "PRIVACY.md", "docs/index.html"):
            self.assertIn('{"v":1,"q":"%s",' % pv.VERSION, self.read(rel), rel)

    def test_the_readmes_say_the_same_number_of_tests(self):
        en = re.search(r"\*\*Automatic tests\.\*\* (\d+) tests", self.read("README.md"))
        it = re.search(r"\*\*Prove automatiche\.\*\* (\d+) prove", self.read("README.it.md"))
        self.assertTrue(en and it)
        self.assertEqual(en.group(1), it.group(1))


if __name__ == "__main__":
    unittest.main()
