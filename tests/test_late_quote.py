"""A quote written when the work is already done opens no job (measured on 01/11/2026, 1 job of 6 in normal use: the agent
wrote `QUOTE: good=130000 kind=research` and `JOB: CONTINUES` at the end of a job it had already done; Quotient opened a
job with that estimate and never closed it, so the next job of the chat was measured together with it). A quote made
before the work (quote-table, the choice window, an earlier message, or an earlier turn's pending quote) still opens
its job. Run: python -m unittest discover tests"""

import unittest

from test_quotient import Base, pv, usage

QUOTE = "QUOTE: good=130000 kind=research"


class Late(Base):
    def tool(self, rid, name="WebSearch", command=None, inputs=None):
        """One tool call of the agent and its result."""
        self.t._write({"type": "assistant", "requestId": rid, "message": {
            "id": "msg_" + rid, "usage": usage(read=20000, output=100),
            "content": [{"type": "tool_use", "id": "b" + rid, "name": name,
                         "input": inputs if inputs is not None else ({"command": command} if command else {})}]}})
        self.t.tool_result()

    def final(self, text, rid="fin"):
        self.t.call(rid, usage(read=40000, output=2000), texts=[text])
        self.stop(text)

    def state(self):
        return pv.load_json(pv.session_path("s1"), {})


class TestQuoteAfterTheWork(Late):
    def test_the_quote_at_the_end_of_a_done_job_opens_no_job(self):
        self.t.user("compare 5 free programs for the household budget")
        for i in range(3):
            self.tool("w%d" % i)
        self.final("Here is the comparison.\n\n%s\nJOB: CONTINUES" % QUOTE)
        state = self.state()
        self.assertFalse(state.get("job"))
        self.assertFalse(state.get("pending"))
        # the next job of the chat is not measured together with it
        self.t.user("now write a short summary of it")
        self.tool("s0", name="Write")
        self.final("Done.", rid="fin2")
        self.assertEqual(pv.finished_jobs(), [])
        self.assertFalse(self.state().get("job"))

    def test_the_same_with_the_choice_written_out(self):
        self.t.user("compare 5 free programs")
        self.tool("w0")
        self.final("Here it is.\n\n%s\nCHOICE: good\nPACE: today\nJOB: CLOSE" % QUOTE)
        self.assertEqual(pv.finished_jobs(), [])
        self.assertFalse(self.state().get("job"))

    def test_a_job_close_alone_after_the_work_is_not_measured_either(self):
        self.t.user("compare 5 free programs")
        self.tool("w0")
        self.tool("w1", name="Bash", command="python spese.py riepilogo")
        self.final("Done.\n\n%s\nJOB: CLOSE" % QUOTE)
        self.assertEqual(pv.finished_jobs(), [])

class TestQuoteBeforeTheWork(Late):
    def test_quote_table_then_the_work_then_the_lines_at_the_end(self):
        # the protocol: quote-table, the window, the work, and the machine lines in the last message
        self.t.user("write the importer and its 15 tests; quote first")
        self.tool("q0", name="Bash", command='"python" "C:/x/quotient.py" quote-table --raw good=400000 max=800000 --kind code')
        self.tool("a0", name="AskUserQuestion", inputs={"questions": [{"header": "Livello", "question": "Quale livello?",
                                                                       "options": [{"label": "Buono"}, {"label": "Massimo"}]}]})
        self.tool("w0", name="Write")
        self.tool("w1", name="Bash", command="python -m unittest")
        self.final("Done.\n\nQUOTE: good=400000 max=800000 kind=code\nCHOICE: good\nPACE: today\nJOB: CLOSE")
        jobs = pv.finished_jobs()
        self.assertEqual([(j["choice"], j["raw_estimate"]) for j in jobs], [("good", 400000)])

    def test_quote_table_alone_before_the_work(self):
        # a small job: quote-table, the one line, the user's yes in the same turn, the work, JOB: CLOSE
        self.t.user("add a total line to the report; how much would it cost?")
        self.tool("q0", name="Bash", command='"python" "C:/x/quotient.py" quote-table --raw good=60000 --kind code')
        self.tool("w0", name="Edit")
        self.final("Done.\n\n%s\nCHOICE: good\nPACE: today\nJOB: CLOSE" % "QUOTE: good=60000 kind=code")
        self.assertEqual([(j["choice"], j["raw_estimate"]) for j in pv.finished_jobs()], [("good", 60000)])

    def test_the_quote_in_an_earlier_message_of_the_turn(self):
        self.t.user("refactor it; quote first")
        self.t.call("q", usage(read=10000, output=300), texts=["The quote.\nQUOTE: good=250000 kind=code"], tools=1)
        self.t.tool_result()
        self.tool("w0", name="Edit")
        self.final("Done.\n\nCHOICE: good\nPACE: today\nJOB: CONTINUES")
        job = self.state().get("job")
        self.assertEqual((job["choice"], job["raw_estimate"]), ("good", 250000))

    def test_the_quote_of_an_earlier_turn_measures_the_work_that_follows(self):
        self.t.user("write the importer; how much would it cost?")
        self.t.call("q", usage(read=10000, output=200), texts=["One line.\nQUOTE: good=30000 kind=code"])
        self.stop()
        self.assertEqual(self.state()["pending"]["options"], {"good": 30000})
        self.t.user("yes, go")
        self.tool("w0", name="Write")
        # the line written again with the work, as the agents do
        self.final("Done.\n\nQUOTE: good=30000 kind=code\nCHOICE: good\nPACE: today\nJOB: CLOSE")
        self.assertEqual([(j["choice"], j["raw_estimate"]) for j in pv.finished_jobs()], [("good", 30000)])

    def test_a_reply_with_no_tool_call_keeps_its_quote(self):
        self.t.user("explain it and say what it costs")
        self.t.call("q", usage(read=10000, output=500), texts=["Explained.\nQUOTE: good=30000 kind=other\nCHOICE: good\nPACE: today\nJOB: CLOSE"])
        self.stop()
        self.assertEqual([(j["choice"], j["raw_estimate"]) for j in pv.finished_jobs()], [("good", 30000)])

    def test_a_quote_shown_after_some_reading_without_a_job_line_stays_pending(self):
        # the agent read files to estimate, then showed the quote and asked: no CHOICE, no JOB line, nothing is done yet
        self.t.user("refactor it; quote first")
        self.tool("r0", name="Read")
        self.tool("r1", name="Read")
        self.final("The quote:\nQUOTE: good=250000 kind=code\nWhich level?")
        self.assertEqual(self.state()["pending"]["options"], {"good": 250000})


if __name__ == "__main__":
    unittest.main()
