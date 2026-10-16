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


class TestBlend(unittest.TestCase):
    """16/10/2026: good 1.1M and max 1.6M were both corrected to 1.75M; then, in brackets, every job above 1M carried
    731k more than its factor. Francesco chose a straight line from the band back to the factor."""
    cfg = {"learn_min_raw": 1000000, "learn_mid_min": 500000, "learn_blend_raw": 3400000}
    src = {"factor": 1.0165, "factor_mid": 1.7476}    # the author's, 16/10/2026
    slope = (3400000 * 1.0165 - 1747600) / 2400000.0

    def corrected(self, raw, src=None, cfg=None):
        return raw * pv.factor_for(cfg or self.cfg, raw, src or self.src)

    def rising(self, src, cfg=None, raws=None):
        raws = raws or sorted(set(list(range(500000, 20000001, 10000)) + [999999, 1000001, 3399999, 3400001]))
        values = [self.corrected(r, src, cfg) for r in raws]
        for r, a, b in zip(raws, values, values[1:]):
            self.assertLess(a, b, (src, r))

    def test_the_default_is_the_one_explained(self):
        self.assertEqual(pv.DEFAULTS["learn_blend_raw"], 3400000)
        self.assertGreater(3400000 * 1.0165, 1000000 * 1.7476)      # rising on the author's numbers

    def test_good_and_max_come_out_different_and_rising(self):
        good, top = self.corrected(1100000), self.corrected(1600000)
        self.assertLess(good, top)
        self.assertAlmostEqual(good, 1747600 + 100000 * self.slope, delta=1)
        self.assertAlmostEqual(top, 1747600 + 600000 * self.slope, delta=1)
        self.assertGreater(top - good, 0.5 * 1.0165 * 500000)        # at least half as fast as the factor

    def test_continuous_at_one_million(self):
        self.assertAlmostEqual(self.corrected(1000000), self.corrected(999999), delta=3)
        self.assertGreater(self.corrected(1000001), self.corrected(1000000))
        self.assertGreater(self.corrected(1000000), self.corrected(999999))
        self.assertAlmostEqual(self.corrected(1000000), 1747600, delta=1)

    def test_continuous_at_the_end_of_the_line(self):
        self.assertAlmostEqual(self.corrected(3399999), self.corrected(3400000), delta=2)
        self.assertAlmostEqual(self.corrected(3400000), 3400000 * 1.0165, delta=1)
        self.assertLess(self.corrected(3399999), self.corrected(3400000))

    def test_from_the_end_up_the_factor_alone(self):
        for raw in (3400000, 3400001, 5000000, 10000000, 20000000, 100000000):
            self.assertEqual(pv.factor_for(self.cfg, raw, self.src), 1.0165)

    def test_rising_from_half_a_million_to_twenty(self):
        self.rising(self.src)

    def test_the_factor_larger_than_the_band(self):
        for src in ({"factor": 2.0, "factor_mid": 1.2}, {"factor": 1.0, "factor_mid": 1.0},
                    {"factor": 3.0, "factor_mid": 1.2}):
            self.rising(src)
            self.assertAlmostEqual(self.corrected(1000000, src), 1000000 * src["factor_mid"], delta=1)
            self.assertGreaterEqual(self.corrected(1000000, src), self.corrected(999999, src))   # never a jump back
            self.assertEqual(pv.factor_for(self.cfg, 5000000, src), src["factor"])

    def test_a_line_too_flat_is_made_longer(self):
        # the factor fell to x0.5: 3.4M x 0.5 = 1.7M is under the band's 1.75M; the line ends where it rises at half
        src = {"factor": 0.5, "factor_mid": 1.7476}
        end = pv.blend_end(self.cfg, 1.7476, 0.5)
        self.assertAlmostEqual(end, 1000000 * (2 * 1.7476 / 0.5 - 1))
        self.rising(src)
        self.assertAlmostEqual(self.corrected(end, src), end * 0.5, delta=1)
        self.assertAlmostEqual(self.corrected(end - 1, src), end * 0.5, delta=1)
        self.assertAlmostEqual(self.corrected(1600000, src) - self.corrected(1100000, src), 0.5 * 0.5 * 500000, delta=1)

    def test_a_short_or_missing_end(self):
        for end in (0, 500000, 1000000):
            cfg = dict(self.cfg, learn_blend_raw=end)
            self.rising(self.src, cfg)                               # the factor smaller: the line made longer
            self.rising({"factor": 2.0, "factor_mid": 1.2}, cfg)     # the factor larger: no line, a jump up
        self.assertEqual(pv.blend_end({"learn_min_raw": 1000000}, 1.7476, 1.0165), 3400000)   # the default

    def test_off_without_the_band(self):
        self.assertEqual(pv.factor_for({}, 1100000, self.src), 1.0165)
        self.assertEqual(pv.factor_for(self.cfg, 1100000, {"factor": 1.0165}), 1.0165)


class TestBlendShown(Base):
    def setUp(self):
        super().setUp()
        pv.store(("learn_min_raw",), 1000000)
        pv.store(("learn_mid_min",), 500000)
        patcher = mock.patch.object(pv, "mid_factor", return_value=1.75)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_protocol_and_quote_table_say_the_line(self):
        cfg = pv.config()
        text = pv.protocol(cfg, 1.0)
        self.assertIn("from it up to 3.40M along a straight line to the factor, then the factor", text)
        self.assertNotIn("brackets", text)
        table = pv.quote_table(cfg, {"good": 1100000, "max": 1600000}, lang="it")
        slope = (3400000 - 1750000) / 2400000.0
        self.assertIn(pv.amount(1750000 + 100000 * slope, "it"), table)
        self.assertIn(pv.amount(1750000 + 600000 * slope, "it"), table)
        self.assertIn("da lì a 3,40 milioni in linea dritta fino a x1.00, poi x1.00", table)
        self.assertNotIn("il resto", table)
        table = pv.quote_table(cfg, {"good": 1100000, "max": 1600000}, lang="en")
        self.assertIn("from it up to 3.40 million along a straight line to x1.00, then x1.00", table)

    def test_no_line_when_the_factor_is_larger_and_the_end_too_short(self):
        pv.store(("learn_blend_raw",), 0)
        cfg = pv.config()
        text = pv.protocol(cfg, 2.0)
        self.assertIn("for quotes under 1.00M wt x1.75", text)
        self.assertNotIn("straight line", text)


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
