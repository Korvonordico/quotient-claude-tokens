"""1.1.0: the time of a job. How long work takes is learned from the finished jobs; a quote can say how long each
level takes; the stopwatch runs while the agent works and stops on the user's turn; the choice window's wait does
not count; old jobs get their time from the logs. Run: python -m unittest discover tests"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

os.environ["QUOTIENT_TIMER_WINDOW"] = "0"   # the tests never open the stopwatch window
from test_quotient import Base, HERE, pv  # noqa: E402
import hermes_source as hs  # noqa: E402


def write_jobs(rows):
    os.makedirs(pv.home(), exist_ok=True)
    with open(os.path.join(pv.home(), "jobs.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def timed_job(seconds, work=1000000, session="s0", raw=None):
    return {"session": session, "raw_estimate": raw or work, "actual": work, "chat": 0, "work": work,
            "seconds": seconds, "started": "2026-10-01T10:00:00+02:00", "finished": "2026-10-01T11:00:00+02:00"}


def iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(epoch)) + ".000Z"


def fake_hermes_db(messages=()):
    d = tempfile.mkdtemp()
    con = sqlite3.connect(os.path.join(d, "state.db"))
    con.execute("create table sessions (id text, source text, model text, started_at real, ended_at real, "
                "parent_session_id text, title text, last_activity_at real, estimated_cost_usd real, "
                "billing_provider text, api_call_count int, input_tokens int, output_tokens int, "
                "cache_read_tokens int, cache_write_tokens int)")
    con.execute("insert into sessions (id, source, model, billing_provider, input_tokens, output_tokens, "
                "cache_read_tokens, cache_write_tokens, api_call_count) values "
                "('chat1', 'cli', 'claude-opus-5-5', 'anthropic', 10, 100, 10000, 1000, 1)")
    con.execute("create table messages (id integer primary key, session_id text, role text, content text, "
                "tool_name text, timestamp real)")
    con.commit()
    con.close()
    add_messages(d, messages)
    return d


def add_messages(d, messages):
    con = sqlite3.connect(os.path.join(d, "state.db"))
    for ts, role, tool in messages:
        con.execute("insert into messages (session_id, role, content, tool_name, timestamp) values "
                    "('chat1', ?, 'not read', ?, ?)", (role, tool, ts))
    con.commit()
    con.close()


class TestLearnedTime(Base):
    def test_durations_for_people(self):
        self.assertEqual([pv.fmt_duration(s) for s in (None, 40, 61, 1500, 3700, 7260)],
                         ["?", "40 s", "1 min", "25 min", "1 h 02 min", "2 h 01 min"])

    def test_minutes_per_million_need_three_timed_jobs_of_the_kind(self):
        cfg = pv.config()
        write_jobs([timed_job(600), timed_job(1200), {"session": "s", "raw_estimate": 1, "actual": 5, "chat": 0}])
        self.assertIsNone(pv.minutes_per_million(cfg))
        self.assertIsNone(pv.expected_seconds(cfg, 1000000))
        write_jobs([timed_job(600), timed_job(1200), timed_job(900, work=500000),
                    timed_job(60, session="rate:x"), timed_job(60, session="rate:y")])
        self.assertEqual(pv.minutes_per_million(cfg), (20.0, 3))      # 10, 20 and 30 min per 1M wt
        self.assertIsNone(pv.minutes_per_million(cfg, "rate"))        # installments are learned apart
        # 2M raw x the factor (raw = real here, x1) x 20 min per 1M = 40 min
        self.assertAlmostEqual(pv.expected_seconds(cfg, 2000000, factor=1.0), 2400.0)
        self.assertEqual(pv.time_text(cfg), "about 20 min per 1M wt of work")
        # 1.1.7: no longer in the line at each message: quote-table gives each level its expected time
        self.assertNotIn("Working time", pv.calibration(cfg, pv.learning(cfg)))

    def test_the_time_misses(self):
        rows = [dict(timed_job(1200), predicted_seconds=600), dict(timed_job(300), predicted_seconds=600)]
        write_jobs(rows + [timed_job(100)])
        self.assertEqual(sorted(pv.time_misses()), [2.0, 2.0])


class TestPace(Base):
    def test_after_the_first_million_the_jobs_own_pace_speaks(self):
        self.assertEqual(pv.pace_note(2000000, 1.0, 900000, 600), "")
        self.assertIn("about 20 min more", pv.pace_note(3000000, 1.0, 1000000, 600))
        self.assertIn("Already x2.0 the corrected estimate", pv.pace_note(1000000, 1.0, 2000000, 1200))


class TestClaudeCodeTime(Base):
    T0 = 1791000000.0   # a fixed moment: the transcript's times, not the clock, give the time

    def entry(self, offset, row):
        row["timestamp"] = iso(self.T0 + offset)
        self.t._write(row)

    def prompt(self, offset, text):
        self.entry(offset, {"type": "user", "message": {"role": "user", "content": text}})

    def say(self, offset, rid, text, u=None, ask=None):
        blocks = [{"type": "text", "text": text}]
        if ask:
            blocks.append({"type": "tool_use", "id": ask, "name": "AskUserQuestion", "input": {}})
        for b in blocks:
            self.entry(offset, {"type": "assistant", "requestId": rid, "message": {
                "id": "m" + rid, "content": [b], "usage": u or {"input_tokens": 0, "output_tokens": 100,
                                                                 "cache_read_input_tokens": 1000}}})

    def answer(self, offset, ask):
        self.entry(offset, {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": ask, "content": "Level: good"}]}})

    def test_active_seconds_leave_out_the_users_turns_and_the_choice_window(self):
        self.prompt(0, "do it")
        self.say(20, "a", "QUOTE: essential=1k good=2k max=4k", ask="q1")
        self.answer(200, "q1")                 # 180 s of the user choosing: not work
        self.say(230, "b", "working")
        self.prompt(500, "next")               # 270 s of the user's turn: not work
        self.say(540, "c", "done")
        entries = pv.read_jsonl(self.t.path)
        self.assertAlmostEqual(pv.claude_active_seconds(entries, self.T0, self.T0 + 540), 20 + 30 + 40)

    def test_a_job_counts_its_working_time_and_the_stopwatch_follows_it(self):
        self.prompt(0, "big job")
        self.say(20, "a", "Tre livelli.\nQUOTE: essential=100000 good=200000 max=400000", ask="q1")
        self.answer(200, "q1")
        self.say(250, "b", "CHOICE: good\nPACE: today\nFirst part done.\nJOB: CONTINUES")
        self.stop()
        state = pv.load_json(pv.session_path("s1"), {})
        self.assertEqual(state["job"]["seconds"], 20 + 50)
        self.assertEqual(pv.timer_state()["state"], "pause")
        out = self.run_hook(pv.hook_prompt, {"session_id": "s1", "transcript_path": self.t.path, "prompt": "go on"})
        self.assertIn("working time so far 1 min", out)
        self.assertEqual(pv.timer_state()["state"], "run")
        self.prompt(400, "go on")
        self.say(460, "c", "All done.")
        self.stop()
        job = pv.read_jsonl(os.path.join(pv.home(), "jobs.jsonl"))[-1]
        self.assertEqual(job["seconds"], 70 + 60)
        self.assertEqual(pv.timer_state()["state"], "end")
        out = self.run_hook(pv.hook_prompt, {"session_id": "s1", "transcript_path": self.t.path, "prompt": "thanks"})
        self.assertIn("working time 2 min", out)
        out = self.run_hook(pv.hook_prompt, {"session_id": "s1", "transcript_path": self.t.path, "prompt": "ok"})
        self.assertNotIn("is closed", out)    # said once

    def test_the_stopwatch_started_by_the_agent_marks_the_start_of_the_work(self):
        write_jobs([timed_job(600) for _ in range(5)])        # 10 min per 1M wt, factor x1
        self.prompt(0, "big job")
        self.say(20, "a", "QUOTE: essential=100000 good=200000 max=400000", ask="q1")
        self.answer(200, "q1")
        with mock.patch.object(pv.time, "time", return_value=self.T0 + 210):
            self.run_hook(lambda: pv.cmd_timer(mock.Mock(what="start", raw=400000, level="max", kind="chat")), {})
        self.assertEqual(pv.timer_state()["predicted"], 240)  # 400k x1 x 10 min per 1M = 4 min
        self.say(250, "b", "CHOICE: max\nPACE: today\nJOB: CONTINUES")
        self.stop()
        job = pv.load_json(pv.session_path("s1"), {})["job"]
        self.assertEqual((job["seconds"], job["predicted_seconds"]), (40, 240))


class TestHermesTime(unittest.TestCase):
    """The Hermes hooks end to end, with a fake session store that has the messages' times."""

    def setUp(self):
        self.q = tempfile.mkdtemp()
        self.h = fake_hermes_db()

    def hook(self, event, response=""):
        payload = {"hook_event_name": event, "session_id": "chat1",
                   "extra": {"assistant_response": response, "model": "claude-opus-5-5"}}
        env = dict(os.environ, QUOTIENT_HOME=self.q, HERMES_HOME=self.h, QUOTIENT_LIMITS_LIVE="0",
                   QUOTIENT_SHARE="0", QUOTIENT_TIMER_WINDOW="0")
        r = subprocess.run([sys.executable, os.path.join(HERE, "..", "scripts", "quotient.py"), "hermes-hook"],
                           input=json.dumps(payload), capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout or "{}")

    def state(self):
        with open(os.path.join(self.q, "hermes-jobs.json"), encoding="utf-8") as f:
            return json.load(f)

    def started(self, seconds_ago):
        """Move the start of the current reply back in time (a test cannot wait minutes)."""
        st = self.state()
        st["chat1"]["turn_start"]["epoch"] = time.time() - seconds_ago
        with open(os.path.join(self.q, "hermes-jobs.json"), "w", encoding="utf-8") as f:
            json.dump(st, f)
        return st["chat1"]["turn_start"]["epoch"]

    def timer(self):
        with open(os.path.join(self.q, "timer.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_the_working_time_leaves_out_the_clarify_wait_and_the_users_turns(self):
        with open(os.path.join(self.q, "jobs.jsonl"), "w", encoding="utf-8") as f:
            for _ in range(5):          # 10 min per 1M wt of work, factor x1
                f.write(json.dumps(dict(timed_job(600), session="hermes:old")) + "\n")
        self.hook("pre_llm_call")
        t = self.started(300)
        add_messages(self.h, [(t, "user", None), (t + 10, "assistant", None), (t + 100, "tool", "clarify"),
                              (t + 150, "assistant", None), (t + 200, "tool", "terminal"), (t + 295, "assistant", None)])
        self.hook("post_llm_call", "QUOTE: essential=100000 good=200000 max=400000\nCHOICE: max\nJOB: CONTINUES")
        job = self.state()["chat1"]["job"]
        # 10 + (clarify: the user's 90 s left out) + 50 + 50 + 95 + the last few seconds
        self.assertTrue(205 <= job["seconds"] <= 230, job["seconds"])
        self.assertEqual(job["predicted_seconds"], 240)
        self.assertEqual(self.timer()["state"], "pause")
        context = self.hook("pre_llm_call")["context"]
        self.assertIn("working time so far", context)
        self.assertNotIn("per 1M wt of work", context)   # 1.1.7: in quote-table's expected time, not in the line
        self.assertEqual(self.timer()["state"], "run")
        t = self.started(60)
        add_messages(self.h, [(t, "user", None), (t + 58, "assistant", None)])
        self.hook("post_llm_call", "Fatto.\nJOB: CLOSE")
        with open(os.path.join(self.q, "jobs.jsonl"), encoding="utf-8") as f:
            row = [json.loads(x) for x in f if x.strip()][-1]
        self.assertTrue(265 <= row["seconds"] <= 300, row["seconds"])
        self.assertEqual(row["predicted_seconds"], 240)
        self.assertEqual(self.timer()["state"], "end")
        self.assertIn("against about 4 min expected", self.hook("pre_llm_call")["context"])

    def test_a_dropped_job_hides_the_stopwatch(self):
        self.hook("pre_llm_call")
        self.hook("post_llm_call", "QUOTE: essential=1000 good=2000 max=4000\nCHOICE: max\nJOB: CONTINUES")
        self.hook("post_llm_call", "JOB: DROP")
        self.assertTrue(self.timer().get("hidden"))


class TestBackfillTime(Base):
    def test_old_jobs_get_their_time_from_the_logs_once(self):
        # an installment job: its runs
        folder = pv.rate_dir("libro")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "runs.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"started": "2026-10-10T03:00:00+02:00", "finished": "2026-10-10T03:10:00+02:00"}) + "\n")
            f.write(json.dumps({"started": "2026-10-11T03:00:00+02:00", "finished": "2026-10-11T03:05:00+02:00"}) + "\n")
        rate = {"session": "rate:libro", "raw_estimate": 1, "actual": 1, "started": "2026-10-10T02:59:00+02:00",
                "finished": "2026-10-11T03:05:00+02:00"}
        # a Claude Code job: its transcript (the CHOICE line ends the first turn: that turn counts from its start)
        for ts, row in (("2026-10-05T10:00:00.000Z", {"type": "user", "message": {"content": "go"}}),
                        ("2026-10-05T10:00:30.000Z", {"type": "assistant", "message": {"content": []}}),
                        ("2026-10-05T10:05:00.000Z", {"type": "user", "message": {"content": "more"}}),
                        ("2026-10-05T10:06:00.000Z", {"type": "assistant", "message": {"content": []}})):
            row["timestamp"] = ts
            self.t._write(row)
        claude = {"session": "cc1", "raw_estimate": 1, "actual": 1, "started": "2026-10-05T10:00:30+00:00",
                  "finished": "2026-10-05T10:06:00+00:00"}
        # a Hermes job: its chat's messages
        h = fake_hermes_db([(1000.0, "user", None), (1020.0, "assistant", None), (1500.0, "user", None),
                            (1530.0, "assistant", None)])
        hermes = {"session": "hermes:chat1", "raw_estimate": 1, "actual": 1, "started": iso(1000.0),
                  "finished": iso(1530.0)}
        lost = {"session": "gone", "raw_estimate": 1, "actual": 1, "started": iso(1.0), "finished": iso(2.0)}
        write_jobs([rate, claude, hermes, lost])
        with mock.patch.object(pv, "find_transcript", side_effect=lambda sid, *a: self.t.path if sid == "cc1" else None):
            self.assertEqual(pv.backfill_time(home_hermes=h), 3)
            self.assertEqual(pv.backfill_time(home_hermes=h), 0)     # each job is looked at once
        jobs = pv.read_jsonl(os.path.join(pv.home(), "jobs.jsonl"))
        self.assertEqual([j.get("seconds") for j in jobs], [900, 30 + 60, 20 + 30, None])
        self.assertTrue(all(j.get("time_checked") for j in jobs))


class TestStopwatch(Base):
    def test_run_pause_and_end(self):
        cfg = pv.config()
        with mock.patch.object(pv.time, "time", return_value=1000.0):
            pv.timer_put(cfg, "run", 0, 600, "max", start=True)
        st = pv.timer_state()
        self.assertEqual(pv.timer_seconds(st, now=1090.0), 90)
        pv.timer_put(cfg, "pause", 95, label="max")
        st = pv.timer_state()
        self.assertEqual((st["state"], pv.timer_seconds(st, now=99999.0), st["predicted"]), ("pause", 95, 600))
        pv.timer_put(cfg, "end", 120)
        self.assertEqual(pv.timer_state()["state"], "end")

    def test_the_window_is_off_unless_asked(self):
        self.assertFalse(pv.config()["timer"]["window"])
        self.assertFalse(pv.timer_window_open(pv.config()))
        with mock.patch.dict(os.environ, {"QUOTIENT_TIMER_WINDOW": ""}):
            pv.store(("timer", "window"), False)
            self.assertFalse(pv.timer_window_open(pv.config()))

    def test_only_the_agents_own_start_counts_as_the_start_of_the_work(self):
        cfg = pv.config()
        with mock.patch.object(pv.time, "time", return_value=5000.0):
            pv.timer_put(cfg, "run", 0, None, "good", start=True)
        self.assertIsNone(pv.timer_started_in(4000.0, 6000.0))    # started by a hook
        st = pv.timer_state()
        st["by"] = "command"
        pv.save_json(pv.timer_path(), st)
        self.assertEqual(pv.timer_started_in(4000.0, 6000.0), 5000.0)
        self.assertIsNone(pv.timer_started_in(5100.0, 6000.0))    # another reply

    def test_the_status_line_shows_the_stopwatch(self):
        pv.timer_put(pv.config(), "pause", 600, 1800, "max", start=True)
        self.assertIn("⏱ 10 min / ~30 min", self.run_hook(pv.statusline, {}))


class TestInstallmentTime(Base):
    def test_each_installment_says_how_long_it_worked(self):
        cfg = pv.config()
        write_jobs([timed_job(300, session="rate:a%d" % i) for i in range(3)])   # 5 min per 1M wt
        job = {"name": "n", "daily_cap": 2200000, "overhead_at_quote": 0.1, "status": "open", "quote": None}
        self.assertAlmostEqual(pv.installment_seconds(cfg, job), 600.0)        # 2M of work in a 2.2M cap
        runs = [{"started": "2026-10-10T03:00:00+02:00", "finished": "2026-10-10T03:12:00+02:00", "wt": 1,
                 "cap": 2200000, "predicted_seconds": 600}]
        lines = pv.report_lines("n", job, runs, 0, self.dir)
        self.assertIn("12 min of work (about 10 min expected)", lines[1])
        self.assertIn("12 min of work.", lines[2])
        title, body = pv.installment_toast("n", job, runs, dict(cfg, lang="it"), page=True)
        self.assertIn("12 min di lavoro (previsti circa 10 min)", body)


if __name__ == "__main__":
    unittest.main()
