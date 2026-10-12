"""0.9.8, for Anthropic's plugin directory: the name token-quotient, the plan limits read through Claude Code's
own /usage (never the login), launchers that run one exact file, commands that may run only their own script."""

import json
import os
import re
import struct
import time
import unittest
from datetime import datetime
from unittest import mock

from test_quotient import Base, pv  # noqa: F401 (pv: the script, loaded with the tests' environment)
import limits_usage as lu  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SAMPLE = ("You are currently using your subscription to power your Claude Code usage\n\n"
          "Current session: 22% used \u00b7 resets Oct 12, 3:49am (Europe/Rome)\n"
          "Current week (all models): 80% used \u00b7 resets Oct 12, 6:59am (Europe/Rome)\n"
          "Current week (Fable): 0% used \u00b7 resets Oct 12, 7am (Europe/Rome)\n")


def local(epoch):
    return datetime.fromtimestamp(epoch)


class UsageText(unittest.TestCase):
    def test_the_lines_of_usage(self):
        snap = lu.parse(SAMPLE, datetime(2026, 10, 12, 2, 0))
        self.assertEqual(snap["five_hour"], 22.0)
        self.assertEqual(snap["seven_day"], 80.0)  # the week of all models, not the week of one model
        self.assertEqual(local(snap["five_hour_resets"]), datetime(2026, 10, 12, 3, 49))
        self.assertEqual(local(snap["seven_day_resets"]), datetime(2026, 10, 12, 6, 59))

    def test_the_forms_of_a_reset_time(self):
        now = datetime(2026, 12, 30, 22, 0)
        self.assertEqual(local(lu.reset_epoch(" \u00b7 resets Jan 2, 7am (Europe/Rome)", now)), datetime(2027, 1, 2, 7, 0))
        self.assertEqual(local(lu.reset_epoch(" \u00b7 resets Dec 31, 12am", now)), datetime(2026, 12, 31, 0, 0))
        self.assertEqual(local(lu.reset_epoch(" \u00b7 resets 1:30pm", now)), datetime(2026, 12, 31, 13, 30))
        self.assertEqual(local(lu.reset_epoch(" \u00b7 resets 11pm", now)), datetime(2026, 12, 30, 23, 0))
        self.assertIsNone(lu.reset_epoch("no time here", now))

    def test_without_a_plan_there_is_no_reading(self):
        self.assertIsNone(lu.parse("Plan limits are shown only for Pro and Max subscriptions."))

    def test_claude_runs_without_hooks_and_without_saving_a_session(self):
        answer = json.dumps({"type": "result", "is_error": False, "result": SAMPLE, "total_cost_usd": 0})
        with mock.patch.object(lu.subprocess, "run", return_value=mock.Mock(stdout=answer.encode("utf-8"))) as run, \
                mock.patch.dict(os.environ, {"CLAUDECODE": "1"}):
            snap = lu.fetch("claude.exe")
        cmd = run.call_args[0][0]
        self.assertEqual(cmd[:3], ["claude.exe", "-p", "/usage"])
        self.assertIn("--no-session-persistence", cmd)
        self.assertEqual(json.loads(cmd[cmd.index("--settings") + 1]), {"disableAllHooks": True})
        self.assertNotIn("CLAUDECODE", run.call_args[1]["env"])
        self.assertEqual(snap["seven_day"], 80.0)

    def test_errors_give_no_reading(self):
        self.assertIsNone(lu.fetch(None))
        failed = json.dumps({"is_error": True, "result": SAMPLE}).encode("utf-8")
        with mock.patch.object(lu.subprocess, "run", return_value=mock.Mock(stdout=failed)):
            self.assertIsNone(lu.fetch("claude.exe"))
        with mock.patch.object(lu.subprocess, "run", side_effect=OSError("not there")):
            self.assertIsNone(lu.fetch("claude.exe"))

    def test_the_plugin_never_reads_the_login(self):
        for folder in ("scripts", "commands", "hooks"):
            for name in os.listdir(os.path.join(ROOT, folder)):
                path = os.path.join(ROOT, folder, name)
                if os.path.isfile(path) and not name.endswith(".pyc"):
                    text = open(path, encoding="utf-8").read()
                    self.assertNotIn(".credentials", text, name)
                    self.assertNotIn("api/oauth", text, name)


class Refresh(Base):
    def live(self, answer):
        return [mock.patch.dict(os.environ, {"QUOTIENT_LIMITS_LIVE": "1"}),
                mock.patch.object(pv, "find_claude", return_value="claude.exe"),
                mock.patch.object(lu, "fetch", return_value=answer)]

    def test_claude_is_asked_at_most_every_ten_minutes_even_without_an_answer(self):
        env, find, fetch = self.live(None)
        with env, find, fetch as asked:
            self.assertIsNone(pv.refresh_limits())
            self.assertIsNone(pv.refresh_limits())
        self.assertEqual(asked.call_count, 1)

    def test_a_reading_is_kept_with_its_source(self):
        snap = {"five_hour": 25.0, "five_hour_resets": time.time() + 3600,
                "seven_day": 81.0, "seven_day_resets": time.time() + 86400}
        env, find, fetch = self.live(snap)
        with env, find, fetch:
            pv.refresh_limits()
        self.assertEqual(pv.read_jsonl(pv.limits_path())[-1]["source"], "usage")
        self.assertEqual(pv.latest_limits()["seven_day"]["used"], 81.0)


class Launchers(Base):
    def test_the_launcher_runs_this_exact_copy(self):
        text = open(pv.launcher(), encoding="utf-8").read()
        self.assertIn(repr(os.path.abspath(pv.__file__)), text)
        self.assertIn("runpy.run_path", text)
        self.assertNotIn("glob", text)

    def test_the_status_line_runs_this_exact_folder(self):
        text = open(pv.statusline_launcher(), encoding="utf-8").read()
        self.assertIn(os.path.dirname(os.path.abspath(pv.__file__)).replace("\\", "/") + "/run.sh", text)
        self.assertNotIn("ls -d", text)

    def test_a_session_start_of_the_plugin_moves_only_the_launchers_there_are(self):
        path = os.path.join(pv.home(), "launcher.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write("# an old launcher that looked for the newest copy\n")
        with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_ROOT": ""}):
            pv.refresh_launchers()  # a copy run by hand leaves it alone
        self.assertIn("old launcher", open(path, encoding="utf-8").read())
        with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_ROOT": os.path.dirname(os.path.abspath(pv.__file__))}):
            pv.refresh_launchers()
        self.assertIn(repr(os.path.abspath(pv.__file__)), open(path, encoding="utf-8").read())
        self.assertFalse(os.path.exists(os.path.join(pv.home(), "statusline.sh")))  # never set up: not created


class Manifest(unittest.TestCase):
    def test_the_name_the_version_and_the_icon(self):
        plugin = json.load(open(os.path.join(ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8"))
        market = json.load(open(os.path.join(ROOT, ".claude-plugin", "marketplace.json"), encoding="utf-8"))
        self.assertEqual(plugin["name"], "token-quotient")
        self.assertEqual(plugin["displayName"], "Token Quotient")
        self.assertEqual(market["plugins"][0]["name"], "token-quotient")
        self.assertEqual(plugin["version"], pv.VERSION)
        icon = os.path.join(ROOT, plugin["icon"])
        with open(icon, "rb") as f:
            head = f.read(24)
        self.assertEqual(head[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", head[16:24])
        self.assertEqual(width, height)
        self.assertTrue(512 <= width <= 2048)
        self.assertLess(os.path.getsize(icon), 2 * 1024 * 1024)

    def test_commands_may_run_only_their_own_script(self):
        prefix = 'sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" '
        for name in sorted(os.listdir(os.path.join(ROOT, "commands"))):
            text = open(os.path.join(ROOT, "commands", name), encoding="utf-8").read()
            rules = re.findall(r"Bash\(([^)]*)\)", text.split("---")[1])
            for rule in rules:
                self.assertTrue(rule.startswith(prefix), (name, rule))
            for injected in re.findall(r"!`([^`]*)`", text):
                self.assertTrue(any(injected == r or (r.endswith(" *") and injected.startswith(r[:-1])) for r in rules),
                                (name, injected))

    def test_no_old_command_names_are_left(self):
        for rel in ("README.md", "README.it.md", "docs/index.html", "PRIVACY.md", "CONTRIBUTING.md",
                    "scripts/quotient.py", "commands/setup.md", "commands/share.md"):
            text = open(os.path.join(ROOT, rel), encoding="utf-8").read()
            self.assertIsNone(re.search(r"(?<![\w-])/quotient:|/plugin install quotient@quotient", text), rel)


if __name__ == "__main__":
    unittest.main()
