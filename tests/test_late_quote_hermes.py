"""The same rule in Hermes: a quote written when the work is already done opens no job (see test_late_quote.py for Claude
Code). In Hermes the job opens when the last message of a reply holds QUOTE and CHOICE, and it counts from the start of
that reply, so a QUOTE + CHOICE written at the end of a job already done measured that job against an estimate nobody
had made; a late QUOTE alone left a quote waiting that a plain yes at the next message opened. A quote made before the
work (quote-table, the clarify window, an earlier message, or an earlier reply's pending quote) still opens its job.
Run: python -m unittest discover tests"""

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
from test_v115 import fake_store  # noqa: E402

QUOTE = "QUOTE: good=130000 kind=research"
LINES = "CHOICE: good\nPACE: today"


class Late(unittest.TestCase):
    """A fake Hermes (its session store, with the messages of each reply) and the hooks run end to end."""

    def setUp(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        self.q = os.path.join(tmp, "q")
        self.h = os.path.join(tmp, "h")
        os.makedirs(self.q)
        os.makedirs(self.h)
        fake_store(self.h)
        self.grown = 0

    def hook(self, event, response=""):
        payload = {"hook_event_name": event, "session_id": "chat1",
                   "extra": {"assistant_response": response, "model": "claude-opus-5-5"}}
        env = dict(os.environ, QUOTIENT_HOME=self.q, HERMES_HOME=self.h, QUOTIENT_LIMITS_LIVE="0", QUOTIENT_SHARE="0",
                   QUOTIENT_TIMER_WINDOW="0", QUOTIENT_CLAUDE_DIR=os.path.join(self.q, "no-claude-dir"))
        for name in ("QUOTIENT_JOB", "HERMES_SESSION_ID"):
            env.pop(name, None)
        r = subprocess.run([sys.executable, os.path.join(HERE, "..", "scripts", "quotient.py"), "hermes-hook"],
                           input=json.dumps(payload), capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout or "{}")

    def add(self, role, content=None, calls=None, tool=None):
        listed = json.dumps([{"id": "c1", "type": "function", "function": {
            "name": name, "arguments": json.dumps(args)}} for name, args in calls]) if calls else None
        con = sqlite3.connect(os.path.join(self.h, "state.db"))
        con.execute("insert into messages (session_id, role, content, tool_calls, tool_name, timestamp) values "
                    "(?, ?, ?, ?, ?, ?)", ("chat1", role, content, listed, tool, time.time()))
        con.commit()
        con.close()

    def user(self, text="do it"):
        """The user's message: the reply starts (pre_llm_call), as in Hermes."""
        self.hook("pre_llm_call")
        self.add("user", text)

    def tool(self, name="web_search", args=None, text=None):
        """The agent calls a tool (with some text in the same message, if given) and gets its result."""
        self.add("assistant", text, calls=[(name, args or {"query": "x"})])
        self.add("tool", "result", tool=name)

    def work(self, name="web_search", args=None):
        self.tool(name, args)
        self.grown += 300
        con = sqlite3.connect(os.path.join(self.h, "state.db"))
        con.execute("update sessions set output_tokens = ?", (100 + self.grown,))
        con.commit()
        con.close()

    def final(self, text):
        self.add("assistant", text)
        self.hook("post_llm_call", text)

    def state(self):
        with open(os.path.join(self.q, "hermes-jobs.json"), encoding="utf-8") as f:
            return json.load(f)["chat1"]

    def jobs(self):
        try:
            with open(os.path.join(self.q, "jobs.jsonl"), encoding="utf-8") as f:
                return [json.loads(x) for x in f if x.strip()]
        except OSError:
            return []

    def measured(self):
        return [(j["choice"], j["raw_estimate"]) for j in self.jobs()]


class TestQuoteAfterTheWork(Late):
    def test_the_quote_and_choice_at_the_end_of_a_done_job_open_no_job(self):
        self.user("compare 5 free programs for the household budget")
        for i in range(3):
            self.work()
        self.final("Here is the comparison.\n\n%s\n%s\nJOB: CONTINUES" % (QUOTE, LINES))
        self.assertIsNone(self.state().get("job"))
        self.assertIsNone(self.state().get("quote"))
        # the next job of the chat is not measured together with it
        self.user("now write a short summary of it")
        self.work("write_file")
        self.final("Done.\nJOB: CLOSE")
        self.assertEqual(self.jobs(), [])

    def test_the_same_closed_in_the_same_reply(self):
        self.user("compare 5 free programs")
        self.work()
        self.final("Here it is.\n\n%s\n%s\nJOB: CLOSE" % (QUOTE, LINES))
        self.assertEqual(self.jobs(), [])
        self.assertIsNone(self.state().get("job"))

    def test_a_late_quote_alone_leaves_no_quote_waiting(self):
        # without a CHOICE the quote waited, and a plain yes (JOB: CLOSE) at the next message opened a job with it
        self.user("compare 5 free programs")
        self.work()
        self.work("terminal", {"command": "python spese.py riepilogo"})
        self.final("Done.\n\n%s\nJOB: CONTINUES" % QUOTE)
        self.assertIsNone(self.state().get("quote"))
        self.user("thanks, now close it")
        self.final("Closed.\nJOB: CLOSE")
        self.assertEqual(self.jobs(), [])


class TestQuoteBeforeTheWork(Late):
    def test_quote_table_the_window_the_work_then_the_lines_at_the_end(self):
        # the protocol in Hermes: quote-table, the clarify window, the work, the machine lines in the last message
        self.user("write the importer and its 15 tests; quote first")
        self.tool("terminal", {"command": "python quotient.py quote-table --raw good=400000 max=800000 --kind code"})
        self.tool("clarify", {"questions": [{"question": "Level?", "choices": ["Good", "Max"]}]})
        self.work("write_file")
        self.work("terminal", {"command": "python -m unittest"})
        self.final("Done.\n\nQUOTE: good=400000 max=800000 kind=code\n%s\nJOB: CLOSE" % LINES)
        self.assertEqual(self.measured(), [("good", 400000)])

    def test_quote_table_alone_before_the_work(self):
        # a small job: quote-table, the one line, the work, JOB: CLOSE
        self.user("add a total line to the report; how much would it cost?")
        self.tool("terminal", {"command": "python quotient.py quote-table --raw good=60000 --kind code"})
        self.work("patch")
        self.final("Done.\n\nQUOTE: good=60000 kind=code\n%s\nJOB: CLOSE" % LINES)
        self.assertEqual(self.measured(), [("good", 60000)])

    def test_the_quote_in_an_earlier_message_of_the_reply(self):
        self.user("refactor it; quote first")
        self.tool(text="The quote.\nQUOTE: good=250000 kind=code")
        self.work("patch")
        self.final("Done.\n\nQUOTE: good=250000 kind=code\n%s\nJOB: CONTINUES" % LINES)
        job = self.state()["job"]
        self.assertEqual((job["choice"], job["raw_estimate"]), ("good", 250000))

    def test_the_quote_of_an_earlier_reply_measures_the_work_that_follows(self):
        self.user("write the importer; how much would it cost?")
        self.final("One line.\nQUOTE: good=30000 kind=code")
        self.assertEqual(self.state()["quote"]["options"], {"good": 30000})
        self.user("yes, go")
        self.work("write_file")
        # the line written again with the work, as the agents do
        self.final("Done.\n\nQUOTE: good=30000 kind=code\n%s\nJOB: CLOSE" % LINES)
        self.assertEqual(self.measured(), [("good", 30000)])

    def test_the_plain_yes_to_a_one_line_quote_still_measures_it(self):
        self.user("write the importer; how much would it cost?")
        self.final("One line.\nQUOTE: good=30000 kind=code")
        self.user("yes, go")
        self.work("write_file")
        self.final("Done.\nJOB: CLOSE")
        self.assertEqual(self.measured(), [("good", 30000)])

    def test_a_reply_with_no_tool_call_keeps_its_quote(self):
        self.user("explain it and say what it costs")
        self.final("Explained.\nQUOTE: good=30000 kind=other\n%s\nJOB: CLOSE" % LINES)
        self.assertEqual(self.measured(), [("good", 30000)])

    def test_a_quote_shown_after_some_reading_without_a_job_line_stays_pending(self):
        # the agent read files to estimate, then showed the quote and asked: no CHOICE, no JOB line, nothing is done yet
        self.user("refactor it; quote first")
        self.tool("read_file")
        self.tool("read_file")
        self.final("The quote:\nQUOTE: good=250000 kind=code\nWhich level?")
        self.assertEqual(self.state()["quote"]["options"], {"good": 250000})

    def test_a_store_that_cannot_be_read_keeps_the_quote_as_before(self):
        # no message of the reply to read: nothing says the quote came late, so it counts, as it always did
        self.user("compare 5 free programs")
        self.work()
        con = sqlite3.connect(os.path.join(self.h, "state.db"))
        con.execute("drop table messages")
        con.commit()
        con.close()
        self.hook("post_llm_call", "Here it is.\n\n%s\n%s\nJOB: CLOSE" % (QUOTE, LINES))
        self.assertEqual(self.measured(), [("good", 130000)])


if __name__ == "__main__":
    unittest.main()
