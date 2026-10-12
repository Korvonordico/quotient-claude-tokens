"""Tests for the Hermes source, with a fake Hermes session store. Run: python -m unittest discover tests"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import hermes_source as hs  # noqa: E402

W = {"input": 1.0, "cache_write_5m": 1.25, "cache_write_1h": 2.0, "cache_read": 0.1, "output": 5.0}


def fake_hermes(rows):
    d = tempfile.mkdtemp()
    con = sqlite3.connect(os.path.join(d, "state.db"))
    con.execute("create table sessions (id text, source text, model text, started_at real, ended_at real, "
                "parent_session_id text, title text, last_activity_at real, estimated_cost_usd real, "
                "billing_provider text, api_call_count int, input_tokens int, output_tokens int, "
                "cache_read_tokens int, cache_write_tokens int, system_prompt text)")
    for r in rows:
        con.execute("insert into sessions (id, source, model, started_at, last_activity_at, parent_session_id, title, "
                    "billing_provider, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens) "
                    "values (?,?,?,?,?,?,?,?,?,?,?,?)", r)
    con.commit(); con.close()
    return d


def update(d, sid, **counters):
    con = sqlite3.connect(os.path.join(d, "state.db"))
    for k, v in counters.items():
        con.execute("update sessions set %s = ? where id = ?" % k, (v, sid))
    con.commit(); con.close()


class HermesSource(unittest.TestCase):
    def setUp(self):
        self.q = tempfile.mkdtemp()
        self.h = fake_hermes([
            ("chat1", "cli", "claude-opus-5-5", 1000.0, 2000.0, None, "Def Jam", "anthropic", 10, 100, 10000, 1000),
            ("sub1", "subagent", "claude-opus-5-5", 1500.0, 1800.0, "chat1", "", "anthropic", 0, 50, 2000, 0),
            ("other", "cli", "gpt-9", 1000.0, 2000.0, None, "not Claude", "openrouter", 999, 999, 999, 999),
        ])

    def test_weights(self):
        row = {"input_tokens": 10, "output_tokens": 100, "cache_read_tokens": 10000, "cache_write_tokens": 1000}
        self.assertEqual(hs.weigh_hermes(row, W), 10 + 500 + 1000 + 1250)

    def test_first_sync_dates_at_last_activity_and_skips_other_providers(self):
        rows = hs.sync(self.q, W, home=self.h, now=5000.0)
        self.assertEqual({r["session"] for r in rows}, {"chat1", "sub1"})
        chat = [r for r in rows if r["session"] == "chat1"][0]
        self.assertEqual(chat["epoch"], 2000.0)
        self.assertEqual(chat["wt"], 2760)

    def test_second_sync_records_only_growth_at_now(self):
        hs.sync(self.q, W, home=self.h, now=5000.0)
        self.assertEqual(hs.sync(self.q, W, home=self.h, now=6000.0), [])
        update(self.h, "chat1", output_tokens=300)
        rows = hs.sync(self.q, W, home=self.h, now=7000.0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["wt"], 1000)
        self.assertEqual(rows[0]["epoch"], 7000.0)

    def test_counters_going_down_do_not_count_twice(self):
        hs.sync(self.q, W, home=self.h, now=5000.0)
        update(self.h, "chat1", cache_read_tokens=5)
        self.assertEqual(hs.sync(self.q, W, home=self.h, now=6000.0), [])

    def test_summary_groups_subagents_under_their_chat(self):
        hs.sync(self.q, W, home=self.h, now=5000.0)
        s = hs.summary(self.q, now=5000.0)
        self.assertEqual(s["week"], 2760 + 450)
        self.assertEqual(s["subagents"], 450)
        self.assertEqual(s["top"][0][0], "chat1")
        self.assertEqual(s["top"][0][1]["title"], "Def Jam")

    def test_missing_hermes_is_quiet(self):
        self.assertEqual(hs.read_sessions(tempfile.mkdtemp()), [])
        self.assertFalse(hs.available(tempfile.mkdtemp()))


class TaskNotification(unittest.TestCase):
    def test_background_task_notices_do_not_start_a_turn(self):
        os.environ["QUOTIENT_HERMES"] = "0"
        import quotient as q
        note = "<task-notification><task-id>b1</task-id><status>completed</status></task-notification>"
        self.assertFalse(q.is_turn_start({"type": "user", "message": {"content": note}}))
        self.assertFalse(q.is_turn_start({"type": "user", "message": {"content": [{"type": "text", "text": note}]}}))
        self.assertTrue(q.is_turn_start({"type": "user", "message": {"content": "fai il lavoro"}}))


class HermesHooks(unittest.TestCase):
    """The shell hooks end to end, through `quotient.py hermes-hook`, with a fake Hermes."""

    def setUp(self):
        self.q = tempfile.mkdtemp()
        self.h = fake_hermes([
            ("chat1", "cli", "claude-opus-5-5", 1000.0, 2000.0, None, "work", "anthropic", 10, 100, 10000, 1000)])
        self.vars = {"QUOTIENT_HOME": self.q, "HERMES_HOME": self.h, "QUOTIENT_LIMITS_LIVE": "0", "QUOTIENT_SHARE": "0"}

    def hook(self, event, response=None):
        import subprocess
        payload = {"hook_event_name": event, "session_id": "chat1", "extra": {"assistant_response": response or "",
                                                                               "model": "claude-opus-5-5"}}
        with mock.patch.dict(os.environ, self.vars):
            r = subprocess.run([sys.executable, os.path.join(HERE, "..", "scripts", "quotient.py"), "hermes-hook"],
                               input=json.dumps(payload), capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout or "{}")

    def jobs(self):
        try:
            with open(os.path.join(self.q, "jobs.jsonl"), encoding="utf-8") as f:
                return [json.loads(x) for x in f if x.strip()]
        except OSError:
            return []

    def test_protocol_in_full_once_then_short(self):
        first = self.hook("pre_llm_call")["context"]
        second = self.hook("pre_llm_call")["context"]
        self.assertIn("QUOTE:", first)
        self.assertIn("clarify", first)
        self.assertLess(len(second), len(first) / 3)

    def test_a_quoted_job_is_measured_from_choice_to_close(self):
        self.hook("pre_llm_call")
        self.hook("post_llm_call", "Preventivo pronto.\nQUOTE: essential=1000 good=2000 max=4000")
        self.hook("post_llm_call", "CHOICE: good\nPACE: today")
        update(self.h, "chat1", output_tokens=700)          # +600 output = 3000 wt of work
        self.hook("post_llm_call", "Fatto.\nJOB: CLOSE j1")
        jobs = self.jobs()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["raw_estimate"], 2000)
        self.assertEqual(jobs[0]["actual"], 3000)
        self.assertEqual(jobs[0]["source"], "hermes")

    def test_declined_and_dropped_jobs_are_not_measured(self):
        self.hook("post_llm_call", "QUOTE: essential=1000 good=2000 max=4000")
        self.hook("post_llm_call", "CHOICE: none")
        self.hook("post_llm_call", "QUOTE: essential=1000 good=2000 max=4000")
        self.hook("post_llm_call", "CHOICE: max")
        self.hook("post_llm_call", "JOB: DROP j1")
        self.assertEqual(self.jobs(), [])


if __name__ == "__main__":
    unittest.main()
