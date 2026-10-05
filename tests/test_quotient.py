"""Tests with fake transcripts. Run: python -m unittest discover tests"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)
import quotient as pv  # noqa: E402


def usage(inp=0, write=0, read=0, output=0, write_1h=None):
    u = {"input_tokens": inp, "cache_creation_input_tokens": write,
         "cache_read_input_tokens": read, "output_tokens": output}
    if write_1h is not None:
        u["cache_creation"] = {"ephemeral_1h_input_tokens": write_1h,
                               "ephemeral_5m_input_tokens": write - write_1h}
    return u


class Transcript:
    """Writes a transcript in Claude Code's format: one line per content block."""

    def __init__(self, path):
        self.path = path
        self.n = 0
        open(path, "w").close()

    def _write(self, row):
        self.n += 1
        row.setdefault("timestamp", "2026-10-05T10:%02d:%02d.000Z" % (self.n // 60, self.n % 60))
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    def user(self, text):
        self._write({"type": "user", "message": {"role": "user", "content": text}})

    def tool_result(self):
        self._write({"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t", "content": "ok"}]}})

    def call(self, request_id, u, texts=(), tools=0):
        """One API call, written as several lines that repeat the same usage."""
        blocks = [{"type": "thinking", "thinking": ""}] + \
                 [{"type": "text", "text": t} for t in texts] + \
                 [{"type": "tool_use", "id": "t", "name": "Read", "input": {}}] * tools
        for block in blocks:
            self._write({"type": "assistant", "requestId": request_id,
                         "message": {"id": "msg_" + request_id, "content": [block], "usage": u}})


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {"QUOTIENT_HOME": os.path.join(self.dir, "home")})
        self.env.start()
        self.t = Transcript(os.path.join(self.dir, "session.jsonl"))
        self.w = pv.config()["weights"]

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_hook(self, func, payload):
        stdin = io.TextIOWrapper(io.BytesIO(json.dumps(payload).encode("utf-8")), encoding="utf-8")
        stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        with mock.patch.object(sys, "stdin", stdin), mock.patch.object(sys, "stdout", stdout):
            func()
            stdout.flush()
            return stdout.buffer.getvalue().decode("utf-8")

    def stop(self, last=""):
        return self.run_hook(pv.hook_stop, {"session_id": "s1", "transcript_path": self.t.path,
                                            "last_assistant_message": last})


class TestCost(Base):
    def test_weights(self):
        self.assertEqual(pv.weigh(usage(inp=10, write=100, read=1000, output=20), self.w),
                         10 + 125 + 100 + 100)
        # a one-hour cache write costs 2x, a five-minute one 1.25x
        self.assertEqual(pv.weigh(usage(write=100, write_1h=60), self.w), 60 * 2 + 40 * 1.25)

    def test_each_call_counted_once(self):
        self.t.user("hello")
        self.t.call("r1", usage(read=1000, output=10), texts=["a"], tools=2)
        self.t.tool_result()
        self.t.call("r2", usage(read=2000, output=10), texts=["b"])
        turn, _, text = pv.turn_of(self.t.path)
        cost, calls = pv.cost_of(turn, self.w)
        self.assertEqual(calls, 2)
        self.assertEqual(cost, 100 + 50 + 200 + 50)
        self.assertEqual(text, "a\nb")

    def test_only_last_turn(self):
        self.t.user("first")
        self.t.call("r1", usage(read=999999))
        self.t.user("second")
        self.t.call("r2", usage(output=1))
        turn, _, _ = pv.turn_of(self.t.path)
        self.assertEqual(pv.cost_of(turn, self.w), (5, 1))


class TestParsing(Base):
    def test_quote_forms(self):
        self.assertEqual(pv.parse_quote("text\nPREVENTIVO: essenziale=120k buono=300k massimo=1.2M"),
                         {"essenziale": 120000, "buono": 300000, "massimo": 1200000})
        self.assertEqual(pv.parse_quote("**PREVENTIVO:** minimo=1.200.000 | rata3=400k"),
                         {"minimo": 1200000, "rata3": 400000})
        self.assertEqual(pv.parse_quote("ESTIMATE: basic=~50k, good=1,5M"),
                         {"basic": 50000, "good": 1500000})
        self.assertIsNone(pv.parse_quote("Il preventivo: niente"))
        self.assertEqual(pv.parse_quote("QUOTE: essential=80k good=250k max=2M split3=700k"),
                         {"essential": 80000, "good": 250000, "max": 2000000, "split3": 700000})

    def test_choice_and_continues(self):
        self.assertEqual(pv.parse_choice("SCELTA: buono\nok"), "buono")
        self.assertEqual(pv.parse_choice("**CHOICE:** `massimo`."), "massimo")
        self.assertTrue(pv.CONTINUES_RE.search("...\nLAVORO: CONTINUA"))
        self.assertFalse(pv.CONTINUES_RE.search("il lavoro continua domani"))
        self.assertEqual(pv.parse_choice("CHOICE: good"), "good")
        self.assertTrue(pv.CONTINUES_RE.search("JOB: CONTINUES"))
        self.assertTrue(pv.INSTALLMENT_RE.match("split7"))


class TestFlow(Base):
    def quote_turn(self):
        self.t.user("write the whole thing")
        self.t.call("q", usage(read=10000, output=200),
                    texts=["Three options.\nPREVENTIVO: essenziale=100k buono=200k massimo=400k"])
        self.stop()

    def test_quote_choice_job_and_learning(self):
        self.quote_turn()
        state = pv.load_json(pv.session_path("s1"), {})
        self.assertEqual(state["pending"]["options"]["buono"], 200000)
        context = self.run_hook(pv.hook_prompt, {"session_id": "s1", "transcript_path": self.t.path})
        self.assertIn("CHOICE", context)
        self.t.user("buono")
        self.t.call("w1", usage(write=100000, read=500000, output=10000), texts=["SCELTA: buono"], tools=1)
        self.t.tool_result()
        self.t.call("w2", usage(read=600000, output=4000), texts=["Done."])
        self.stop("Done.")
        jobs = pv.finished_jobs()
        self.assertEqual(len(jobs), 1)
        actual = 125000 + 50000 + 50000 + 60000 + 20000
        self.assertEqual(jobs[0]["actual"], actual)
        self.assertAlmostEqual(pv.learning(pv.config())["factor"], actual / 200000)
        self.assertIsNone(pv.load_json(pv.session_path("s1"), {})["pending"])

    def test_job_over_several_turns(self):
        self.quote_turn()
        self.t.user("massimo")
        self.t.call("w1", usage(output=1000), texts=["SCELTA: massimo", "part one\nLAVORO: CONTINUA"])
        self.stop()
        self.assertEqual(pv.finished_jobs(), [])
        self.t.user("go on")
        self.t.call("w2", usage(output=1000), texts=["finished"])
        self.stop()
        jobs = pv.finished_jobs()
        self.assertEqual((jobs[0]["actual"], jobs[0]["turns"]), (10000, 2))

    def test_stop_sent_back_counts_only_the_rest(self):
        self.quote_turn()
        self.t.user("buono")
        self.t.call("w1", usage(output=1000), texts=["SCELTA: buono", "first answer\nLAVORO: CONTINUA"])
        self.stop()
        # another hook sends Claude back: same turn, one more call
        self.t.call("w2", usage(output=400), texts=["added line"])
        self.stop()
        job = pv.load_json(pv.session_path("s1"), {})["job"]
        self.assertEqual((job["actual"], job["turns"]), (7000, 1))

    def test_declined_and_expired(self):
        self.quote_turn()
        self.t.user("no thanks")
        self.t.call("d", usage(output=10), texts=["SCELTA: nessuna"])
        self.stop()
        self.assertIsNone(pv.load_json(pv.session_path("s1"), {})["pending"])
        self.assertEqual(pv.finished_jobs(), [])
        self.quote_turn()
        for i in range(4):
            self.t.user("something else %d" % i)
            self.t.call("x%d" % i, usage(output=10), texts=["ok"])
            self.stop()
        self.assertIsNone(pv.load_json(pv.session_path("s1"), {})["pending"])

    def test_report_and_export(self):
        self.test_quote_choice_job_and_learning()
        report = self.run_hook(pv.report, {})
        self.assertIn("x1.5", report)
        exported = json.loads(self.run_hook(pv.export, {}))
        self.assertEqual(set(exported), {"date", "options", "level", "raw_estimate", "actual", "turns", "version"})


class TestWindow(Base):
    """0.3: the quote and the choice arrive in the same turn, through the choice window."""

    def test_same_turn_choice_today_is_measured(self):
        self.t.user("rewrite chapter 3, it's a big job")
        self.t.call("q", usage(output=100), texts=["QUOTE: essential=100k good=250k max=500k"], tools=1)
        self.t.tool_result()  # the user's answer in the window
        self.t.call("w", usage(output=2000), texts=["CHOICE: good\nPACE: today", "done"])
        self.stop()
        jobs = pv.finished_jobs()
        self.assertEqual((jobs[0]["choice"], jobs[0]["raw_estimate"], jobs[0]["actual"]), ("good", 250000, 10500))
        self.assertIsNone(pv.load_json(pv.session_path("s1"), {}).get("pending"))

    def test_installments_are_not_a_session_job(self):
        self.t.user("big job")
        self.t.call("q", usage(output=100), texts=["QUOTE: essential=100k good=250k max=500k"])
        self.t.call("w", usage(output=100), texts=["CHOICE: max\nPACE: daily=100k"])
        self.stop()
        self.assertEqual(pv.finished_jobs(), [])
        self.assertIsNone(pv.load_json(pv.session_path("s1"), {}).get("pending"))

    def test_pace(self):
        self.assertEqual(pv.parse_pace("PACE: today"), "today")
        self.assertEqual(pv.parse_pace("**RITMO:** tutto oggi"), "today")
        self.assertEqual(pv.parse_pace("PACE: days=5"), "days=5")
        self.assertIsNone(pv.parse_pace("no pace here"))

    def test_session_protocol_and_short_prompt(self):
        protocol = self.run_hook(pv.hook_session, {})
        self.assertIn("AskUserQuestion", protocol)
        self.assertIn("free field", protocol)
        self.assertIn("ONE DAY of work", protocol)
        self.assertIn("never bare numbers in parentheses", protocol)
        line = self.run_hook(pv.hook_prompt, {"session_id": "s1", "transcript_path": self.t.path})
        self.assertLess(len(line), 600)
        with mock.patch.dict(os.environ, {"QUOTIENT_JOB": "book"}):
            self.assertIn("installment run", self.run_hook(pv.hook_prompt, {}))
            self.assertEqual(self.run_hook(pv.hook_session, {}), "")


class TestLimits(Base):
    """0.4: the plan limits, from the status line or from Claude, and the size of 1%."""

    def test_statusline_records_and_shows(self):
        future = int(pv.time.time()) + 3600
        shown = self.run_hook(pv.statusline, {"rate_limits": {
            "five_hour": {"used_percentage": 23.5, "resets_at": future},
            "seven_day": {"used_percentage": 41.2, "resets_at": future + 86400}}})
        self.assertIn("24% used, 76% left", shown)
        self.assertIn("41% used, 59% left", shown)
        # the same reading within 5 minutes is not written twice
        self.run_hook(pv.statusline, {"rate_limits": {"five_hour": {"used_percentage": 23.5, "resets_at": future},
                                                      "seven_day": {"used_percentage": 41.2, "resets_at": future + 86400}}})
        self.assertEqual(len(pv.read_jsonl(pv.limits_path())), 1)

    def test_limits_line_from_claude(self):
        snap = pv.parse_limits("text\nLIMITS: five_hour=31 seven_day=6% five_hour_resets=2099-10-05T19:30:00.262Z seven_day_resets=2099-10-12T05:00:00Z")
        self.assertEqual((snap["five_hour"], snap["seven_day"]), (31.0, 6.0))
        self.assertEqual(snap["five_hour_resets"], pv.to_epoch("2099-10-05T19:30:00+00:00"))
        self.t.user("hi")
        self.t.call("a", usage(output=10), texts=["LIMITS: five_hour=31 seven_day=6 seven_day_resets=2099-10-12T05:00:00Z"])
        self.stop()
        self.assertEqual(pv.latest_limits()["seven_day"]["used"], 6.0)

    def test_capacity_and_weeks(self):
        now = int(pv.time.time())
        resets = now + 86400
        pv.append_jsonl(pv.limits_path(), {"ts": "x", "epoch": now - 3000, "seven_day": 10, "seven_day_resets": resets})
        pv.append_jsonl(pv.limits_path(), {"ts": "x", "epoch": now - 10, "seven_day": 15, "seven_day_resets": resets})
        moment = pv.datetime.fromtimestamp(now - 1000).astimezone().isoformat()
        pv.append_jsonl(os.path.join(pv.home(), "turns.jsonl"), {"ts": moment, "wt": 500000})
        c = pv.capacity("seven_day")
        self.assertEqual((c["per_point"], c["points"]), (100000, 5))
        self.assertEqual((round(c["low"]), round(c["high"])), (round(50000000 / 6 * 100 / 100), 12500000))
        rows = pv.weeks()
        self.assertEqual((rows[0]["used"], rows[0]["wt"], rows[0]["complete"]), (15, 500000, False))
        report = self.run_hook(pv.report, {})
        self.assertIn("10.00M", report)
        self.assertIn("Too early", report)


class TestSetup(Base):
    """0.7: the first use asks for the settings; Claude Code's plugin dialog and /quotient:setup change them."""

    def test_first_use_opens_the_setup_window(self):
        text = self.run_hook(pv.hook_session, {})
        self.assertIn("FIRST USE", text)
        self.run_hook(lambda: pv.cmd_setup(mock.Mock(threshold=150000, reserve=30, lang="it", after="sleep")), {})
        cfg = pv.config()
        self.assertEqual((cfg["threshold"], cfg["week"]["reserve_percent"], cfg["lang"], cfg["rate"]["after"], cfg["configured"]),
                         (150000, 30, "it", "sleep", True))
        self.assertNotIn("FIRST USE", self.run_hook(pv.hook_session, {}))

    def test_plugin_dialog_settings_reach_scheduled_runs(self):
        with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_OPTION_THRESHOLD": "500000",
                                          "CLAUDE_PLUGIN_OPTION_RESERVE_PERCENT": "25",
                                          "CLAUDE_PLUGIN_OPTION_AFTER": "hibernate"}):
            self.run_hook(pv.hook_session, {})
        # a scheduled run has no plugin variables: it reads config.json
        cfg = pv.config()
        self.assertEqual((cfg["threshold"], cfg["week"]["reserve_percent"], cfg["rate"]["after"], cfg["configured"]),
                         (500000, 25, "hibernate", True))


class TestWakeChoice(Base):
    """0.7.5: the user decides whether Quotient may wake the PC."""

    def test_never_touch_the_pc(self):
        self.run_hook(lambda: pv.cmd_setup(mock.Mock(threshold=None, reserve=None, lang=None, after="sleep", wake="no")), {})
        cfg = pv.config()
        self.assertEqual((cfg["rate"]["wake"], cfg["rate"]["after"]), (False, "nothing"))
        self.assertFalse(pv.wake_allowed(mock.Mock(no_wake=False)))

    def test_plugin_dialog_switch(self):
        with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_OPTION_WAKE": "false"}):
            self.run_hook(pv.hook_session, {})
        self.assertFalse(pv.config()["rate"]["wake"])
        self.assertIn("never touch the PC", pv.setup_instructions(pv.config()))


class TestWeek(Base):
    """0.6: all installment jobs together against what is left of the week."""

    def setUp(self):
        super().setUp()
        now = int(pv.time.time())
        resets = now + 3 * 86400 - 60  # 3 days left
        # 1% of the week = 100k wt, and 40% of the week is used
        pv.append_jsonl(pv.limits_path(), {"ts": "x", "epoch": now - 3000, "seven_day": 30, "seven_day_resets": resets})
        pv.append_jsonl(pv.limits_path(), {"ts": "x", "epoch": now - 10, "seven_day": 40, "seven_day_resets": resets})
        moment = pv.datetime.fromtimestamp(now - 1000).astimezone().isoformat()
        pv.append_jsonl(os.path.join(pv.home(), "turns.jsonl"), {"ts": moment, "wt": 1000000})

    def job(self, name, daily, days, quote=None):
        args = mock.Mock(dir=self.dir, task="job", task_file=None, days=days, daily=daily, quote=quote, model=None,
                         after="nothing")
        args.name = name
        self.run_hook(lambda: pv.rate_new(args), {})

    def test_jobs_that_fit_alone_but_not_together(self):
        self.job("one", 1000000, 5)   # 3 days left: 3M wt = 30%
        plan = pv.week_plan(pv.config())
        self.assertEqual((round(plan["need"]), plan["fits"]), (30, True))   # 60% left - 20% reserve = 40%
        self.job("two", 1000000, 5)
        plan = pv.week_plan(pv.config())
        self.assertEqual((round(plan["need"]), round(plan["for_jobs"]), plan["fits"]), (60, 40, False))
        first = pv.week_alert(pv.config())
        self.assertIn("choice window", first)
        self.assertIsNone(pv.week_alert(pv.config()))  # told once
        self.assertIn("NOT fit", pv.week_text(plan, "en"))

    def test_pause_takes_a_job_out_of_the_week(self):
        self.job("one", 1000000, 5)
        self.job("two", 1000000, 5)
        pause = mock.Mock()
        pause.name = "two"
        self.run_hook(lambda: pv.rate_pause(pause), {})
        self.assertTrue(pv.week_plan(pv.config())["fits"])
        args = mock.Mock(force=True)
        args.name = "two"
        with mock.patch.object(pv, "find_claude") as find:
            said = self.run_hook(lambda: pv.run_installment(args), {})
        find.assert_not_called()
        self.assertIn("paused", said)

    def test_an_installment_shrinks_to_stay_out_of_the_reserve(self):
        self.job("big", 5000000, 5)   # more than the 40% (4M wt) there is
        args = mock.Mock(force=True)
        args.name = "big"
        with mock.patch.object(pv, "find_claude", return_value="claude"), \
                mock.patch.object(pv.subprocess, "run", side_effect=pv.subprocess.TimeoutExpired("c", 1)) as run:
            said = self.run_hook(lambda: pv.run_installment(args), {})
        self.assertIn("shortened to 4.00M", said)
        self.assertEqual(run.call_args.kwargs["env"]["QUOTIENT_CAP"], "4000000")


class TestInstallments(Base):
    def new_job(self, **kw):
        args = mock.Mock(dir=self.dir, task="job", task_file=None, days=None, daily=None, quote=None, model=None,
                         after="nothing")
        args.name = "book"
        for k, v in kw.items():
            setattr(args, k, v)
        self.run_hook(lambda: pv.rate_new(args), {})
        return pv.load_json(os.path.join(pv.rate_dir("book"), "job.json"), None)

    def test_custom_daily_gives_the_days(self):
        job = self.new_job(quote=500000, daily=100000)
        self.assertEqual((job["daily_cap"], job["days"]), (100000, 5))

    def test_days_give_the_daily_cap(self):
        job = self.new_job(quote=500000, days=2)
        self.assertEqual((job["daily_cap"], job["days"]), (250000, 2))

    def test_finished_installment_is_told_once(self):
        self.new_job(quote=500000, days=2)
        pv.append_jsonl(os.path.join(pv.rate_dir("book"), "runs.jsonl"),
                        {"started": "2026-10-05T14:00:00+02:00", "finished": "2026-10-05T14:40:00+02:00",
                         "wt": 240000, "error": None, "done": False})
        payload = {"session_id": "s1", "transcript_path": self.t.path}
        first = self.run_hook(pv.hook_prompt, payload)
        second = self.run_hook(pv.hook_prompt, payload)
        self.assertIn("choice window", first)
        self.assertIn("own risk", first)
        self.assertNotIn("Installment 1", second)


    def test_cap_allows_only_the_handoff(self):
        args = mock.Mock(name="x", dir=self.dir, task="job", task_file=None, days=3, daily=1000,
                         quote=None, model=None, after="nothing")
        args.name = "book"
        self.run_hook(lambda: pv.rate_new(args), {})
        handoff = os.path.join(pv.rate_dir("book"), "HANDOFF.md")
        self.t.user("installment")
        self.t.call("r", usage(output=300))  # 1500 wt, over the cap
        with mock.patch.dict(os.environ, {"QUOTIENT_JOB": "book"}):
            denied = self.run_hook(pv.hook_pretool, {"transcript_path": self.t.path, "tool_name": "Bash",
                                                     "tool_input": {"command": "ls"}})
            allowed = self.run_hook(pv.hook_pretool, {"transcript_path": self.t.path, "tool_name": "Edit",
                                                      "tool_input": {"file_path": handoff}})
        self.assertEqual(json.loads(denied)["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(allowed, "")

    def test_task_wakes_the_pc_and_runs_late(self):
        start = pv.datetime(2026, 10, 6, 3, 0)
        xml = pv.task_xml("book", start, True, '"C:/x y/launcher.py" rate run book --force')
        self.assertIn("<WakeToRun>true</WakeToRun>", xml)
        self.assertIn("<StartWhenAvailable>true</StartWhenAvailable>", xml)
        self.assertIn("<TimeTrigger><StartBoundary>2026-10-06T03:00:00</StartBoundary>", xml)
        self.assertIn("&quot;C:/x y/launcher.py&quot; rate run book --force", xml)
        daily = pv.task_xml("book", start, False, "a", wake=False)
        self.assertIn("<DaysInterval>1</DaysInterval>", daily)
        self.assertIn("<WakeToRun>false</WakeToRun>", daily)

    def test_each_once_time_is_its_own_task(self):
        # 05/10/2026: three `rate once` at 19:00, 19:30, 20:00 left only the 20:00 one
        times = [pv.datetime(2026, 10, 5, 19, 0), pv.datetime(2026, 10, 5, 19, 30), pv.datetime(2026, 10, 5, 20, 0)]
        names = [pv.task_name("prova", True, t) for t in times]
        self.assertEqual(len(set(names)), 3)
        self.assertEqual(names[1], "quotient-prova-once-20261005-1930")
        self.assertEqual(pv.task_name("prova"), "quotient-prova")
        self.assertTrue(all(pv.once_task("prova", n) for n in names))
        self.assertTrue(pv.once_task("prova", "quotient-prova-once"))       # the old name is still removed
        self.assertFalse(pv.once_task("prova", "quotient-prova"))           # the daily task is not a once task
        self.assertFalse(pv.once_task("prova", "quotient-prova-notte-once-20261005-1900"))  # another job
        xml = pv.task_xml("prova", times[0], True, "a")
        self.assertIn("<EndBoundary>2026-10-12T19:00:00</EndBoundary>", xml)
        self.assertIn("<DeleteExpiredTaskAfter>PT1H</DeleteExpiredTaskAfter>", xml)
        self.assertNotIn("DeleteExpiredTaskAfter", pv.task_xml("prova", times[0], False, "a"))

    def test_only_a_first_line_job_done_ends_the_job(self):
        # 05/10/2026: "After line 3: write JOB DONE at the top" closed a job with 1 line of 3
        notes = "Installment 4: done. Wrote line 1.\nRemains: lines 2 and 3.\nAfter line 3: write JOB DONE at the top of this file.\n"
        self.assertIsNone(pv.DONE_RE.search(notes))
        for done in ("JOB DONE\n" + notes, "# JOB DONE\n", "**LAVORO FINITO**\n", "﻿\n  JOB DONE: all 3 lines\n"):
            self.assertIsNotNone(pv.DONE_RE.search(done), done)

    def test_a_past_time_means_tomorrow(self):
        past = pv.datetime.now().replace(second=0, microsecond=0)
        moment = pv.next_time(past.strftime("%H:%M"))
        self.assertGreater(moment, pv.datetime.now())
        self.assertLess((moment - pv.datetime.now()).total_seconds(), 86400 + 60)

    def test_launcher_finds_the_newest_version(self):
        text = open(pv.launcher(), encoding="utf-8").read()
        self.assertIn("runpy.run_path", text)
        self.assertIn("quotient.py", text)

    def test_after_the_installment_the_pc_sleeps_only_if_idle(self):
        self.new_job(quote=500000, days=2, after="sleep")
        with mock.patch.object(pv, "run_installment"), mock.patch.object(pv, "keep_awake"),                 mock.patch.object(pv, "go_to_sleep") as sleep,                 mock.patch.object(pv, "idle_seconds", return_value=60):
            args = mock.Mock(force=False)
            args.name = "book"
            self.run_hook(lambda: pv.rate_run(args), {})
            sleep.assert_not_called()
        with mock.patch.object(pv, "run_installment"), mock.patch.object(pv, "keep_awake"),                 mock.patch.object(pv, "go_to_sleep") as sleep,                 mock.patch.object(pv, "idle_seconds", return_value=3600):
            args = mock.Mock(force=False)
            args.name = "book"
            self.run_hook(lambda: pv.rate_run(args), {})
            sleep.assert_called_once_with("sleep")

    def test_two_installments_never_run_together(self):
        self.new_job(quote=500000, days=2)
        open(os.path.join(pv.rate_dir("book"), "run.lock"), "w").close()
        args = mock.Mock(force=True)
        args.name = "book"
        with mock.patch.object(pv, "run_installment") as run:
            said = self.run_hook(lambda: pv.rate_run(args), {})
        run.assert_not_called()
        self.assertIn("already running", said)

    def test_outside_installments_nothing_happens(self):
        os.environ.pop("QUOTIENT_JOB", None)
        self.assertEqual(self.run_hook(pv.hook_pretool, {"tool_name": "Bash"}), "")


class TestLauncher(unittest.TestCase):
    @unittest.skipUnless(shutil.which("sh"), "needs sh")
    def test_run_sh_passes_stdin(self):
        with tempfile.TemporaryDirectory() as home:
            proc = subprocess.run(["sh", os.path.join(SCRIPTS, "run.sh"), "hook-prompt"],
                                  input=json.dumps({"session_id": "z"}).encode("utf-8"),
                                  capture_output=True, env=dict(os.environ, QUOTIENT_HOME=home))
        self.assertIn("[Quotient", proc.stdout.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
