"""1.3.4: a small job pays almost nothing for Quotient (measured on 01/11/2026, docs/evidence/small-jobs.md): the short
rules at the start (lean_start), a small job's quote in one line (small_quote_line on), the steps every job takes in the
chat part (chat.steps_base), a quoted job measured without its CHOICE line (infer_choice), and the chat found under
CLAUDE_CONFIG_DIR. Run: python -m unittest discover tests"""

import os
import unittest
from unittest import mock

from test_quotient import Base, pv, usage


class TestDefaults(Base):
    def test_on_by_default(self):
        self.assertEqual((pv.DEFAULTS["lean_start"], pv.DEFAULTS["small_quote_line"], pv.DEFAULTS["infer_choice"],
                          pv.DEFAULTS["chat"]["steps_base"]), (1, 1, 1, 3))


class TestLeanStart(Base):
    def test_the_short_rules_fit_what_claude_code_shows_of_a_hook(self):
        # Claude Code cuts a hook's text over about 10,000 characters and saves it to a file: the whole protocol
        # (about 11,200) was cut, and the agent spent one more call reading it
        pv.store(("writing_wt_per_word",), 27)   # as by default (Base keeps the older tests' 0)
        pv.store(("share", "notice_shown"), True)   # the plain text, not the JSON with the sharing notice
        said = self.run_hook(pv.hook_session, {"session_id": "s1"})
        self.assertLess(len(said), 3000)
        self.assertGreater(len(pv.protocol(pv.config(), 1.0)), 10000)
        for kept in ("WHEN:", "threshold (300k wt)", "Estimate the WORK", "quote-table --raw good=<n>", "--type <type>",
                     "kind=<type>", "LAST message of your reply", "CHOICE: <level>", "JOB: CONTINUES", "ASIDE",
                     "LIMITS: five_hour=", "27 wt per word"):
            self.assertIn(kept, said)
        for left in ("AskUserQuestion", "rate new", "ONE DAY of work", "WEEK:"):
            self.assertNotIn(left, said)

    def test_off_the_whole_protocol_as_before(self):
        pv.store(("lean_start",), 0)
        said = self.run_hook(pv.hook_session, {"session_id": "s1"})
        self.assertIn("AskUserQuestion", said)
        self.assertIn("ONE DAY of work", said)

    def test_the_details_are_the_protocol_from_step_4_on(self):
        cfg = pv.config()
        details = pv.protocol_details(cfg, 1.0)
        self.assertIn("4) Open the choice window", details)
        self.assertIn("6) Installments", details)
        self.assertIn("WEEK:", details)
        self.assertNotIn("1) Estimate the WORK", details)
        self.assertEqual(pv.protocol(cfg, 1.0), "\n".join(x for x in pv.protocol_items(cfg, 1.0) if x) + "\n")

    def test_a_big_quote_brings_the_rest_once_per_chat(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "s1"}):
            first = pv.quote_table(pv.config(), {"good": 400000}, lang="en")
            self.assertIn("| Level |", first)
            self.assertIn("The rest of Quotient's rules", first)
            self.assertIn("4) Open the choice window", first)
            again = pv.quote_table(pv.config(), {"good": 500000}, lang="en")
            self.assertNotIn("4) Open the choice window", again)
            self.assertIn("already in this chat", again)
            # after a compaction the chat no longer holds them
            self.run_hook(pv.hook_session, {"session_id": "s1", "source": "compact"})
            self.assertIn("4) Open the choice window", pv.quote_table(pv.config(), {"good": 400000}, lang="en"))

    def test_a_small_quote_brings_nothing_more(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "s1"}):
            text = pv.quote_table(pv.config(), {"good": 40000}, lang="en", wtype="code")
        self.assertIn("QUOTE, a small job", text)
        self.assertNotIn("Open the choice window", text)
        self.assertLess(len(text), 1200)

    def test_first_use_one_line_then_the_questions_with_the_first_big_quote(self):
        pv.store(("configured",), False)
        said = self.run_hook(pv.hook_session, {"session_id": "s1"})
        self.assertIn("FIRST USE", said)
        self.assertNotIn("'Soglia'/'Threshold'", said)
        self.assertIn("'Soglia'/'Threshold'", pv.quote_table(pv.config(), {"good": 400000}, lang="en"))
        pv.store(("configured",), True)
        self.assertNotIn("'Soglia'/'Threshold'", pv.quote_table(pv.config(), {"good": 400000}, lang="en"))


class TestSmallQuote(Base):
    def test_one_line_by_default_with_the_type_note_and_the_total_shown(self):
        text = pv.quote_table(pv.config(), {"good": 60000}, context=30000, lang="it")
        self.assertIn("PREVENTIVO, lavoro piccolo", text)
        self.assertNotIn("| Livello |", text)
        self.assertIn("Add the type of work", text)
        saved = pv.load_json(os.path.join(pv.home(), "quote-table.json"), {})
        # 60k of work, (3 + 2) steps re-reading 30k tokens (3k wt): 15k of chat part
        self.assertEqual(saved["shown"], {"good": 75000})


class TestStepsBase(Base):
    def test_every_job_takes_three_steps_more_until_the_steps_are_learned(self):
        row = pv.quote_numbers(pv.config(), {"good": 30000}, "chat", 40000)["rows"][0]
        self.assertAlmostEqual(row["chat"], (3 + 1) * 4000)
        pv.store(("chat", "steps_base"), 0)
        row = pv.quote_numbers(pv.config(), {"good": 30000}, "chat", 40000)["rows"][0]
        self.assertAlmostEqual(row["chat"], 1 * 4000)

    def test_learned_steps_are_used_as_they_are(self):
        for i in range(3):
            pv.append_jsonl(os.path.join(pv.home(), "jobs.jsonl"), {
                "started": "2026-10-0%dT10:00:00+00:00" % (i + 1), "finished": "2026-10-0%dT10:30:00+00:00" % (i + 1),
                "session": "s%d" % i, "raw_estimate": 100000, "actual": 120000, "chat": 20000, "calls": 10,
                "choice": "good"})
        steps = pv.steps_per_million(pv.config())[0]
        row = pv.quote_numbers(pv.config(), {"good": 100000}, "chat", 40000)["rows"][0]
        self.assertAlmostEqual(row["chat"], steps * row["work"] / 1e6 * 4000)


class TestInferChoice(Base):
    def test_the_rules(self):
        one, two = {"good": 60000}, {"good": 60000, "max": 120000}
        self.assertIsNone(pv.infer_choice(one, "good", "", True))                   # a CHOICE of the quote: kept
        self.assertEqual(pv.infer_choice(one, None, "vai", True), "good")            # only JOB: CLOSE
        self.assertIsNone(pv.infer_choice(one, None, "cosa include?", False))        # no work done: no choice
        self.assertEqual(pv.infer_choice(one, "max", "", False), "good")             # a level the quote did not have
        self.assertEqual(pv.infer_choice(two, None, "Scelgo il livello più grande, tutto oggi", True), "max")
        self.assertEqual(pv.infer_choice(two, None, "the smallest one", True), "good")
        self.assertEqual(pv.infer_choice(two, None, "Buono — 60.000 token", True), "good")
        self.assertEqual(pv.infer_choice(two, "massimo", "", False), "max")
        self.assertIsNone(pv.infer_choice(two, None, "ok, go", True))               # two levels, none named
        self.assertEqual(pv.infer_choice(two, None, "ok, go", True, timer="max"), "max")

    def quote_then(self, options_line, user, reply, tools=()):
        self.t.user("add the option and the tests; quote first")
        self.t.call("q", usage(read=10000, output=200), texts=["Quote: one line.\n" + options_line])
        self.stop()
        self.t.user(user)
        for i, command in enumerate(tools):
            self.t._write({"type": "assistant", "requestId": "c%d" % i, "message": {
                "id": "msg_c%d" % i, "usage": usage(read=20000, output=100),
                "content": [{"type": "tool_use", "id": "b%d" % i, "name": "Bash", "input": {"command": command}}]}})
            self.t.tool_result()
        self.t.call("w", usage(read=40000, output=3000), texts=[reply])
        self.stop(reply)
        return pv.finished_jobs()

    def test_job_close_alone_is_measured(self):
        # 01/11/2026: 3 jobs of 11 ended with only `JOB: CLOSE`
        jobs = self.quote_then("QUOTE: good=30000 kind=other", "Scelgo il livello più grande, tutto oggi.",
                               "Fatto.\n\nJOB: CLOSE")
        self.assertEqual(len(jobs), 1)
        self.assertEqual((jobs[0]["choice"], jobs[0]["raw_estimate"], jobs[0]["type"]), ("good", 30000, "other"))

    def test_a_choice_the_quote_did_not_have(self):
        # 01/11/2026: `CHOICE: max` for a quote with only good
        jobs = self.quote_then("QUOTE: good=100000 kind=research", "Scelgo il livello più grande, tutto oggi.",
                               "Fatto.\n\nCHOICE: max\nPACE: today\nJOB: CLOSE")
        self.assertEqual([(j["choice"], j["raw_estimate"]) for j in jobs], [("good", 100000)])

    def test_the_level_the_user_named(self):
        jobs = self.quote_then("QUOTE: good=100000 max=200000 kind=code", "Scelgo il livello più grande, tutto oggi.",
                               "Fatto.\n\nJOB: CLOSE")
        self.assertEqual([(j["choice"], j["raw_estimate"]) for j in jobs], [("max", 200000)])

    def test_the_stopwatch_names_the_level(self):
        cmd = '"python" "C:/x/token-quotient/1.3.4/scripts/quotient.py" timer start --raw 100000 --level good'
        jobs = self.quote_then("QUOTE: good=100000 max=200000 kind=code", "ok", "Fatto.", tools=[cmd])
        self.assertEqual([(j["choice"], j["raw_estimate"]) for j in jobs], [("good", 100000)])

    def test_not_when_nothing_tells_the_level_or_no_work_was_done(self):
        self.assertEqual(self.quote_then("QUOTE: good=100000 max=200000", "ok, go", "Fatto.\n\nJOB: CLOSE"), [])
        self.assertEqual(self.quote_then("QUOTE: good=100000", "what does it include?", "It includes the tests."), [])

    def test_off(self):
        pv.store(("infer_choice",), 0)
        pv.store(("small_quote_line",), 0)
        self.assertEqual(self.quote_then("QUOTE: good=30000", "go", "Fatto.\n\nJOB: CLOSE"), [])

    def test_the_window_answer_in_the_same_turn(self):
        self.t.user("refactor it; quote first")
        self.t._write({"type": "assistant", "requestId": "a", "message": {"id": "msg_a", "usage": usage(read=10000, output=300),
                       "content": [{"type": "tool_use", "id": "ask1", "name": "AskUserQuestion", "input": {
                           "questions": [{"header": "Livello", "question": "Quale livello?",
                                          "options": [{"label": "Buono"}, {"label": "Massimo"}]}]}}]}})
        self.t._write({"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "ask1", "content": "Livello: Massimo"}]}})
        self.t.call("w", usage(read=40000, output=3000),
                    texts=["Fatto.\n\nQUOTE: good=400000 max=800000 kind=code\nJOB: CLOSE"])
        self.stop("Fatto.\n\nQUOTE: good=400000 max=800000 kind=code\nJOB: CLOSE")
        self.assertEqual([(j["choice"], j["raw_estimate"]) for j in pv.finished_jobs()], [("max", 800000)])


class TestConfigDir(Base):
    def test_the_chat_is_found_under_claude_config_dir(self):
        folder = os.path.join(self.dir, "cfg", "projects", "E--work")
        os.makedirs(folder)
        path = os.path.join(folder, "abc-123.jsonl")
        open(path, "w").close()
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": os.path.join(self.dir, "cfg")}):
            self.assertEqual(os.path.normcase(pv.find_transcript("abc-123")), os.path.normcase(path))


if __name__ == "__main__":
    unittest.main()
