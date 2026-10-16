"""1.1.5: in Hermes the quote's table and the clarify window come in the reply's messages before the last one, the QUOTE
line in the last one; the check of the quote reads them all. Run: python -m unittest discover tests"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
os.environ["QUOTIENT_TIMER_WINDOW"] = "0"   # the tests never open the stopwatch window
import hermes_source as hs  # noqa: E402

TABLE = ("| Level | Work | Expected time |\n|---|---|---|\n| Good | 2k | about 1 min |\n| Max | 4k | about 2 min |")


def fake_store(d):
    """A Hermes session store with one chat and the columns of its messages Quotient reads."""
    con = sqlite3.connect(os.path.join(d, "state.db"))
    con.execute("create table sessions (id text, source text, model text, started_at real, ended_at real, "
                "parent_session_id text, title text, last_activity_at real, estimated_cost_usd real, "
                "billing_provider text, api_call_count int, input_tokens int, output_tokens int, "
                "cache_read_tokens int, cache_write_tokens int)")
    con.execute("insert into sessions (id, source, model, billing_provider, input_tokens, output_tokens, "
                "cache_read_tokens, cache_write_tokens, api_call_count) values "
                "('chat1', 'cli', 'claude-opus-5-5', 'anthropic', 10, 100, 10000, 1000, 1)")
    con.execute("create table messages (id integer primary key, session_id text, role text, content text, "
                "tool_calls text, tool_name text, timestamp real)")
    con.commit()
    con.close()


def add(d, ts, role, content="", clarify=None, sid="chat1"):
    calls = None
    if clarify is not None:
        calls = json.dumps([{"id": "c1", "type": "function", "function": {
            "name": "clarify", "arguments": json.dumps({"questions": clarify})}}])
    con = sqlite3.connect(os.path.join(d, "state.db"))
    con.execute("insert into messages (session_id, role, content, tool_calls, tool_name, timestamp) values "
                "(?, ?, ?, ?, NULL, ?)", (sid, role, content, calls, ts))
    con.commit()
    con.close()


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        self.q = os.path.join(tmp, "q")
        self.h = os.path.join(tmp, "h")
        os.makedirs(self.h)
        fake_store(self.h)


class TestReplyTexts(Base):
    def test_the_lines_of_hermes_replies_and_the_choices_of_its_windows(self):
        add(self.h, 100.0, "user", "my message, never read")
        add(self.h, 101.0, "assistant", "Three levels.\n" + TABLE,
            clarify=[{"question": "Level?", "choices": ["Good (2k) about 1 min", "Max (4k) about 2 min"]},
                     {"question": "When?", "choices": ["Today", {"label": "In 3 days", "description": "at 2:00"}]}])
        add(self.h, 102.0, "tool", "Good")
        add(self.h, 103.0, "assistant", "QUOTE: good=2000 max=4000")
        add(self.h, 50.0, "assistant", "an older reply")
        add(self.h, 101.5, "assistant", "another chat", sid="chat2")
        lines = hs.reply_texts("chat1", 100.0, 110.0, home=self.h)
        self.assertEqual(lines[:2], ["Three levels.", "| Level | Work | Expected time |"])
        self.assertIn("Good (2k) about 1 min", lines)
        self.assertIn("In 3 days at 2:00", lines)
        self.assertEqual(lines[-1], "QUOTE: good=2000 max=4000")
        for absent in ("my message, never read", "Good", "an older reply", "another chat"):
            self.assertNotIn(absent, lines)

    def test_nothing_when_the_store_cannot_be_read(self):
        self.assertEqual(hs.reply_texts("chat1", 0, 1e12, home=os.path.join(self.h, "none")), [])
        self.assertEqual(hs.reply_texts("", 0, 1e12, home=self.h), [])
        add(self.h, 101.0, "assistant", None, clarify=None)
        con = sqlite3.connect(os.path.join(self.h, "state.db"))
        con.execute("update messages set tool_calls = 'not json'")
        con.commit()
        con.close()
        self.assertEqual(hs.reply_texts("chat1", 0, 1e12, home=self.h), [])


class TestHermesQuoteCheck(Base):
    """16/10/2026: a complete quote in Hermes was sent back as incomplete at the next message."""

    def hook(self, event, response=""):
        payload = {"hook_event_name": event, "session_id": "chat1",
                   "extra": {"assistant_response": response, "model": "claude-opus-5-5"}}
        env = dict(os.environ, QUOTIENT_HOME=self.q, HERMES_HOME=self.h, QUOTIENT_LIMITS_LIVE="0",
                   QUOTIENT_SHARE="0", QUOTIENT_TIMER_WINDOW="0")
        for name in ("QUOTIENT_JOB", "HERMES_SESSION_ID"):
            env.pop(name, None)
        r = subprocess.run([sys.executable, os.path.join(HERE, "..", "scripts", "quotient.py"), "hermes-hook"],
                           input=json.dumps(payload), capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout or "{}")

    def setUp(self):
        super().setUp()
        os.makedirs(self.q)
        with open(os.path.join(self.q, "jobs.jsonl"), "w", encoding="utf-8") as f:
            for i in range(3):   # 3 jobs measured with their time: a quote must give the time of each level
                f.write(json.dumps({"started": "2026-10-1%dT10:00:00+02:00" % i, "session": "x%d" % i,
                                    "choice": "good", "raw_estimate": 1000000, "actual": 1000000, "work": 1000000,
                                    "seconds": 600}) + "\n")

    def incomplete(self):
        with open(os.path.join(self.q, "hermes-jobs.json"), encoding="utf-8") as f:
            return json.load(f)["chat1"].get("quote_incomplete")

    def test_the_table_in_a_message_before_and_quote_in_the_last(self):
        self.hook("pre_llm_call")
        now = time.time()
        add(self.h, now, "user", "do it")
        add(self.h, now + 0.1, "assistant", "Three levels.\n" + TABLE)
        add(self.h, now + 0.2, "assistant", "QUOTE: good=2000 max=4000")
        self.hook("post_llm_call", "QUOTE: good=2000 max=4000")
        self.assertIsNone(self.incomplete())
        self.assertNotIn("INCOMPLETE", self.hook("pre_llm_call")["context"])

    def test_the_times_in_the_clarify_window(self):
        self.hook("pre_llm_call")
        now = time.time()
        add(self.h, now + 0.1, "assistant", "Which level?",
            clarify=[{"question": "Level?", "choices": ["Good (2k): about 1 min", "Max (4k): about 2 min"]}])
        self.hook("post_llm_call", "QUOTE: good=2000 max=4000\nCHOICE: good\nPACE: today\nJOB: CONTINUES")
        self.assertIsNone(self.incomplete())

    def test_without_the_table_the_quote_is_still_sent_back(self):
        self.hook("pre_llm_call")
        now = time.time()
        add(self.h, now + 0.1, "assistant", "Good or max?")
        self.hook("post_llm_call", "QUOTE: good=2000 max=4000")
        self.assertEqual(self.incomplete(), [["good", ["time"]], ["max", ["time"]]])
        self.assertIn("THE QUOTE BEFORE WAS INCOMPLETE ('good': its expected time; 'max': its expected time)",
                      self.hook("pre_llm_call")["context"])

    def test_the_table_of_the_reply_before_does_not_count(self):
        add(self.h, time.time() - 60, "assistant", TABLE)   # an earlier reply: not this quote's
        self.hook("pre_llm_call")
        self.hook("post_llm_call", "QUOTE: good=2000 max=4000")
        self.assertEqual(self.incomplete(), [["good", ["time"]], ["max", ["time"]]])


if __name__ == "__main__":
    unittest.main()
