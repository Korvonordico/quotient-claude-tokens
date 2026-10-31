"""1.1.3: the levels and the paces by the size of the job (1 to 4 options, the window adds its free field), a choice of
the user's own (CHOICE: custom=<n>), a pace with a time, and the quote worked out by Quotient (quote-table) with its
check at the end of the reply. Run: python -m unittest discover tests"""

import json
import os
import re
import sys
from unittest import mock

from q_patch import patch_q

from test_quotient import Base, usage, pv, HERE
from test_v111 import InstallmentBase
from test_hermes import fake_hermes

# what Quotient knows in these tests: 10 min per 1M wt of work, 1% of the 5 hours = 50k wt, 1% of the week = 500k wt,
# 20% of the 5 hours and 30% of the week used
KNOWN = [("minutes_per_million", (10.0, 3)), ("capacity", {"per_point": 50000.0}),
         ("week_capacity", {"per_point": 500000.0}),
         ("latest_limits", {"five_hour": {"used": 20, "resets": None}, "seven_day": {"used": 30, "resets": None}})]


class Known(Base):
    def known(self, names=None):
        for name, value in KNOWN:
            if names is None or name in names:
                patcher = patch_q(pv, name, return_value=value)
                patcher.start()
                self.addCleanup(patcher.stop)

    def pace_lines(self, text):
        start = text.index("PACE (4 options at most):" if "PACE (" in text else "RITMO (al massimo 4 scelte):")
        return [line for line in text[start:].splitlines()[1:] if re.match(r"^\d\. ", line)]


class TestParsing(Base):
    def test_a_plan_in_the_users_words_with_its_time(self):
        self.assertEqual(pv.parse_plan("5 giorni alle 2:00"), {"days": 5, "at": "02:00"})
        self.assertEqual(pv.parse_plan("days=3 daily=200k at=02:30"), {"days": 3, "daily": 200000, "at": "02:30"})
        self.assertEqual(pv.parse_plan("3 days, 200k a day, at 2am"), {"days": 3, "daily": 200000, "at": "02:00"})
        self.assertEqual(pv.parse_plan("50.000 al giorno"), {"daily": 50000})
        self.assertEqual(pv.parse_plan("4 giorni a mezzanotte"), {"days": 4, "at": "00:00"})
        self.assertEqual(pv.parse_plan("7 giorni, 1,5 milioni al giorno, alle ore 23.30"),
                         {"days": 7, "daily": 1500000, "at": "23:30"})
        self.assertEqual(pv.parse_plan("every day at 9pm"), {"at": "21:00"})
        self.assertEqual(pv.parse_plan("2 al giorno"), {})          # two a day is not an amount of tokens
        self.assertEqual(pv.parse_plan("tutto oggi"), {})

    def test_the_pace_line_keeps_a_plan_with_a_time(self):
        self.assertEqual(pv.parse_pace("PACE: today"), "today")
        self.assertEqual(pv.parse_pace("PACE: days=5 at=02:00"), "days=5 at=02:00")
        self.assertEqual(pv.parse_pace("RITMO: tutto in 3 giorni alle 4:00"), "tutto in 3 giorni alle 4:00")
        self.assertEqual(pv.parse_pace("PACE: new chat"), "new-chat")
        self.assertEqual(pv.parse_pace("PACE: apart"), "apart")

    def test_a_choice_of_the_users_own_comes_with_its_estimate(self):
        self.assertEqual(pv.parse_custom("CHOICE: custom=700k"), ("custom", 700000))
        self.assertEqual(pv.parse_choice("CHOICE: custom=700k"), "custom")
        self.assertEqual(pv.parse_custom("**SCELTA:** mix = 1,2M"), ("mix", 1200000))
        self.assertIsNone(pv.parse_custom("CHOICE: good"))
        self.assertIsNone(pv.parse_custom("CHOICE: custom=0"))
        # only the CHOICE line parse_choice reads: an amount on a later line is not the choice's
        self.assertIsNone(pv.parse_custom("CHOICE: good\nCHOICE: custom=5k"))

    def test_the_number_of_levels_goes_with_the_size(self):
        cfg = pv.config()
        self.assertEqual([pv.level_count(cfg, n) for n in (200000, 300000, 800000, 3000000, 5000000, 8000000)],
                         [1, 1, 2, 3, 3, 4])
        pv.store(("levels", "two"), 2000000)
        self.assertEqual(pv.level_count(pv.config(), 1500000), 2)
        self.assertEqual(pv.level_label("good", "it"), "Buono")
        self.assertEqual(pv.level_label("deep", "it"), "Deep")


class TestQuoteTable(Known):
    def test_every_level_has_its_time_and_shares(self):
        self.known()
        text = pv.quote_table(pv.config(), {"good": 200000, "max": 400000}, context=100000, lang="en")
        self.assertIn("| Level | Work | Chat part | Total | Expected time | 5 hours | Week |", text)
        good = next(line for line in text.splitlines() if line.startswith("| Good |"))
        self.assertIn("about 2 min", good)           # 200k x 10 min per 1M
        self.assertRegex(good, r"~\d+(\.\d)?% \(\d+(\.\d)?% left\) \| ~\d+(\.\d)?% \(\d+(\.\d)?% left\) \|$")
        self.assertIn("about 4 min", next(line for line in text.splitlines() if line.startswith("| Max |")))
        self.assertNotIn("No number yet", text)
        self.assertIn("OTHER (the free field", text)
        self.assertIn("'5 days at 2:00'", text)
        self.assertIn("QUOTE: good=200000 max=400000", text)
        saved = pv.load_json(os.path.join(pv.home(), "quote-table.json"), {})
        self.assertEqual((saved["options"], saved["kind"]), ({"good": 200000, "max": 400000}, "chat"))
        # the table itself is a complete quote
        self.assertEqual(pv.quote_gaps(pv.config(), {"good": 200000, "max": 400000}, text), [])

    def test_italian(self):
        self.known()
        text = pv.quote_table(pv.config(), {"essential": 1000000, "good": 2000000, "max": 4000000}, lang="it")
        self.assertIn("| Livello | Lavoro | Parte della chat | Totale | Tempo previsto | 5 ore | Settimana |", text)
        for label in ("| Essenziale |", "| Buono |", "| Massimo |"):
            self.assertIn(label, text)
        self.assertIn("circa 10 min", text)
        self.assertIn("ALTRO (il campo libero", text)
        self.assertIn("«5 giorni alle 2:00»", text)
        self.assertIn("la parte della chat non è nota qui", text)

    def test_small_jobs_get_short_plans_and_big_jobs_longer_ones(self):
        self.known()
        cfg = pv.config()
        small = self.pace_lines(pv.quote_table(cfg, {"good": 200000, "max": 400000}, lang="en"))
        self.assertEqual([line.split(":")[0] for line in small],
                         ["1. All today", "2. Apart, now", "3. 2 days", "4. 3 days"])
        middle = self.pace_lines(pv.quote_table(cfg, {"essential": 500000, "good": 1000000, "max": 2000000}, lang="en"))
        self.assertEqual([line.split(":")[0] for line in middle],
                         ["1. All today", "2. Apart, now", "3. 3 days", "4. 5 days"])
        big = self.pace_lines(pv.quote_table(cfg, {"essential": 1000000, "good": 3000000, "full": 5000000,
                                                   "max": 8000000}, lang="en"))
        self.assertEqual([line.split(":")[0] for line in big], ["1. All today", "2. 3 days", "3. 5 days", "4. 7 days"])
        # each plan with the amount a day of each level and the time
        self.assertRegex(big[3], r"a day essential ~[\d,]+ · good ~[\d,]+ · full ~[\d,.]+( million)? · max ~[\d,.]+"
                                 r"( million)?; one installment a day at 03:00")
        self.assertIn("of the 5 hours", big[3])
        self.assertIn("of the week a day", big[3])
        # a long chat: 'in a new chat' among the four
        long_chat = self.pace_lines(pv.quote_table(cfg, {"good": 200000, "max": 400000}, new_chat=True, lang="en"))
        self.assertEqual([line.split(":")[0] for line in long_chat],
                         ["1. All today", "2. In a new chat", "3. Apart, now", "4. 2 days"])

    def test_the_time_of_the_plans_is_the_setting(self):
        self.known()
        pv.store(("rate", "time"), "02:00")
        text = pv.quote_table(pv.config(), {"good": 200000, "max": 400000}, lang="it")
        self.assertIn("una rata al giorno alle 02:00", text)

    def test_installments_have_no_share_of_the_5_hours_in_the_table(self):
        self.known()
        text = pv.quote_table(pv.config(), {"good": 200000, "max": 400000}, kind="rate", lang="en")
        self.assertIn("| Level | Work | Installments' re-reading | Total | Expected time | Week |", text)
        self.assertEqual(self.pace_lines(text)[0].split(":")[0], "1. Apart, now")
        self.assertEqual(pv.load_json(os.path.join(pv.home(), "quote-table.json"), {})["kind"], "rate")

    def test_the_agent_is_told_how_many_levels_and_in_what_order(self):
        self.known()
        cfg = pv.config()
        text = pv.quote_table(cfg, {"essential": 50000, "good": 200000, "max": 400000}, lang="en")
        self.assertIn("Quotient gives 2 levels (good, max); you gave 3", text)
        text = pv.quote_table(cfg, {"max": 400000, "good": 200000}, lang="en")
        self.assertIn("Write the levels from the smallest to the biggest.", text)
        text = pv.quote_table(cfg, {"good": 200000}, lang="en")
        self.assertIn("with one level, ask only the pace", text)
        self.assertNotIn("you gave", text)

    def test_what_is_not_known_yet_is_said(self):
        text = pv.quote_table(pv.config(), {"good": 200000, "max": 400000}, lang="en")
        self.assertIn("No number yet (?): the expected time comes after 3 jobs measured with their time", text)
        self.assertIn("the shares of the limits come after a few days of limit readings", text)
        # and with nothing to check, no quote is incomplete
        self.assertEqual(pv.quote_gaps(pv.config(), {"good": 200000}, "QUOTE: good=200000"), [])

    def test_the_command(self):
        self.known()
        said = self.run_hook(lambda: pv.main(["quote-table", "--raw", "good=200k", "max=400k", "--lang", "en"]), {})
        self.assertIn("QUOTE (unit: weighted tokens)", said)
        self.assertIn("QUOTE: good=200000 max=400000", said)
        with self.assertRaises(SystemExit):
            self.run_hook(lambda: pv.main(["quote-table", "--raw", "nothing"]), {})


class TestQuoteCheck(Known):
    """15/10/2026, the user: "non sei tu che devi ricordarti, deve essere Quotient"."""

    def test_what_a_quote_lacks(self):
        self.known()
        cfg, quote = pv.config(), {"good": 200000, "max": 400000}
        self.assertEqual(pv.quote_gaps(cfg, quote, "Good or max?\nQUOTE: good=200k max=400k"),
                         [["good", ["time", "shares"]], ["max", ["time", "shares"]]])
        self.assertEqual(pv.quote_gaps(cfg, quote, "- Buono: circa 2 min\n- Massimo: circa 4 min\nQUOTE: good=200k "
                                                   "max=400k"), [["good", ["shares"]], ["max", ["shares"]]])
        self.assertEqual(pv.quote_gaps(cfg, quote, "- Buono: circa 2 min, 4% delle 5 ore, 0,4% della settimana\n"
                                                   "- Massimo: 1 h 05 min\nQUOTE: good=200k max=400k"),
                         [["max", ["shares"]]])
        # what the window shows counts too
        self.assertEqual(pv.quote_gaps(cfg, quote, "QUOTE: good=200k max=400k",
                                       ["Buono (200k) circa 2 min · 4% delle 5 ore · 0,4% della settimana",
                                        "Massimo (400k) circa 4 min · 8% delle 5 ore · 0,8% della settimana"]), [])

    def quote_turn(self, texts, ask=None):
        self.t.user("do the whole thing")
        if ask:
            self.t._write({"type": "assistant", "requestId": "a", "message": {"id": "msg_a", "usage": usage(output=50),
                                                                             "content": [ask]}})
            self.t._write({"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "ask1", "content": "Buono"}]}})
        self.t.call("q", usage(read=10000, output=200), texts=texts)
        self.stop()

    def prompt(self):
        return self.run_hook(pv.hook_prompt, {"session_id": "s1", "transcript_path": self.t.path, "prompt": "ok"})

    def test_an_incomplete_quote_is_sent_back_at_the_next_message(self):
        self.known(["minutes_per_million"])          # only the time is known: only the time is checked
        self.quote_turn(["Good or max?\nQUOTE: good=200k max=400k"])
        self.assertEqual(pv.load_json(pv.session_path("s1"), {})["quote_incomplete"],
                         [["good", ["time"]], ["max", ["time"]]])
        lines = self.prompt().splitlines()
        self.assertTrue(lines[1].startswith("THE QUOTE BEFORE WAS INCOMPLETE ('good': its expected time; 'max': its "
                                            "expected time)"), lines[:2])
        self.assertIn("quote-table --raw", lines[1])
        self.assertNotIn("INCOMPLETE", self.prompt())   # said once

    def test_a_complete_quote_is_not_sent_back(self):
        self.known(["minutes_per_million"])
        self.quote_turn(["Good: about 2 min. Max: about 4 min.\nQUOTE: good=200k max=400k"])
        self.assertNotIn("quote_incomplete", pv.load_json(pv.session_path("s1"), {}))
        self.assertNotIn("INCOMPLETE", self.prompt())

    def test_the_times_in_the_window_count(self):
        self.known(["minutes_per_million"])
        ask = {"type": "tool_use", "id": "ask1", "name": "AskUserQuestion", "input": {"questions": [
            {"header": "Livello", "question": "Quale livello?", "options": [
                {"label": "Buono (200.000)", "description": "il lavoro di base; circa 2 min"},
                {"label": "Massimo (400.000)", "description": "tutto; circa 4 min"}]},
            {"header": "Ritmo", "question": "Quando?", "options": [{"label": "Tutto oggi", "description": "x"}]}]}}
        self.quote_turn(["QUOTE: good=200k max=400k\nCHOICE: good\nPACE: today\nJOB: CONTINUES"], ask=ask)
        self.assertNotIn("quote_incomplete", pv.load_json(pv.session_path("s1"), {}))

    def test_the_protocol_points_to_the_command(self):
        text = pv.protocol(pv.config(), 1.0)
        self.assertIn("quote-table --raw", text)
        self.assertIn("CHOICE: custom=<n>", text)
        self.assertIn("4 options at most", text)
        self.assertIn("AT WHAT TIME", text)
        self.assertIn("--pace", text)


class TestCustomChoice(Base):
    def test_a_choice_of_the_users_own_is_measured_against_its_estimate(self):
        self.t.user("do it")
        self.t.call("q", usage(read=10000, output=200), texts=["Three ways.\nQUOTE: good=200k max=400k"])
        self.stop()
        self.t.user("a mix: the good one plus the tests of the max")
        self.t.call("w1", usage(output=10000), texts=["CHOICE: custom=300k\nPACE: today"], tools=1)
        self.t.tool_result()
        self.t.call("w2", usage(output=4000), texts=["Done."])
        self.stop("Done.")
        job = pv.finished_jobs()[-1]
        self.assertEqual((job["choice"], job["raw_estimate"], job.get("custom")), ("custom", 300000, True))
        self.assertEqual(job["options"], {"good": 200000, "max": 400000})

    def test_in_the_same_reply_as_the_quote(self):
        self.t.user("do it")
        self.t.call("q", usage(output=2000), texts=["QUOTE: good=200k max=400k\nCHOICE: mix=250k\nPACE: today"])
        self.stop()
        job = pv.finished_jobs()[-1]
        self.assertEqual((job["choice"], job["raw_estimate"], job.get("custom")), ("mix", 250000, True))

    def test_the_waiting_quote_tells_how_to_write_it(self):
        self.t.user("do it")
        self.t.call("q", usage(output=200), texts=["QUOTE: good=200k max=400k"])
        self.stop()
        said = self.run_hook(pv.hook_prompt, {"session_id": "s1", "transcript_path": self.t.path, "prompt": "mix"})
        self.assertIn("CHOICE: custom=", said)


class TestPaceWithTime(InstallmentBase):
    def test_the_users_words_give_the_days_and_the_time(self):
        job = self.new_job(pace="5 giorni alle 2:00", quote=1000000, days=None, daily=None)
        self.assertEqual((job["days"], job["at"]), (5, "02:00"))
        self.assertEqual(job["daily_cap"], 200000)       # factor 1, nothing re-read in the tests
        job = self.new_job("small", pace="200k al giorno, alle 23:15", quote=1000000, days=None, daily=None)
        self.assertEqual((job["days"], job["daily_cap"], job["at"]), (5, 200000, "23:15"))

    def test_what_is_given_apart_counts_first(self):
        job = self.new_job(pace="5 giorni alle 2:00", at="04:30", quote=1000000, days=2, daily=None)
        self.assertEqual((job["days"], job["at"], job["daily_cap"]), (2, "04:30", 500000))

    def test_without_days_nor_amount_it_asks(self):
        with self.assertRaises(SystemExit):
            self.new_job(pace="alle 2:00", quote=1000000, days=None, daily=None)

    def args(self, name, time=None):
        args = mock.Mock(time=time, no_wake=True, force=False)
        args.name = name
        return args

    def test_once_and_every_day_use_the_jobs_time(self):
        self.new_job(pace="5 giorni alle 2:00", quote=1000000, days=None, daily=None)
        self.new_job("plain")
        with patch_q(pv, "schedule") as made:
            pv.rate_once(self.args("book"))
            pv.rate_schedule(self.args("book"))
            pv.rate_schedule(self.args("plain"))
            pv.rate_once(self.args("plain", "04:15"))
            with self.assertRaises(SystemExit):
                pv.rate_once(self.args("plain"))
        self.assertEqual([(c.args[1], c.kwargs["once"]) for c in made.call_args_list],
                         [("02:00", True), ("02:00", False), ("03:00", False), ("04:15", True)])

    def test_the_command_line(self):
        task = os.path.join(self.dir, "task.md")
        with open(task, "w", encoding="utf-8") as f:
            f.write("the job")
        said = self.run_hook(lambda: pv.main(["rate", "new", "cli", "--dir", self.dir, "--task-file", task, "--quote",
                                              "600000", "--pace", "3 giorni alle 1:30"]), {})
        self.assertIn("Once at 01:30", said)
        job = pv.load_json(os.path.join(pv.rate_dir("cli"), "job.json"), {})
        self.assertEqual((job["days"], job["at"]), (3, "01:30"))


class TestHermes(Known):
    """The same in Hermes: the clarify window, a choice of the user's own, and the check of the quote."""

    def setUp(self):
        super().setUp()
        self.q = os.path.join(self.dir, "home")
        self.h = fake_hermes([
            ("chat1", "cli", "claude-opus-5-5", 1000.0, 2000.0, None, "work", "anthropic", 10, 100, 10000, 1000)])

    def hook(self, event, response=None):
        import subprocess
        payload = {"hook_event_name": event, "session_id": "chat1", "extra": {"assistant_response": response or "",
                                                                               "model": "claude-opus-5-5"}}
        with mock.patch.dict(os.environ, {"QUOTIENT_HOME": self.q, "HERMES_HOME": self.h, "QUOTIENT_LIMITS_LIVE": "0",
                                          "QUOTIENT_SHARE": "0"}):
            r = subprocess.run([sys.executable, os.path.join(HERE, "..", "scripts", "quotient.py"), "hermes-hook"],
                               input=json.dumps(payload), capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout or "{}")

    def timed_jobs(self):
        """3 jobs measured with their time: from now on a quote must give the time of each level."""
        os.makedirs(self.q, exist_ok=True)
        for i in range(3):
            pv.append_jsonl(os.path.join(self.q, "jobs.jsonl"), {
                "started": "2026-10-1%dT10:00:00+02:00" % i, "session": "x%d" % i, "choice": "good",
                "raw_estimate": 1000000, "actual": 1000000, "work": 1000000, "seconds": 600})

    def test_the_protocol_tells_the_window_and_the_command(self):
        text = self.hook("pre_llm_call")["context"]
        self.assertIn("call the clarify tool", text)
        self.assertIn("--context <the tokens of the CHAT PART line>", text)
        self.assertIn("4 choices at most", text)

    def test_an_incomplete_quote_is_sent_back(self):
        self.timed_jobs()
        self.hook("pre_llm_call")
        self.hook("post_llm_call", "Good or max?\nQUOTE: good=2000 max=4000")
        context = self.hook("pre_llm_call")["context"]
        self.assertIn("THE QUOTE BEFORE WAS INCOMPLETE ('good': its expected time; 'max': its expected time)", context)
        self.assertNotIn("INCOMPLETE", self.hook("pre_llm_call")["context"])
        self.hook("post_llm_call", "Good: about 1 min. Max: about 2 min.\nQUOTE: good=2000 max=5000")
        self.assertNotIn("INCOMPLETE", self.hook("pre_llm_call")["context"])

    def test_a_choice_of_the_users_own(self):
        self.hook("pre_llm_call")
        self.hook("post_llm_call", "QUOTE: good=2000 max=4000")
        self.hook("post_llm_call", "CHOICE: custom=3000\nPACE: today")
        update_counters(self.h, output_tokens=700)
        self.hook("post_llm_call", "Fatto.\nJOB: CLOSE")
        job = pv.read_jsonl(os.path.join(self.q, "jobs.jsonl"))[-1]
        self.assertEqual((job["choice"], job["raw_estimate"], job.get("custom"), job["actual"]),
                         ("custom", 3000, True, 3000))


def update_counters(d, **counters):
    from test_hermes import update
    update(d, "chat1", **counters)
