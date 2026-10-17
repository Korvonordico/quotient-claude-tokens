"""1.1.8: what 9 small jobs measured in new sessions taught (16/10/2026), each behind a key that is off by default:
the rule for texts (writing_wt_per_word), the line on the web searches' small model (note_web_haiku), one line for a
small job's quote (small_quote_line), the margin at the end of a job (margin_percent) and a quote of its own for a task
added to a job (requote_on_addition). Run: python -m unittest discover tests"""

import json
import os
import unittest

from test_quotient import Base, pv, usage

KEYS = ("writing_wt_per_word", "note_web_haiku", "small_quote_line", "margin_percent", "requote_on_addition")


class TestOffByDefault(Base):
    def test_all_off(self):
        for key in KEYS:
            self.assertEqual(pv.DEFAULTS[key], 0, key)

    def test_nothing_new_while_off(self):
        cfg = pv.config()
        text = pv.protocol(cfg, 1.0)
        for new in ("TEXTS (kind=writing)", "ADDITIONS:", "a task added to it", "ONE line"):
            self.assertNotIn(new, text)
        self.assertIn("At the user's first message in this session, before anything else", pv.setup_instructions(cfg))
        table = pv.quote_table(cfg, {"good": 50000}, lang="it", wtype="writing", words=900)
        self.assertIn("| Livello |", table)
        self.assertNotIn("Testo di circa", table)
        self.assertNotIn("lavoro piccolo", table)
        self.assertIsNone(pv.writing_raw(cfg, 900))
        row = {"choice": "good", "raw_estimate": 100000, "factor_used": 1.0, "actual": 105000, "chat": 0,
               "work": 105000, "type": "research", "searches": 3}
        note = pv.closed_note(row, cfg)
        self.assertNotIn("margin", note)
        self.assertNotIn("haiku", note)
        self.assertEqual(pv.addition_hint(cfg), "")


class TestWritingRule(Base):
    """The texts were quoted 4 times under: 10 to 19 wt a word in the quotes, 49 to 56 measured."""

    def setUp(self):
        super().setUp()
        pv.store(("writing_wt_per_word",), 50)

    def test_the_two_texts_of_the_measures(self):
        cfg = pv.config()
        article, low, high = pv.writing_raw(cfg, 881)
        self.assertAlmostEqual(article, 44050)          # about 44,000 (it cost 49,571)
        self.assertAlmostEqual(low, 881 * 25)
        self.assertAlmostEqual(high, 881 * 55)
        self.assertAlmostEqual(pv.writing_raw(cfg, 5073)[0], 253650)   # about 254,000 (it cost 257,043)

    def test_in_the_protocol(self):
        text = pv.protocol(pv.config(), 1.0)
        self.assertIn("TEXTS (kind=writing): count about 50 wt per word of the final text (between 25 and 55)", text)
        self.assertIn("weight 5", text)
        self.assertIn("re-read at every call after it", text)
        self.assertIn("--words <n>", text)

    def test_quote_table_with_the_words(self):
        table = pv.quote_table(pv.config(), {"good": 250000}, lang="it", wtype="writing", words=5000)
        self.assertIn("Testo di circa 5.000 parole: con la regola dei testi (50 token pesati a parola finale, fra 25 e "
                      "55) il lavoro grezzo è circa 250.000, fra 125.000 e 275.000.", table)
        self.assertIn("| Livello |", table)

    def test_an_estimate_under_the_rule_is_made_again(self):
        table = pv.quote_table(pv.config(), {"good": 50000}, lang="en", wtype="writing", words=5000)
        self.assertIn("Nothing to copy yet", table)
        self.assertIn("under the rule for 5,000 words (125k to 275k, about 250k)", table)
        self.assertNotIn("| Level |", table)
        self.assertFalse(os.path.exists(os.path.join(pv.home(), "quote-table.json")))   # no quote was given

    def test_a_text_without_its_words(self):
        table = pv.quote_table(pv.config(), {"good": 400000}, lang="en", wtype="writing")
        self.assertIn("run quote-table again with --words", table)
        self.assertNotIn("--words", pv.quote_table(pv.config(), {"good": 400000}, lang="en", wtype="code"))

    def test_the_command_takes_the_words(self):
        said = self.run_hook(lambda: pv.main(["quote-table", "--raw", "good=250000", "--type", "writing", "--words",
                                              "5000", "--lang", "en"]), {})
        self.assertIn("A text of about 5,000 words", said)


class TestSmallQuoteLine(Base):
    """In a new session the full quote cost about 70,000 wt, more than the small job itself."""

    def setUp(self):
        super().setUp()
        pv.store(("small_quote_line",), 1)

    def test_one_line_under_the_threshold(self):
        text = pv.quote_table(pv.config(), {"good": 80000}, lang="it", wtype="code")
        self.assertIn("PREVENTIVO, lavoro piccolo (sotto la soglia di 300.000 token pesati): circa 80.000 token pesati "
                      "(lavoro 80.000)", text)
        self.assertNotIn("| Livello |", text)
        self.assertNotIn("RITMO", text)
        self.assertIn("no choice window", text)
        self.assertIn("QUOTE: good=80000 kind=code", text)
        saved = pv.load_json(os.path.join(pv.home(), "quote-table.json"), {})
        self.assertEqual((saved["options"], saved["small"]), ({"good": 80000}, True))

    def test_the_biggest_level_and_the_chat_part(self):
        text = pv.quote_table(pv.config(), {"essential": 40000, "good": 100000}, context=200000, lang="en")
        # re-reading 200k tokens (20k wt) at each of ~3.3 calls of 30k wt of work: about +67k
        self.assertIn("about 166,667 weighted tokens (work 100,000 + chat part 66,667)", text)
        self.assertIn("QUOTE: good=100000", text)

    def test_the_full_table_over_the_threshold_and_for_installments(self):
        self.assertIn("| Level |", pv.quote_table(pv.config(), {"good": 400000}, lang="en"))
        self.assertIn("| Level |", pv.quote_table(pv.config(), {"good": 80000}, kind="rate", lang="en"))

    def test_not_sent_back_as_incomplete(self):
        pv.quote_table(pv.config(), {"good": 80000}, lang="en")
        self.assertEqual(pv.quote_gaps(pv.config(), {"good": 80000}, "QUOTE, a small job: about 80,000"), [])

    def test_the_first_use_questions_wait(self):
        text = pv.setup_instructions(pv.config())
        self.assertIn("Before the first quote of a job above the threshold (300k wt; a small job does not need these "
                      "questions)", text)
        self.assertNotIn("At the user's first message", text)

    def test_said_in_the_protocol(self):
        self.assertIn("for a job under the threshold it gives ONE line", pv.protocol(pv.config(), 1.0))

    def one_line_then_close(self):
        self.t.user("fix the module; quote first")
        self.t.call("q", usage(read=10000, output=200), texts=["Quote: one line.\nQUOTE: good=60000 kind=code"])
        self.stop()
        self.t.user("I choose the biggest level, all today")
        self.t.call("w", usage(read=40000, output=3000), texts=["Fixed the six bugs.\n\nJOB: CLOSE"])
        self.stop("Fixed the six bugs.\n\nJOB: CLOSE")

    def test_the_work_done_chooses_the_one_level(self):
        # 17/10/2026: after the one line the agent wrote only JOB: CLOSE, no CHOICE, and the job went unmeasured
        self.one_line_then_close()
        jobs = pv.finished_jobs()
        self.assertEqual(len(jobs), 1)
        self.assertEqual((jobs[0]["choice"], jobs[0]["raw_estimate"], jobs[0]["type"]), ("good", 60000, "code"))
        self.assertIsNone(pv.load_json(pv.session_path("s1"), {})["pending"])

    def test_not_without_the_key_nor_without_a_job_line(self):
        pv.store(("small_quote_line",), 0)
        self.one_line_then_close()
        self.assertEqual(pv.finished_jobs(), [])
        pv.store(("small_quote_line",), 1)
        self.t.user("what does it include?")
        self.t.call("a", usage(read=10000, output=100), texts=["It includes the tests."])
        self.stop("It includes the tests.")
        self.assertEqual(pv.finished_jobs(), [])


class TestMargin(Base):
    """The same job done again cost from -9% to +10%."""

    def row(self, work):
        return {"choice": "good", "raw_estimate": 100000, "factor_used": 1.0, "actual": work, "chat": 0, "work": work}

    def test_within_the_margin(self):
        pv.store(("margin_percent",), 15)
        cfg = pv.config()
        self.assertIn("x1.10: within the ±15% margin", pv.closed_note(self.row(110000), cfg))
        self.assertIn("x0.90: within the ±15% margin", pv.closed_note(self.row(90000), cfg))
        self.assertNotIn("margin", pv.closed_note(self.row(120000), cfg))
        self.assertNotIn("margin", pv.closed_note(self.row(80000), cfg))

    def test_the_installments_report(self):
        pv.store(("margin_percent",), 15)
        folder = os.path.join(self.dir, "job")
        os.makedirs(folder)
        job = {"name": "j", "quote": 1000000, "factor_at_quote": 1.0, "daily_cap": 500000, "status": "done",
               "dir": folder}
        runs = [{"wt": 520000, "started": "2026-10-17T03:00:00+02:00", "finished": "2026-10-17T03:40:00+02:00"},
                {"wt": 540000, "started": "2026-10-18T03:00:00+02:00", "finished": "2026-10-18T03:40:00+02:00"}]
        text = "\n".join(pv.report_lines("j", job, runs, 0, folder))
        self.assertIn("106% of it spent (x1.06: within the ±15% margin", text)
        runs[1]["wt"] = 800000
        self.assertNotIn("margin", "\n".join(pv.report_lines("j", job, runs, 0, folder)))


class TestWebNote(Base):
    """Claude Code's web searches also run haiku, which is not in the session's log (about 12% of the session)."""

    def setUp(self):
        super().setUp()
        pv.store(("note_web_haiku",), 1)

    def search_call(self, request_id, u, texts=(), searches=0):
        for i in range(searches):
            self.t._write({"type": "assistant", "requestId": request_id, "message": {
                "id": "msg_" + request_id, "usage": u,
                "content": [{"type": "tool_use", "id": "s%d" % i, "name": "WebSearch", "input": {"query": "q"}}]}})
        self.t.call(request_id, u, texts=texts)

    def test_a_research_job_counts_its_searches(self):
        self.t.user("check these claims")
        self.t.call("q", usage(read=10000, output=200), texts=["Quote.\nQUOTE: good=100k kind=research"])
        self.stop()
        self.t.user("good")
        self.search_call("w1", usage(read=20000, output=1000), texts=["CHOICE: good"], searches=2)
        self.t.tool_result()
        self.search_call("w2", usage(read=30000, output=1000), texts=["JOB: CONTINUES"], searches=1)
        self.stop()
        self.t.user("go on")
        self.search_call("w3", usage(read=40000, output=1000), texts=["Done."], searches=4)
        self.stop("Done.")
        job = pv.finished_jobs()[-1]
        self.assertEqual((job["type"], job["searches"]), ("research", 7))
        note = pv.load_json(pv.session_path("s1"), {})["last_closed"]
        self.assertIn("web searches (7 in this job) also ran a small model (haiku)", note)
        self.assertIn("about 12% of the session at list prices", note)

    def test_a_research_job_without_searches_seen(self):
        row = {"choice": "good", "raw_estimate": 100000, "actual": 100000, "chat": 0, "work": 100000, "type": "research"}
        self.assertIn("Claude Code's web searches also ran", pv.closed_note(row, pv.config()))
        row["type"] = "code"
        self.assertNotIn("haiku", pv.closed_note(row, pv.config()))

    def test_a_research_job_in_installments(self):
        folder = os.path.join(self.dir, "job")
        os.makedirs(folder)
        job = {"name": "j", "quote": 1000000, "factor_at_quote": 1.0, "daily_cap": 500000, "status": "done",
               "dir": folder, "type": "research"}
        runs = [{"wt": 900000, "started": "2026-10-17T03:00:00+02:00", "finished": "2026-10-17T03:40:00+02:00"}]
        self.assertIn("Note: Claude Code's web searches also ran a small model (haiku)",
                      "\n".join(pv.report_lines("j", job, runs, 0, folder)))
        job["type"] = "code"
        self.assertNotIn("haiku", "\n".join(pv.report_lines("j", job, runs, 0, folder)))


class TestAdditions(Base):
    """The jobs with signs of additions cost x1.82 their raw quote, the others x1.20; a new quote made halfway came
    within x0.84 to x1.14 of the real cost."""

    def setUp(self):
        super().setUp()
        pv.store(("requote_on_addition",), 1)

    def test_in_the_protocol(self):
        text = pv.protocol(pv.config(), 1.0)
        self.assertIn("ADDITIONS: a message that adds a task to the job", text)
        self.assertIn("gets a quote of its own BEFORE you do it", text)
        self.assertIn("A new QUOTE line closes the open job with what it cost so far", text)
        self.assertIn("adds to its cost, that a task added to it gets a quote of its own, and that messages", text)

    def test_said_once_in_the_line_of_the_open_job(self):
        self.t.user("write it")
        self.t.call("q", usage(read=10000, output=200), texts=["QUOTE: good=100k kind=code"])
        self.stop()
        self.t.user("good")
        self.t.call("w1", usage(read=20000, output=1000), texts=["CHOICE: good\nJOB: CONTINUES"])
        self.stop()
        first = self.run_hook(pv.hook_prompt, {"session_id": "s1", "transcript_path": self.t.path})
        self.assertIn("quote the new part before doing it (ADDITIONS)", first)
        second = self.run_hook(pv.hook_prompt, {"session_id": "s1", "transcript_path": self.t.path})
        self.assertIn("Open job", second)
        self.assertNotIn("ADDITIONS", second)

    def test_a_new_quote_measures_the_addition_apart(self):
        # what the protocol relies on: a new QUOTE line closes the job so far and the addition is a job of its own
        self.t.user("write it")
        self.t.call("q", usage(read=10000, output=200), texts=["QUOTE: good=100k kind=code"])
        self.stop()
        self.t.user("good")
        self.t.call("w1", usage(read=20000, output=10000), texts=["CHOICE: good\nJOB: CONTINUES"])
        self.stop()
        self.t.user("add a CSV export too")
        self.t.call("a", usage(read=30000, output=200), texts=["Quote for the addition.\nQUOTE: good=40k kind=code"])
        self.stop()
        self.assertEqual(len(pv.finished_jobs()), 1)
        state = pv.load_json(pv.session_path("s1"), {})
        self.assertEqual(state["pending"]["options"], {"good": 40000})
        self.assertIsNone(state["job"])


if __name__ == "__main__":
    unittest.main()
