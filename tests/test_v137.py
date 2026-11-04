"""1.3.7: Token Quotient in Codex, the full version. Codex keeps its own folder (limits, jobs, learning, settings), the
plugin package Codex installs from its plugin list, and installments done by `codex exec`, measured from Codex's log
as they go and stopped from outside at their cap. A fake Codex (a small script) stands in for the real one.
Run: python -m unittest discover tests"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
import unittest
from unittest import mock

from test_quotient import Base, pv

from quotient_lib import q_codex, q_limits, q_runs, q_schedules, q_settings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TID = "0199a213-81c0-7800-8aa1-bbab2a035a53"

FAKE = r'''import json, os, sys, time
args = sys.argv[1:]
assert args[0] == "exec" and "--json" in args and args[-1] == "-", args
prompt = sys.stdin.read()
cwd, folder = args[args.index("--cd") + 1], args[args.index("--add-dir") + 1]
mode = os.environ.get("FAKE_CODEX_MODE", "done")
def out(e):
    print(json.dumps(e), flush=True)
if mode == "login":
    out({"type": "error", "message": "You are not logged in. Run `codex login`."})
    sys.exit(1)
tid = "%s"
d = os.path.join(os.environ["CODEX_HOME"], "sessions", "2026", "11", "04")
os.makedirs(d, exist_ok=True)
path = os.path.join(d, "rollout-2026-11-04T03-00-00-%%s.jsonl" %% tid)
def row(kind, payload):
    return json.dumps({"timestamp": "2026-11-04T03:00:00.000Z", "type": kind, "payload": payload}) + "\n"
with open(path, "w") as f:
    f.write(row("session_meta", {"id": tid, "cwd": cwd}) + row("turn_context", {"model": "gpt-5.5"}))
    f.write(row("event_msg", {"type": "user_message", "message": prompt}))
out({"type": "thread.started", "thread_id": tid})
out({"type": "turn.started"})
total = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
for i in range(3 if mode == "done" else 600):
    last = {"input_tokens": 20000, "cached_input_tokens": 15000, "output_tokens": 1000}
    total = {k: total[k] + last[k] for k in total}
    with open(path, "a") as f:
        f.write(row("event_msg", {"type": "token_count", "info": {"total_token_usage": total, "last_token_usage": last},
                                  "rate_limits": {"primary": {"used_percent": 20.0 + i, "window_minutes": 300,
                                                              "resets_at": 1893456000},
                                                  "secondary": {"used_percent": 30.0, "window_minutes": 10080,
                                                                "resets_at": 1893800000}}}))
    if mode != "done":
        time.sleep(0.1)
with open(os.path.join(folder, "HANDOFF.md"), "w") as f:
    f.write("JOB DONE\nPROGRESS: 100%%\n")
out({"type": "item.completed", "item": {"id": "i1", "type": "agent_message", "text": "Done."}})
out({"type": "turn.completed", "usage": total})
''' % TID

PER_CALL = 5000 + 15000 * 0.1 + 1000 * 5   # 20,000 in of which 15,000 cached, 1,000 out


class CodexBase(Base):
    def setUp(self):
        super().setUp()
        self.codex_home = os.path.join(self.dir, "codexhome")
        os.makedirs(self.codex_home)
        patcher = mock.patch.dict(os.environ, {"CODEX_HOME": self.codex_home, "QUOTIENT_CODEX": "1"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.fake = os.path.join(self.dir, "fake_codex.py")
        with open(self.fake, "w") as f:
            f.write(FAKE)
        self.work = os.path.join(self.dir, "work")
        os.makedirs(self.work)

    def new_job(self, **kw):
        args = mock.Mock(dir=self.work, task="job", task_file=None, days=2, daily=None, quote=500000, model=None,
                         after="nothing")
        args.name = "book"
        for k, v in kw.items():
            setattr(args, k, v)
        with mock.patch.object(q_codex, "find_codex", return_value=None):
            self.run_hook(lambda: pv.rate_new(args), {})
        return pv.load_json(os.path.join(pv.rate_dir("book"), "job.json"), None)

    def run_one(self, codex=None, mode="done"):
        args = mock.Mock(force=True)
        args.name = "book"
        with mock.patch.object(q_codex, "find_codex", return_value=codex or [sys.executable, self.fake]), \
                mock.patch.dict(os.environ, {"FAKE_CODEX_MODE": mode}), mock.patch.object(q_codex, "POLL", 0.2):
            said = self.run_hook(lambda: pv.run_installment(args), {})
        return said, pv.read_jsonl(os.path.join(pv.rate_dir("book"), "runs.jsonl"))[-1]


class TestOwnFolder(Base):
    def test_codex_has_its_own_folder_that_starts_from_claude_settings(self):
        claude_home = q_settings.home()
        pv.save_settings({("lang",): "it"})
        with mock.patch.dict(os.environ, {"QUOTIENT_CODEX": "1"}):
            home = q_settings.home()
            self.assertEqual(home, os.path.join(claude_home, "codex"))
            self.assertEqual(pv.config()["lang"], "it")
            self.assertFalse(pv.config()["share"]["enabled"])
            pv.save_settings({("lang",): "en"})
        self.assertEqual(pv.config()["lang"], "it")   # Codex's change stays in Codex's folder
        self.assertEqual(q_settings.home(), claude_home)

    def test_the_codex_flag_never_reads_claude_limits(self):
        env = dict(os.environ, QUOTIENT_HOME=os.path.join(self.dir, "h"))
        env.pop("QUOTIENT_CODEX", None)
        code = ("import os,sys; sys.argv=['q','commands','--codex']; sys.path.insert(0,%r); import quotient; "
                "quotient.main() if hasattr(quotient,'main') else None; "
                "print('LIVE', os.environ.get('QUOTIENT_LIMITS_LIVE'), os.environ.get('QUOTIENT_CODEX'))"
                % os.path.join(ROOT, "scripts"))
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, env=env, timeout=60)
        self.assertIn(b"LIVE 0 1", done.stdout, done.stderr)


class TestPluginPackage(unittest.TestCase):
    def load(self, rel):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return json.load(f)

    def test_the_manifest(self):
        m = self.load(os.path.join(".codex-plugin", "plugin.json"))
        self.assertEqual(m["version"], q_settings.VERSION)
        self.assertEqual(m["name"], self.load(os.path.join(".claude-plugin", "plugin.json"))["name"])
        self.assertNotIn("commands", m)   # Claude Code's slash commands would run without --codex
        for rel in (m["skills"], m["hooks"], m["interface"]["composerIcon"],
                    m["extensions"]["com.openai"]["onboardingSkill"]):
            self.assertTrue(rel.startswith("./") and ".." not in rel, rel)
            self.assertTrue(os.path.exists(os.path.join(ROOT, rel[2:])), rel)
        market = self.load(os.path.join(".agents", "plugins", "marketplace.json"))
        entry = market["plugins"][0]
        self.assertEqual((entry["name"], entry["source"]["path"]), (m["name"], "./"))
        for key in ("policy", "category"):
            self.assertIn(key, entry)

    def test_the_skills(self):
        base = os.path.join(ROOT, "codex", "skills")
        names = sorted(os.listdir(base))
        self.assertEqual(names, ["help", "rate", "report", "setup"])
        for name in names:
            with open(os.path.join(base, name, "SKILL.md"), encoding="utf-8") as f:
                text = f.read()
            head = text.split("---")[1]
            self.assertIn("name: %s\n" % name, head)
            self.assertRegex(head, r"\ndescription: \S")
            self.assertIn("--codex", text)
        self.assertFalse(os.path.exists(os.path.join(ROOT, "skills")))   # Claude Code would load a root skills/

    def test_the_hooks_say_codex(self):
        hooks = self.load(os.path.join("codex", "hooks.json"))["hooks"]
        self.assertEqual(sorted(hooks), ["SessionStart", "Stop", "UserPromptSubmit"])
        for groups in hooks.values():
            h = groups[0]["hooks"][0]
            self.assertTrue(h["command"].endswith(" --codex") and "$PLUGIN_ROOT/scripts/run.sh" in h["command"])
            self.assertTrue(h["commandWindows"].endswith(" --codex") and "%PLUGIN_ROOT%" in h["commandWindows"])

    def payload(self, home):
        rollout = os.path.join(home, "rollout-2026-11-04T03-00-00-x.jsonl")
        os.makedirs(home, exist_ok=True)
        with open(rollout, "w") as f:
            f.write(json.dumps({"timestamp": "2026-11-04T03:00:00Z", "type": "event_msg",
                                "payload": {"type": "user_message", "message": "hi"}}) + "\n")
        return json.dumps({"session_id": "p1", "transcript_path": rollout, "turn_id": "t", "prompt": "hi",
                           "hook_event_name": "UserPromptSubmit", "cwd": home}).encode()

    def run_command(self, command, shell_cmd):
        import tempfile
        tmp = tempfile.mkdtemp()
        env = dict(os.environ, PLUGIN_ROOT=ROOT.replace("\\", "/") if "run.sh" in command else ROOT,
                   QUOTIENT_HOME=os.path.join(tmp, "q"))
        env.pop("QUOTIENT_CODEX", None)
        done = subprocess.run(shell_cmd, input=self.payload(tmp), capture_output=True, env=env, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(b"[Quotient", done.stdout, done.stderr)
        self.assertTrue(os.path.isdir(os.path.join(tmp, "q", "codex")))

    @unittest.skipUnless(os.name == "nt", "cmd.exe runs Codex's hooks on Windows")
    def test_the_windows_hook_runs_with_cmd(self):
        h = self.load(os.path.join("codex", "hooks.json"))["hooks"]["UserPromptSubmit"][0]["hooks"][0]
        # as Codex does (hooks/src/engine/command_runner.rs): cmd.exe /C, then the command line in one pair of quotes
        self.run_command(h["commandWindows"], 'cmd.exe /C "%s"' % h["commandWindows"])

    @unittest.skipUnless(shutil.which("sh"), "no sh")
    def test_the_posix_hook_runs_with_sh(self):
        h = self.load(os.path.join("codex", "hooks.json"))["hooks"]["UserPromptSubmit"][0]["hooks"][0]
        self.run_command(h["command"], [shutil.which("sh"), "-c", h["command"]])


class TestCodexInstallments(CodexBase):
    def test_a_job_made_in_codex_is_done_by_codex_exec(self):
        job = self.new_job()
        self.assertEqual(job["engine"], "codex")
        self.assertTrue(pv.rate_dir("book").startswith(os.path.join(q_settings.home())))
        self.assertIn(os.sep + "codex" + os.sep, pv.rate_dir("book"))
        said, run = self.run_one()
        self.assertEqual((run["engine"], run["session"], run["calls"], run["error"], run["done"]),
                         ("codex", TID, 3, None, True))
        self.assertAlmostEqual(run["wt"], 3 * PER_CALL, delta=3)
        self.assertEqual(pv.load_json(os.path.join(pv.rate_dir("book"), "job.json"), None)["status"], "done")
        last = pv.read_jsonl(q_limits.limits_path())[-1]
        self.assertEqual((last["source"], last["five_hour"], last["seven_day"]), ("codex", 22.0, 30.0))
        finished = pv.read_jsonl(os.path.join(q_settings.home(), "jobs.jsonl"))[-1]
        self.assertEqual(finished["choice"], "rate")

    def test_the_prompt_goes_on_stdin_and_tells_what_codex_does_at_the_cap(self):
        self.new_job()
        seen = {}
        real = q_codex.run_exec

        def spy(cmd, prompt, *a):
            seen["cmd"], seen["prompt"] = cmd, prompt
            return real(cmd, prompt, *a)

        with mock.patch.object(q_codex, "run_exec", side_effect=spy):
            self.run_one()
        self.assertEqual(seen["cmd"][-1], "-")
        self.assertIn("--sandbox", seen["cmd"])
        self.assertIn("workspace-write", seen["cmd"])
        self.assertIn("stops this installment from outside", seen["prompt"])
        self.assertNotIn("lets Write and Edit through", seen["prompt"])
        self.assertIn("6. When the WHOLE job is finished", seen["prompt"])
        self.assertIn("Time limit:", seen["prompt"])

    def test_the_cap_stops_codex_from_outside(self):
        self.new_job(quote=200000, days=2)    # 100,000 wt an installment: about 9 calls of the fake
        started = time.time()
        said, run = self.run_one(mode="slow")
        self.assertLess(time.time() - started, 30)
        self.assertEqual(run["stopped"], "cap")
        self.assertIsNone(run["error"])
        self.assertGreaterEqual(run["wt"], 100000)
        self.assertLess(run["wt"], 100000 + 20 * PER_CALL)
        self.assertEqual(pv.load_json(os.path.join(pv.rate_dir("book"), "job.json"), None)["status"], "open")

    def test_a_codex_that_is_not_logged_in(self):
        self.new_job()
        said, run = self.run_one(mode="login")
        self.assertEqual(run["error"], q_codex.LOGIN_ERROR)

    def test_codex_installed_with_npm_on_windows_is_a_cmd(self):
        if os.name == "nt":
            wrapper = os.path.join(self.dir, "codex.cmd")
            with open(wrapper, "w") as f:
                f.write('@"%s" "%s" %%*\r\n' % (sys.executable, self.fake))
        else:
            wrapper = os.path.join(self.dir, "codex")
            with open(wrapper, "w") as f:
                f.write('#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable, self.fake))
            os.chmod(wrapper, 0o755)
        self.new_job()
        said, run = self.run_one(codex=[wrapper])
        self.assertEqual((run["session"], run["done"], run["error"]), (TID, True, None))

    def test_apart_and_scheduled_runs_keep_the_codex_flag(self):
        self.new_job()
        seen = []
        with mock.patch.object(q_runs.subprocess, "Popen", side_effect=lambda argv, **kw: seen.append(argv)):
            self.assertTrue(q_runs.start_detached(["rate", "run", "book"], os.path.join(self.dir, "log")))
        self.assertEqual(seen[0][-4:], ["rate", "run", "book", "--codex"])
        self.assertTrue(pv.task_name("book").startswith("quotient-codex-"))
        with mock.patch.object(q_schedules.subprocess, "run", return_value=mock.Mock(returncode=0, stdout=b"", stderr=b"")):
            said = self.run_hook(lambda: q_schedules.schedule("book", "03:00", once=False), {})
        if os.name == "nt":
            with open(os.path.join(pv.rate_dir("book"), "task-daily.xml"), encoding="utf-16") as f:
                self.assertIn("rate run book --codex", f.read())
        else:
            self.assertIn("rate run book --codex", said)

    def test_events_of_codex_exec(self):
        lines = [json.dumps({"type": "thread.started", "thread_id": "t1"}),
                 json.dumps({"type": "turn.completed", "usage": {"input_tokens": 100, "cached_input_tokens": 60,
                                                                  "output_tokens": 10}}),
                 "not json", json.dumps({"type": "turn.failed", "error": {"message": "boom"}})]
        said = q_codex.read_events(lines)
        self.assertEqual((said["session_id"], said["num_turns"], said["error"]), ("t1", 1, "boom"))
        self.assertEqual(said["usage"], {"input_tokens": 40, "cache_read_input_tokens": 60,
                                         "cache_creation_input_tokens": 0, "output_tokens": 10})

    def test_a_claude_model_name_is_not_given_to_codex(self):
        cmd = q_codex.exec_cmd(["codex"], {"dir": "x", "model": "opus"}, "f", {})
        self.assertNotIn("--model", cmd)
        cmd = q_codex.exec_cmd(["codex"], {"dir": "x", "model": "gpt-5.5"}, "f", {})
        self.assertEqual(cmd[cmd.index("--model") + 1], "gpt-5.5")


class TestTwoCopiesOfTheHooks(CodexBase):
    def test_the_same_event_works_once(self):
        ran = []
        data = {"session_id": "s1", "turn_id": "t1", "transcript_path": ""}
        for _ in range(2):
            with mock.patch.object(q_settings, "read_stdin_json", return_value=data):
                q_codex.run_hook(lambda: ran.append(1), "hook-prompt")
        self.assertEqual(len(ran), 1)
        data = dict(data, turn_id="t2")   # the next message works again
        with mock.patch.object(q_settings, "read_stdin_json", return_value=data):
            q_codex.run_hook(lambda: ran.append(1), "hook-prompt")
        self.assertEqual(len(ran), 2)

    def test_setup_codex_remove_takes_only_quotient_away(self):
        path = os.path.join(self.codex_home, "hooks.json")
        mine = {"hooks": [{"type": "command", "command": "echo mine"}]}
        with open(path, "w") as f:
            json.dump({"hooks": {"Stop": [mine]}}, f)
        with mock.patch.object(q_settings, "out"):
            q_codex.setup(mock.Mock(remove=False))
        with open(path) as f:
            self.assertEqual(len(json.load(f)["hooks"]["Stop"]), 2)
        with mock.patch.object(q_settings, "out") as out:
            q_codex.setup(mock.Mock(remove=True))
        with open(path) as f:
            hooks = json.load(f)["hooks"]
        self.assertEqual(hooks["Stop"], [mine])
        self.assertEqual(hooks["UserPromptSubmit"], [])
        self.assertIn("removed", out.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
