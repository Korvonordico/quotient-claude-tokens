"""31/10/2026: sor-tappa4 was stopped by the timeout after 4 hours and recorded 0 wt and no session: the session id comes
only with the answer at the end of a run. A stopped installment now counts its real cost, from its transcript."""

import json
import os
import shutil
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from q_patch import patch_q
from test_quotient import Base, pv


def stamp(seconds=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def local(seconds=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).astimezone().isoformat(timespec="seconds")


class Stopped(Base):
    def setUp(self):
        super().setUp()
        self.user = os.path.join(self.dir, "user")
        patcher = mock.patch.dict(os.environ, {"HOME": self.user, "USERPROFILE": self.user})
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("QUOTIENT_STOP_AT", None)
        self.addCleanup(shutil.rmtree, self.dir, True)

    def new_job(self, name="stop", **kw):
        args = mock.Mock(dir=self.dir, task="job", task_file=None, days=None, daily=5000000, quote=None, model=None,
                         after="nothing")
        args.name = name
        for k, v in kw.items():
            setattr(args, k, v)
        self.run_hook(lambda: pv.rate_new(args), {})
        return pv.rate_dir(name)

    def transcript(self, folder, sid="11111111-aaaa", at=0, calls=3):
        """A session of an installment: its first prompt names the job's TASK.md."""
        project = os.path.join(self.user, ".claude", "projects", "proj")
        os.makedirs(project, exist_ok=True)
        path = os.path.join(project, sid + ".jsonl")
        rows = [{"type": "queue-operation", "timestamp": stamp(at)},
                {"type": "user", "entrypoint": "sdk-cli", "timestamp": stamp(at + 1),
                 "message": {"role": "user", "content": "1. Read the job: %s" % os.path.join(folder, "TASK.md")}}]
        for i in range(calls):
            rows.append({"type": "assistant", "requestId": "r%d" % i, "timestamp": stamp(at + 2 + i),
                         "message": {"id": "m%d" % i, "model": "claude-opus-5-5", "role": "assistant", "content": [],
                                     "usage": {"input_tokens": 1000, "output_tokens": 100, "cache_read_input_tokens": 0,
                                               "cache_creation_input_tokens": 0}}})
        with open(path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        return path

    def run_stopped(self, name, how):
        args = mock.Mock(force=True, woke=None)
        args.name = name
        folder = pv.rate_dir(name)

        def stopped(cmd, **k):
            self.prompt = cmd[2]
            self.stop_at = os.environ.get("QUOTIENT_STOP_AT")
            self.marker = os.path.exists(os.path.join(folder, "run-open.json"))
            self.transcript(folder)
            return how()
        with patch_q(pv, "find_claude", return_value="claude"), mock.patch.object(pv.subprocess, "run", side_effect=stopped):
            self.run_hook(lambda: pv.run_installment(args), {})
        return pv.read_jsonl(os.path.join(folder, "runs.jsonl"))[-1]


class TestStoppedRun(Stopped):
    def check_measured(self, run):
        self.assertEqual(run["session"], "11111111-aaaa")
        self.assertGreater(run["wt"], 0)
        self.assertEqual(run["calls"], 3)
        self.assertEqual(run["tokens"]["input_tokens"], 3000)
        self.assertEqual(run["tokens"]["output_tokens"], 300)
        self.assertIsNone(run["usd"])   # not known: Claude Code's answer gives it, and there was none

    def test_a_run_stopped_by_the_timeout_counts_its_cost(self):
        self.new_job()

        def too_long():
            raise pv.subprocess.TimeoutExpired("c", 1)
        run = self.run_stopped("stop", too_long)
        self.assertEqual(run["error"], "timeout")
        self.check_measured(run)
        job = pv.load_json(os.path.join(pv.rate_dir("stop"), "job.json"), None)
        self.assertEqual(job["families"], {"opus": run["wt"]})
        self.assertFalse(os.path.exists(os.path.join(pv.rate_dir("stop"), "run-open.json")))
        self.assertTrue(self.marker)
        _, body = pv.installment_toast("stop", job, [run], pv.config())
        self.assertIn("spent", body)

    def test_a_run_killed_counts_its_cost(self):
        self.new_job()
        run = self.run_stopped("stop", lambda: mock.Mock(stdout=b"", stderr=b"killed", returncode=1))
        self.assertEqual(run["error"], "killed")
        self.check_measured(run)

    def test_no_transcript_stays_at_zero(self):
        folder = self.new_job()
        args = mock.Mock(force=True, woke=None)
        args.name = "stop"
        with patch_q(pv, "find_claude", return_value="claude"), \
                mock.patch.object(pv.subprocess, "run", side_effect=pv.subprocess.TimeoutExpired("c", 1)):
            self.run_hook(lambda: pv.run_installment(args), {})
        run = pv.read_jsonl(os.path.join(folder, "runs.jsonl"))[-1]
        self.assertEqual((run["wt"], run["session"]), (0, None))

    def test_only_its_own_transcript(self):
        folder = self.new_job()
        other = self.new_job("other")
        begin, end = local(-100), local(100)
        self.transcript(other, "other-job")
        self.assertIsNone(pv.find_run_transcript(folder, begin, end))
        self.transcript(folder, "too-old", at=-3600)
        self.transcript(folder, "too-late", at=3600)
        self.assertIsNone(pv.find_run_transcript(folder, begin, end))
        mine = self.transcript(folder, "mine")
        self.assertEqual(pv.find_run_transcript(folder, begin, end), mine)
        self.assertIsNone(pv.find_run_transcript(folder, begin, end, {"mine"}))   # already another run's


class TestRepair(Stopped):
    def old_line(self, folder, **kw):
        line = dict({"started": local(-100), "finished": local(100), "session": None, "wt": 0, "calls": None, "usd": None,
                     "tokens": None, "error": "timeout", "done": False, "cap": 5000000, "progress": 70.0, "pieces": [],
                     "seconds": 200, "helpers": 0, "helpers_stopped": 0, "check": 1}, **kw)
        pv.append_jsonl(os.path.join(folder, "runs.jsonl"), line)
        return line

    def repair(self, name=None, dry=False):
        args = mock.Mock(dry=dry)
        args.name = name
        return self.run_hook(lambda: pv.rate_repair(args), {})

    def test_an_old_line_gets_its_cost(self):
        folder = self.new_job()
        self.old_line(folder)
        self.transcript(folder)
        said = self.repair("stop", dry=True)
        self.assertIn("--dry", said)
        self.assertEqual(pv.read_jsonl(os.path.join(folder, "runs.jsonl"))[0]["wt"], 0)
        said = self.repair("stop")
        self.assertNotIn("--dry", said)
        run = pv.read_jsonl(os.path.join(folder, "runs.jsonl"))[0]
        self.assertGreater(run["wt"], 0)
        self.assertEqual(run["session"], "11111111-aaaa")
        self.assertEqual(run["error"], "timeout")
        self.assertEqual(run["repaired"]["wt"], 0)
        self.assertEqual(len([f for f in os.listdir(folder) if f.endswith(".bak")]), 1)
        job = pv.load_json(os.path.join(folder, "job.json"), None)
        self.assertEqual(job["families"], {"opus": run["wt"]})
        self.assertIn("No stopped installment", self.repair("stop"))   # once

    def test_lines_with_a_measure_are_left_alone(self):
        folder = self.new_job()
        self.old_line(folder, wt=500, session="x", error=None)
        self.transcript(folder)
        self.assertIn("No stopped installment", self.repair("stop"))
        self.assertEqual(pv.read_jsonl(os.path.join(folder, "runs.jsonl"))[0]["wt"], 500)

    def test_a_running_job_is_left_alone(self):
        folder = self.new_job()
        self.old_line(folder)
        self.transcript(folder)
        with open(os.path.join(folder, "run.lock"), "w") as f:
            f.write("1")
        self.assertIn("left as it is", self.repair("stop"))
        self.assertEqual(pv.read_jsonl(os.path.join(folder, "runs.jsonl"))[0]["wt"], 0)

    def test_a_finished_job_gets_its_total_right(self):
        folder = self.new_job()
        self.old_line(folder)
        self.old_line(folder, started=local(200), finished=local(300), wt=1000, chat=100, session="y", error=None, calls=2)
        self.transcript(folder)
        job = pv.load_json(os.path.join(folder, "job.json"), None)
        job.update(status="done", actual=1000)
        pv.save_json(os.path.join(folder, "job.json"), job)
        pv.append_jsonl(pv.jobs_path(), {"session": "rate:stop", "started": local(-100), "actual": 1000, "chat": 100, "work": 900,
                                         "raw_estimate": 1000, "ratio": 0.9, "calls": 2})
        self.repair("stop")
        wt = pv.read_jsonl(os.path.join(folder, "runs.jsonl"))[0]["wt"]
        row = pv.read_jsonl(pv.jobs_path())[0]
        self.assertEqual(row["actual"], 1000 + wt)
        self.assertEqual(row["calls"], 5)
        self.assertEqual(pv.load_json(os.path.join(folder, "job.json"), None)["actual"], 1000 + wt)
        self.assertEqual(row["ratio"], round(row["work"] / 1000, 4))

    def test_a_run_quotient_did_not_see_the_end_of(self):
        folder = self.new_job()
        pv.save_json(os.path.join(folder, "run-open.json"), {"started": local(-100), "cap": 777})
        self.transcript(folder)
        run = pv.close_lost_run("stop", pv.config())
        self.assertGreater(run["wt"], 0)
        self.assertEqual(run["cap"], 777)
        self.assertIn("did not see the end", run["error"])
        self.assertEqual(pv.read_jsonl(os.path.join(folder, "runs.jsonl")), [run])
        self.assertFalse(os.path.exists(os.path.join(folder, "run-open.json")))
        self.assertIsNone(pv.close_lost_run("stop", pv.config()))   # once


class TestTimeLimit(Stopped):
    def hook(self, tool, stop_at, given=None, close=None):
        path = self.transcript(pv.rate_dir("stop"), calls=1)
        env = {"QUOTIENT_JOB": "stop", "QUOTIENT_CAP": "5000000", "QUOTIENT_STOP_AT": str(stop_at)}
        cfg = pv.config()
        if close is not None:
            cfg["rate"]["close_minutes"] = close
        with mock.patch.dict(os.environ, env), patch_q(pv, "config", return_value=cfg):
            return self.run_hook(lambda: pv.hook_pretool(), {"session_id": "s", "transcript_path": path, "tool_name": tool,
                                                              "tool_input": given or {}})

    def test_the_prompt_tells_when_it_stops(self):
        self.new_job()

        def too_long():
            raise pv.subprocess.TimeoutExpired("c", 1)
        self.run_stopped("stop", too_long)
        self.assertIn("Time limit", self.prompt)
        at = datetime.fromtimestamp(float(self.stop_at)).strftime("%H:%M")
        self.assertIn(at, self.prompt)
        self.assertIsNone(os.environ.get("QUOTIENT_STOP_AT"))

    def test_new_work_stops_in_the_last_minutes(self):
        self.new_job()
        said = self.hook("Grep", time.time() + 300)
        self.assertIn("nearly out of time", said)
        self.assertIn("deny", said)
        self.assertRegex(said, pv.CAP_RE)

    def test_saving_passes_in_the_last_minutes(self):
        self.new_job()
        self.assertEqual(self.hook("Write", time.time() + 300, {"file_path": os.path.join(self.dir, "x.md")}).strip(), "")
        handoff = os.path.join(pv.rate_dir("stop"), "HANDOFF.md")
        self.assertEqual(self.hook("Edit", time.time() + 300, {"file_path": handoff}).strip(), "")

    def test_before_the_last_minutes_nothing_changes(self):
        self.new_job()
        self.assertEqual(self.hook("Grep", time.time() + 3600).strip(), "")

    def test_it_can_be_turned_off(self):
        self.new_job()
        self.assertEqual(self.hook("Grep", time.time() + 300, close=0).strip(), "")


if __name__ == "__main__":
    unittest.main()
