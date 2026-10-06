"""0.9.5: the work apart from re-reading the chat, jobs that move between chats, Quotient's own weight,
the warnings, the installment cap with a reserve, the PROGRESS line, the page with charts and the templates.
Run: python -m unittest discover tests"""

import json
import os
import time
from unittest import mock

from test_quotient import Base, Transcript, usage, pv

A = "aaaa1111-0000-0000-0000-000000000001"
B = "bbbb2222-0000-0000-0000-000000000002"


def tool_call(transcript, request_id, u, name, given, texts=()):
    """One API call whose only tool is the given one."""
    blocks = [{"type": "text", "text": t} for t in texts] + [{"type": "tool_use", "id": "x", "name": name, "input": given}]
    for block in blocks:
        transcript._write({"type": "assistant", "requestId": request_id,
                           "message": {"id": "msg_" + request_id, "content": [block], "usage": u}})


class ChatBase(Base):
    def stop_in(self, sid, transcript, last=""):
        return self.run_hook(pv.hook_stop, {"session_id": sid, "transcript_path": transcript.path,
                                            "last_assistant_message": last})

    def chat(self, name):
        return Transcript(os.path.join(self.dir, name + ".jsonl"))

    def last_turn(self):
        return pv.read_jsonl(os.path.join(pv.home(), "turns.jsonl"))[-1]


class TestChatPart(ChatBase):
    def test_the_prompt_is_read_then_written_then_plain_input(self):
        u = usage(inp=10, write=50, read=100)
        self.assertAlmostEqual(pv.span_cost(u, 0, 160, self.w), 100 * 0.1 + 50 * 1.25 + 10)
        self.assertAlmostEqual(pv.span_cost(u, 120, 160, self.w), 30 * 1.25 + 10)
        self.assertEqual(pv.span_cost(u, 200, 300, self.w), 0)

    def test_a_job_in_a_new_chat_rereads_only_its_start(self):
        self.t.user("rewrite chapter 3")
        self.t.call("q", usage(write=20000, output=100), texts=["QUOTE: essential=100k good=200k max=400k"], tools=1)
        self.t.tool_result()
        self.t.call("w", usage(read=20000, write=5000, output=2000), texts=["CHOICE: good\nPACE: today", "done"])
        self.stop()
        job = pv.finished_jobs()[0]
        # every call re-reads the 20k the chat started with: written once (x1.25), then read (x0.1)
        self.assertEqual((job["actual"], job["chat"], job["older"]), (43750, 25000 + 2000, 0))
        self.assertEqual(job["work"], 43750 - 27000)
        self.assertEqual(job["calls"], 2)

    def test_a_job_in_a_long_chat_has_an_older_part(self):
        self.t.user("hello")
        self.t.call("a", usage(write=10000, output=10))
        self.stop()
        self.t.user("now the big job")
        self.t.call("q", usage(read=300000, output=100), texts=["QUOTE: essential=100k good=200k max=400k"], tools=1)
        self.t.tool_result()
        self.t.call("w", usage(read=300000, write=1000, output=100), texts=["CHOICE: max\nPACE: today"])
        self.stop()
        job = pv.finished_jobs()[0]
        self.assertEqual((job["fresh"], job["base"]), (10000, 300000))
        self.assertEqual(job["chat"], 30000 + 30000)
        self.assertEqual(job["older"], 29000 + 29000)  # the part a new chat would not have carried

    def test_after_a_compaction_the_older_chat_adds_nothing(self):
        self.t.user("big job")
        self.t.call("q", usage(read=200000, output=100), texts=["QUOTE: essential=100k good=200k max=400k"], tools=1)
        self.t.tool_result()
        self.t.call("w", usage(read=200000, output=100), texts=["CHOICE: max\nPACE: today", "JOB: CONTINUES"])
        self.stop()
        self.t.user("go on")
        self.t.call("c", usage(read=50000, output=100), texts=["finished"])  # the chat was compacted
        self.stop()
        job = pv.finished_jobs()[0]
        self.assertEqual(job["chat"], 20000 + 20000)
        self.assertEqual(job["turns"], 2)

    def test_the_line_at_each_message_gives_the_chat_part_and_offers_a_new_chat(self):
        self.t.user("hello")
        self.t.call("a", usage(write=10000, output=10))
        self.t.user("more")
        self.t.call("b", usage(read=300000, output=10))
        line = self.run_hook(pv.hook_prompt, {"session_id": "s1", "transcript_path": self.t.path})
        self.assertIn("CHAT PART", line)
        self.assertIn("+100%", line)            # 300k x 0.1 = 30k a call, on 30k of work a call
        self.assertIn("new chat", line)
        short = self.chat("short")
        short.user("hello")
        short.call("a", usage(write=20000, output=10))
        line = self.run_hook(pv.hook_prompt, {"session_id": "s2", "transcript_path": short.path})
        self.assertIn("CHAT PART", line)
        self.assertNotIn("new chat", line)

    def test_work_per_call_is_learned_from_jobs(self):
        for work in (20000, 40000, 60000):
            pv.append_jsonl(os.path.join(pv.home(), "jobs.jsonl"), {
                "raw_estimate": 100000, "actual": work * 10 + 5000, "chat": 5000, "work": work * 10, "calls": 10})
        self.assertEqual(pv.work_per_call(pv.config()), (40000, 3))

    def test_the_line_sent_to_the_shared_average_holds_the_work(self):
        row = pv.share_row({"raw_estimate": 200000, "actual": 300000, "chat": 100000, "family": "opus"})
        self.assertEqual((row["estimate"], row["actual"]), (200000, 200000))
        self.assertEqual(set(row), {"v", "q", "family", "estimate", "actual"})

    def test_protocol_asks_for_the_work_and_knows_the_new_chat(self):
        protocol = self.run_hook(pv.hook_session, {"session_id": "s1"})
        self.assertIn("Estimate the WORK", protocol)
        self.assertIn("PACE: new chat", protocol)
        self.assertIn("JOB: RESUME", protocol)

    def test_parsing(self):
        self.assertEqual(pv.parse_pace("PACE: new chat"), "new-chat")
        self.assertEqual(pv.parse_pace("**RITMO:** in una nuova chat"), "new-chat")
        self.assertEqual(pv.parse_move("done\nJOB: RESUME 474332df"), ("resume", "474332df"))
        self.assertEqual(pv.parse_move("**LAVORO:** chiudi AAAA1111"), ("close", "aaaa1111"))
        self.assertIsNone(pv.parse_move("JOB: CONTINUES"))


class TestMovingJobs(ChatBase):
    def open_job_in_a(self):
        a = self.chat("a")
        a.user("big job")
        a.call("q", usage(write=10000, output=100), texts=["QUOTE: essential=100k good=200k max=400k"], tools=1)
        a.tool_result()
        a.call("w", usage(read=10000, output=1000), texts=["CHOICE: max\nPACE: today", "JOB: CONTINUES"])
        self.stop_in(A, a)
        return a

    def test_a_job_chosen_for_a_new_chat_is_measured_there(self):
        a = self.chat("a")
        a.user("hello")
        a.call("a", usage(write=10000, output=10))
        self.stop_in(A, a)
        a.user("rewrite it all")
        a.call("q", usage(read=200000, output=100), texts=["QUOTE: essential=100k good=200k max=400k"], tools=1)
        a.tool_result()
        a.call("c", usage(read=200000, output=100), texts=["CHOICE: good\nPACE: new chat"])
        self.stop_in(A, a)
        self.assertEqual(pv.finished_jobs(), [])
        waiting = pv.chat_jobs()[A]["job"]
        self.assertTrue(waiting["waiting"])
        self.assertAlmostEqual(waiting["chat_avoided_percent"], 63.3, places=1)  # 190k older x0.1 on 30k a call
        told = self.run_hook(pv.hook_session, {"session_id": B})
        self.assertIn("A JOB WAITS TO BE DONE IN A NEW CHAT", told)
        self.assertIn("JOB: RESUME aaaa1111", told)
        b = self.chat("b")
        b.user("let's do the job")
        b.call("r", usage(write=30000, output=1000), texts=["JOB: RESUME aaaa1111", "done"])
        self.stop_in(B, b)
        job = pv.finished_jobs()[0]
        self.assertEqual((job["choice"], job["actual"], job["chat"], job["older"], job["chats"]),
                         ("good", 42500, 37500, 0, [B]))
        self.assertEqual(pv.chat_jobs(), {})
        saved = pv.savings(pv.finished_jobs())
        self.assertEqual(saved["moved"], 1)
        self.assertAlmostEqual(saved["moved_wt"], 5000 * 0.633, delta=1)

    def test_an_open_job_moves_to_another_chat(self):
        self.open_job_in_a()
        self.assertIn(A, pv.chat_jobs())
        told = self.run_hook(pv.hook_session, {"session_id": B})
        self.assertIn("AN OPEN JOB IN ANOTHER CHAT", told)
        b = self.chat("b")
        b.user("let's go on with the job")
        b.call("r", usage(write=20000, output=100), texts=["JOB: RESUME aaaa1111\nJOB: CONTINUES"])
        self.stop_in(B, b)
        self.assertIsNone(pv.load_json(pv.session_path(A), {}).get("job"))
        self.assertEqual(list(pv.chat_jobs()), [B])
        b.user("finish it")
        b.call("r2", usage(read=20000, output=100), texts=["finished"])
        self.stop_in(B, b)
        job = pv.finished_jobs()[0]
        self.assertEqual((job["actual"], job["chats"], job["turns"]), (19000 + 25500 + 2500, [A, B], 3))
        self.assertEqual(pv.chat_jobs(), {})

    def test_an_open_job_can_be_closed_or_dropped_from_another_chat(self):
        self.open_job_in_a()
        b = self.chat("b")
        b.user("that job is done")
        b.call("r", usage(output=10), texts=["ok\nJOB: CLOSE aaaa1111"])
        self.stop_in(B, b)
        self.assertEqual(pv.finished_jobs()[0]["actual"], 19000)
        self.assertIsNone(pv.load_json(pv.session_path(B), {}).get("job"))
        os.remove(os.path.join(pv.home(), "jobs.jsonl"))
        self.open_job_in_a()
        b.user("forget it")
        b.call("r2", usage(output=10), texts=["ok\nJOB: DROP aaaa1111"])
        self.stop_in(B, b)
        self.assertEqual((pv.finished_jobs(), pv.chat_jobs()), ([], {}))

    def test_an_old_open_job_is_forgotten(self):
        self.open_job_in_a()
        jobs = pv.chat_jobs()
        jobs[A]["epoch"] = time.time() - 8 * 86400
        pv.save_json(pv.chat_jobs_path(), jobs)
        told = self.run_hook(pv.hook_session, {"session_id": B})
        self.assertNotIn("OPEN JOB", told)
        self.assertEqual(pv.chat_jobs(), {})


class TestWeight(ChatBase):
    def test_texts_and_actions_of_quotient_are_counted(self):
        self.run_hook(pv.hook_prompt, {"session_id": "s1", "transcript_path": self.t.path})
        chars = pv.load_json(pv.session_path("s1"), {})["q_chars"]
        self.assertGreater(chars, 100)
        self.t.user("how are my limits?")
        tool_call(self.t, "a", usage(read=1000, output=10), "mcp__ccd_session_mgmt__get_usage", {})
        self.t.tool_result()
        self.t.call("b", usage(read=2000, output=100), texts=["LIMITS: five_hour=10 seven_day=5"])
        self.stop()
        row = self.last_turn()
        self.assertEqual((row["q_actions"], row["q_actions_wt"]), (1, 200 + 500))
        per = pv.config()["chars_per_token"]
        expected = chars / per * 0.1 * 2 + chars / per * (1.25 - 0.1)
        self.assertAlmostEqual(row["q_text"], expected, delta=1)
        s = pv.weight_summary()
        self.assertEqual(s["weight"], row["q_text"] + 700)

    def test_only_quotient_windows_and_commands_are_its_actions(self):
        mine = {"name": "AskUserQuestion", "input": {"questions": [{"header": "Livello"}, {"header": "Ritmo"}]}}
        other = {"name": "AskUserQuestion", "input": {"questions": [{"header": "Colore"}]}}
        cmd = {"name": "Bash", "input": {"command": '"py" "C:/Users/x/.claude/plugins/cache/quotient/quotient/0.9.5/scripts/quotient.py" rate week'}}
        launcher = {"name": "PowerShell", "input": {"command": "py C:/Users/x/.quotient/launcher.py rate run book"}}
        dev = {"name": "Bash", "input": {"command": "python -m unittest discover -s tests"}}
        usage_read = {"name": "mcp__ccd_session_mgmt__get_usage", "input": {}}
        self.assertTrue(pv.quotient_action(mine, ""))
        self.assertFalse(pv.quotient_action(other, ""))
        self.assertTrue(pv.quotient_action(cmd, ""))
        self.assertTrue(pv.quotient_action(launcher, ""))
        self.assertFalse(pv.quotient_action(dev, ""))
        self.assertTrue(pv.quotient_action(usage_read, "LIMITS: five_hour=3"))
        self.assertFalse(pv.quotient_action(usage_read, "no limits line: the user's own reading"))

    def test_a_big_reply_without_a_quote_is_said_once_and_counted(self):
        for i in range(2):
            self.t.user("do it all %d" % i)
            self.t.call("x%d" % i, usage(output=70000), texts=["done"])  # 350k wt, above 300k
            self.stop()
            said = self.run_hook(pv.hook_prompt, {"session_id": "s1", "transcript_path": self.t.path})
            if i == 0:
                self.assertIn("had no quote", said)
            else:
                self.assertNotIn("had no quote", said)
        self.assertEqual(pv.weight_summary()["unquoted"], 2)
        self.assertIn("without a quote: 2", self.run_hook(pv.report, {}))

    def test_a_scheduled_task_is_not_an_unquoted_reply(self):
        pv.store(("rate", "prompt_prefix"), "[AUTO]")
        self.t.user("[AUTO] the nightly copy")
        self.t.call("x", usage(output=70000), texts=["done"])
        self.stop()
        self.assertNotIn("unquoted", self.last_turn())


class TestWeekPace(ChatBase):
    def test_a_pace_that_runs_out_before_the_reset_is_said_once(self):
        now = time.time()
        pv.record_limits({"seven_day": 60, "seven_day_resets": round(now + 4 * 86400)}, "claude")
        alert = pv.pace_alert(pv.config())
        self.assertIn("WEEK PACE", alert)
        self.assertIn("~20% a day", alert)
        self.assertIn("about 10% a day", alert)
        self.assertIsNone(pv.pace_alert(pv.config()))

    def test_a_pace_that_lasts_says_nothing(self):
        pv.record_limits({"seven_day": 10, "seven_day_resets": round(time.time() + 4 * 86400)}, "claude")
        self.assertIsNone(pv.pace_alert(pv.config()))
        self.assertLess(pv.week_pace()["projected"], 100)


class TestInstallments010(ChatBase):
    def new_job(self, **kw):
        args = mock.Mock(dir=self.dir, task="write the book", task_file=None, days=None, daily=None, quote=None,
                         model=None, after="nothing", template=None)
        args.name = "book"
        for k, v in kw.items():
            setattr(args, k, v)
        self.run_hook(lambda: pv.rate_new(args), {})
        return pv.load_json(os.path.join(pv.rate_dir("book"), "job.json"), None)

    def test_the_cap_keeps_room_for_the_closing_steps(self):
        self.new_job(daily=100000, days=3)
        self.t.user("installment")
        for i in range(3):
            self.t.call("c%d" % i, usage(output=4000), tools=1)  # 20k wt each
            self.t.tool_result()
            with mock.patch.dict(os.environ, {"QUOTIENT_JOB": "book"}):
                said = self.run_hook(pv.hook_pretool, {"transcript_path": self.t.path, "tool_name": "Bash",
                                                       "tool_input": {"command": "ls"}})
            if i < 2:
                self.assertEqual(said, "", "after %d calls (%dk spent) there is still room" % (i + 1, 20 * (i + 1)))
            else:
                self.assertEqual(json.loads(said)["hookSpecificOutput"]["permissionDecision"], "deny")
                self.assertIn("PROGRESS", said)

    def test_the_progress_line_tells_what_remains(self):
        self.assertEqual(pv.parse_progress("# Handoff\nPROGRESS: 40%\nDone: ..."), 40)
        self.assertEqual(pv.parse_progress("**AVANZAMENTO:** ~55,5 %"), 55.5)
        self.assertIsNone(pv.parse_progress("no line"))
        self.assertIsNone(pv.parse_progress("PROGRESS: 140%"))
        self.assertIn("PROGRESS: <n>%", pv.RATE_PROMPT)
        job = self.new_job(daily=250000, days=2)
        runs = [{"started": "2026-10-06T03:00:00+02:00", "finished": "2026-10-06T03:10:00+02:00", "wt": 400000,
                 "cap": 250000, "progress": 40, "error": None, "done": False}]
        self.assertEqual(pv.remaining(job, runs), (40, 600000, 3))
        lines = "\n".join(pv.report_lines("book", job, runs, 0, pv.rate_dir("book")))
        self.assertIn("~40% of the whole job is done", lines)
        self.assertIn("~3 more installment(s)", lines)
        pv.store(("lang",), "it")
        title, body = pv.installment_toast("book", job, runs, pv.config())
        self.assertIn("fatto circa il 40%, ne mancano circa 3", body)

    def test_the_cap_pays_for_rereading_each_installments_start(self):
        pv.store(("chat", "installment_start"), 50000)
        job = self.new_job(quote=500000, days=2)
        # 50k re-read at each call (x0.1 = 5k) on 30k of work a call: +1/6
        self.assertEqual(job["daily_cap"], 291667)
        self.assertAlmostEqual(job["overhead_at_quote"], 0.167, places=3)
        folder = pv.rate_dir("other")
        os.makedirs(folder)
        for chat, wt in ((100000, 500000), (200000, 600000)):
            pv.append_jsonl(os.path.join(folder, "runs.jsonl"), {"started": "2026-10-06T03:00:00", "wt": wt, "chat": chat})
        self.assertAlmostEqual(pv.installment_overhead(pv.config()), (0.25 + 0.5) / 2)

    def test_a_template_gives_the_job_a_way_of_working(self):
        self.new_job(quote=500000, days=2, template="book")
        task = open(os.path.join(pv.rate_dir("book"), "TASK.md"), encoding="utf-8").read()
        self.assertTrue(task.startswith("# Template: book"))
        self.assertIn("PROGRESS", task)
        self.assertTrue(task.rstrip().endswith("# The job\n\nwrite the book"))
        self.assertEqual(set(pv.templates()), {"book", "research", "code-review"})
        with self.assertRaises(SystemExit):
            os.remove(os.path.join(pv.rate_dir("book"), "job.json"))
            self.new_job(quote=500000, days=2, template="nothing-like-this")


class TestBackfill(ChatBase):
    def test_old_jobs_get_their_chat_part_from_the_transcript(self):
        path = os.path.join(self.dir, "old.jsonl")
        rows = [
            {"type": "user", "timestamp": "2026-10-05T07:00:00Z", "message": {"role": "user", "content": "hi"}},
            {"type": "assistant", "timestamp": "2026-10-05T07:00:05Z", "requestId": "a",
             "message": {"id": "a", "content": [], "usage": usage(write=10000, output=10)}},
            {"type": "user", "timestamp": "2026-10-05T07:10:00Z", "message": {"role": "user", "content": "job"}},
            {"type": "assistant", "timestamp": "2026-10-05T07:10:05Z", "requestId": "b",
             "message": {"id": "b", "content": [], "usage": usage(read=50000, output=100)}},
            {"type": "assistant", "timestamp": "2026-10-05T07:11:00Z", "requestId": "c",
             "message": {"id": "c", "content": [], "usage": usage(read=50000, output=100)}},
        ]
        with open(path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        pv.append_jsonl(os.path.join(pv.home(), "jobs.jsonl"), {
            "started": "2026-10-05T09:11:00+02:00", "finished": "2026-10-05T09:11:30+02:00", "session": "cccc",
            "raw_estimate": 10000, "actual": 11000, "choice": "max"})
        pv.append_jsonl(os.path.join(pv.home(), "jobs.jsonl"), {
            "started": "x", "finished": "y", "session": "rate:book", "raw_estimate": 10000, "actual": 9000})
        with mock.patch.object(pv, "find_transcript", return_value=path):
            self.assertEqual(pv.backfill_chat(), 1)
            self.assertEqual(pv.backfill_chat(), 0)  # each job is looked at once
        jobs = pv.finished_jobs()
        self.assertEqual((jobs[0]["chat"], jobs[0]["older"], jobs[0]["work"]), (10000, 8000, 1000))
        self.assertTrue(jobs[1]["chat_checked"])
        self.assertIsNone(jobs[1].get("chat"))


class TestReportPage(ChatBase):
    def test_the_page_is_written_in_quotients_folder_with_charts_and_no_outside_links(self):
        self.t.user("rewrite chapter 3")
        self.t.call("q", usage(write=20000, output=100), texts=["QUOTE: essential=100k good=200k max=400k"], tools=1)
        self.t.tool_result()
        self.t.call("w", usage(read=20000, write=5000, output=2000), texts=["CHOICE: good\nPACE: today", "done"])
        self.stop()
        pv.record_limits({"seven_day": 30, "seven_day_resets": round(time.time() + 3 * 86400)}, "claude")
        pv.store(("lang",), "it")
        args = mock.Mock(html=True, no_open=True)
        with mock.patch.object(pv, "open_file") as opened:
            said = self.run_hook(lambda: pv.report(args), {})
        opened.assert_not_called()
        path = os.path.join(pv.home(), "report.html")
        self.assertIn(path, said)
        page = open(path, encoding="utf-8").read()
        self.assertIn("<svg", page)
        self.assertIn("<table", page)
        self.assertIn("resoconto", page)
        self.assertIn("prefers-color-scheme:dark", page)
        self.assertNotIn("http", page)  # nothing loaded from outside: the page works offline
        self.assertNotIn("src=", page)

    def test_savings_are_estimates_of_the_choices(self):
        saved = pv.savings([{"options": {"e": 100000, "g": 200000, "m": 400000}, "choice": "g",
                             "raw_estimate": 200000, "factor_used": 1.2, "actual": 1}])
        self.assertEqual(saved["below"], 1)
        self.assertAlmostEqual(saved["below_wt"], 240000)
