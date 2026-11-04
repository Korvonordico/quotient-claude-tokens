"""1.3.6: Quotient inside OpenAI Codex (experimental). Codex's session log (rollout-*.jsonl) is read as a Claude Code
transcript: user messages, one assistant entry per model call with its usage (cached input = cache read), the model's
text; the plan limits come from the same log. `setup-codex` writes Codex's hooks.json.
Run: python -m unittest discover tests"""

import json
import os
import subprocess
import sys
import unittest
from unittest import mock

from test_quotient import Base, pv

from quotient_lib import q_codex, q_limits, q_runs

ENTRY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "quotient.py")
RESET5, RESET7 = 1893456000, 1893800000


def row(kind, payload, ts="2026-11-04T01:00:00.000Z"):
    return {"timestamp": ts, "type": kind, "payload": payload}


def token_count(total, last, five=12.5, week=40.0):
    return row("event_msg", {"type": "token_count",
                             "info": {"total_token_usage": total, "last_token_usage": last, "model_context_window": 272000},
                             "rate_limits": {"primary": {"used_percent": five, "window_minutes": 300, "resets_at": RESET5},
                                             "secondary": {"used_percent": week, "window_minutes": 10080,
                                                           "resets_at": RESET7}}})


def usage(inp, cached, out):
    return {"input_tokens": inp, "cached_input_tokens": cached, "output_tokens": out, "reasoning_output_tokens": 0,
            "total_tokens": inp + out}


def old_log():
    """Two turns; the second has two model calls, and Codex tells the last call again with new limits."""
    u1, u2, u3 = usage(10000, 8000, 500), usage(12000, 10000, 300), usage(13000, 12000, 200)
    t1 = u1
    t2 = {k: u1[k] + u2[k] for k in u1}
    t3 = {k: t2[k] + u3[k] for k in u1}
    return [row("session_meta", {"id": "abc", "cwd": "C:/x"}),
            row("turn_context", {"model": "gpt-5.5", "cwd": "C:/x"}),
            row("event_msg", {"type": "user_message", "message": "hello"}),
            row("event_msg", {"type": "agent_message", "message": "Hi."}),
            token_count(t1, u1),
            row("event_msg", {"type": "user_message", "message": "fix the bug"}, ts="2026-11-04T01:05:00.000Z"),
            token_count(t2, u2),
            row("event_msg", {"type": "agent_message", "message": "Fixed."}),
            token_count(t3, u3, five=14.0),
            token_count(t3, u3, five=14.5)]


class CodexLog(Base):
    def write(self, rows, name="rollout-2026-11-04T01-00-00-abc.jsonl"):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        return path


class TestConvert(CodexLog):
    def test_calls_and_their_cost(self):
        entries = pv.read_jsonl(self.write(old_log()))
        calls = pv.calls_of(entries)
        self.assertEqual(len(calls), 3)                       # the call told twice is counted once
        w = pv.config()["weights"]
        costs = sorted(pv.weigh(u, w) for u in calls.values())
        # 10000 in, 8000 of them cached, 500 out: 2000 + 0.1 x 8000 + 5 x 500
        self.assertIn(2000 + 800 + 2500, costs)
        self.assertIn(1000 + 1200 + 1000, costs)              # 13000 in, 12000 cached, 200 out

    def test_the_turn_is_the_last_message(self):
        turn, start, text = pv.turn_of(self.write(old_log()))
        self.assertEqual(start, "2026-11-04T01:05:00.000Z")
        self.assertEqual(len(pv.calls_of(turn)), 2)
        self.assertEqual(text.strip(), "Fixed.")

    def test_the_newer_log_with_one_record_per_call(self):
        rows = [row("turn_context", {"model": "gpt-5.5"}),
                row("event_msg", {"type": "user_message", "message": "go"}),
                row("token_usage_record", {"response_id": "r1", "usage": dict(usage(5000, 4000, 100),
                                                                              cache_write_input_tokens=500)}),
                token_count(usage(5000, 4000, 100), usage(5000, 4000, 100)),
                row("token_usage_record", {"response_id": "r1", "usage": usage(5000, 4000, 100)})]
        calls = pv.calls_of(pv.read_jsonl(self.write(rows)))
        self.assertEqual(list(calls.values()), [{"input_tokens": 500, "cache_read_input_tokens": 4000,
                                                 "cache_creation_input_tokens": 500, "output_tokens": 100}])

    def test_a_claude_transcript_is_not_touched(self):
        rows = [{"type": "user", "message": {"content": "hi"}, "timestamp": "2026-11-04T01:00:00Z"}]
        self.assertEqual(pv.read_jsonl(self.write(rows, "chat.jsonl")), rows)
        self.assertFalse(q_codex.is_codex_file(os.path.join(self.dir, "chat.jsonl")))

    def test_first_context(self):
        self.assertEqual(pv.first_context(self.write(old_log())), 10000)

    def test_limits(self):
        snap = q_codex.limits_of(old_log())
        self.assertEqual(snap, {"five_hour": 14.5, "five_hour_resets": RESET5, "seven_day": 40.0,
                                "seven_day_resets": RESET7})


class TestHooks(CodexLog):
    def run_codex_hook(self, func, name, payload):
        return self.run_hook(lambda: q_codex.run_hook(func, name), payload)

    def test_a_message_records_codex_limits_and_never_calls_claude(self):
        path = self.write(old_log())
        with mock.patch.dict(os.environ, {"QUOTIENT_CODEX": "1"}), \
                mock.patch.object(q_runs, "start_detached", side_effect=AssertionError("claude -p /usage")):
            said = self.run_codex_hook(pv.hook_prompt, "hook-prompt", {
                "session_id": "c1", "transcript_path": path, "turn_id": "t2", "prompt": "fix the bug",
                "hook_event_name": "UserPromptSubmit"})
            self.assertEqual(os.environ.get("QUOTIENT_LIMITS_LIVE"), "0")
            last = pv.read_jsonl(q_limits.limits_path())[-1]   # 1.3.7: in Codex's own folder
        self.assertIn("[Quotient", said)
        self.assertEqual((last["source"], last["five_hour"], last["seven_day"]), ("codex", 14.5, 40.0))
        self.assertEqual(pv.read_jsonl(q_limits.limits_path()), [])   # Claude Code's limits are not touched

    def test_stop_prints_json_or_nothing(self):
        path = self.write(old_log())
        with mock.patch.dict(os.environ, {"QUOTIENT_CODEX": "1"}):
            said = self.run_codex_hook(pv.hook_stop, "hook-stop", {
                "session_id": "c1", "transcript_path": path, "turn_id": "t2", "last_assistant_message": "Fixed.",
                "stop_hook_active": False})
        self.assertTrue(said == "" or said.lstrip().startswith("{"), said)

    def test_setup_writes_the_hooks_once_and_keeps_others(self):
        codex = os.path.join(self.dir, "codex")
        os.makedirs(codex)
        mine = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}}
        with open(os.path.join(codex, "hooks.json"), "w") as f:
            json.dump(mine, f)
        with mock.patch.dict(os.environ, {"CODEX_HOME": codex}):
            self.run_hook(q_codex.setup, {})
            self.run_hook(q_codex.setup, {})
        with open(os.path.join(codex, "hooks.json")) as f:
            hooks = json.load(f)["hooks"]
        self.assertEqual(sorted(hooks), ["SessionStart", "Stop", "UserPromptSubmit"])
        self.assertEqual(len(hooks["Stop"]), 2)                # the user's own hook and one of Quotient
        handler = hooks["UserPromptSubmit"][0]["hooks"][0]
        self.assertTrue(handler["command"].endswith("hook-prompt --codex"))
        self.assertTrue(handler["commandWindows"].endswith("hook-prompt --codex"))
        self.assertFalse(handler["commandWindows"].startswith('"'))   # PowerShell would not run a quoted first word
        self.assertEqual(handler["additionalContextLimit"], 0)
        shared = pv.config()["share"]["enabled"]   # 1.3.7: Claude Code's sharing stays as it was
        with mock.patch.dict(os.environ, {"QUOTIENT_CODEX": "1"}):
            self.assertFalse(pv.config()["share"]["enabled"])
        self.assertEqual(pv.config()["share"]["enabled"], shared)


class TestCommandLine(CodexLog):
    def test_the_real_command_with_the_codex_flag(self):
        path = self.write(old_log())
        env = dict(os.environ, QUOTIENT_HOME=os.path.join(self.dir, "home2"))
        env.pop("QUOTIENT_CODEX", None)
        payload = {"session_id": "c9", "transcript_path": path, "turn_id": "t1", "prompt": "hello",
                   "hook_event_name": "UserPromptSubmit", "cwd": self.dir}
        done = subprocess.run([sys.executable, ENTRY, "hook-prompt", "--codex"], input=json.dumps(payload).encode(),
                              capture_output=True, env=env, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(b"[Quotient", done.stdout)
        rows = pv.read_jsonl(os.path.join(self.dir, "home2", "codex", "limits.jsonl"))
        self.assertEqual(rows[-1]["source"], "codex")


if __name__ == "__main__":
    unittest.main()
