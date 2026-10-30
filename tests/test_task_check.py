"""1.2.7 (improvement 12): before a job starts, a few lines when its task looks vague or when the CLAUDE.md rules
Claude Code loads for its folder are missing or big (Francesco, 30/10/2026).
Run: python -m unittest discover tests"""

import json
import os
from unittest import mock

import unittest

from test_v116 import Cli, pv

CLEAR = ("Translate the dialogue files in text/ into Italian: read text/README.md first, then each file text/*.txt. "
         "Keep the codes like {NAME} as they are. After each file run python tools/check.py text/it to check the "
         "lines and the codes. The job is finished when every file has its Italian copy and check.py says ok; if a "
         "file cannot be read, stop and write it in the handoff. Write the new files next to the old ones, with _it "
         "in their name.")
VAGUE = "Make the code faster."


class TaskCheck(Cli):
    def setUp(self):
        super().setUp()
        self.top = os.path.join(self.dir, "work")
        self.work = os.path.join(self.top, "game")
        self.user = os.path.join(self.dir, "claude")
        os.makedirs(self.work)
        os.makedirs(self.user)
        env = mock.patch.dict(os.environ, {"QUOTIENT_CLAUDE_DIR": self.user})
        env.start()
        self.addCleanup(env.stop)

    def write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def new(self, task, name="game"):
        return self.cli("rate", "new", name, "--dir", self.work, "--task", task, "--daily", "500000")

    def made(self, name="game"):
        return os.path.isfile(os.path.join(pv.rate_dir(name), "job.json"))

    def test_off_by_default(self):
        self.assertEqual(pv.config()["rate"]["task_check"], 0)
        self.assertNotIn("Task check", self.new(VAGUE))
        self.assertTrue(self.made())

    def test_a_vague_task_is_told_and_the_job_is_still_made(self):
        pv.store(("rate", "task_check"), 1)
        text = self.new(VAGUE)
        self.assertIn("Task check", text)
        self.assertIn("it is short (4 words)", text)
        self.assertIn("it names no file or folder", text)
        self.assertIn("no way to check the work", text)
        self.assertIn("when the job is finished", text)
        self.assertIn("there is no CLAUDE.md in %s" % self.work, text)      # with a thin task, the missing rules too
        self.assertIn(os.path.join(pv.rate_dir("game"), "TASK.md"), text)   # where to improve it: the job's copy
        self.assertTrue(self.made())

    def test_a_clear_task_says_nothing_with_or_without_rules(self):
        pv.store(("rate", "task_check"), 1)
        self.assertNotIn("Task check", self.new(CLEAR, "one"))              # no CLAUDE.md: a clear task does without
        self.write(os.path.join(self.top, "CLAUDE.md"), "Run the tests with python -m unittest.\n")
        self.assertNotIn("Task check", self.new(CLEAR, "two"))
        self.assertEqual(pv.task_check(CLEAR, self.work, pv.config()), [])

    def test_the_rules_are_counted_with_their_imports_and_big_ones_are_told(self):
        pv.store(("rate", "task_check"), 1)
        top = os.path.join(self.top, "CLAUDE.md")
        more = os.path.join(self.top, "notes", "more.md")
        skip = os.path.join(self.top, "notes", "skip.md")
        mine = os.path.join(self.user, "CLAUDE.md")
        here = os.path.join(self.work, ".claude", "CLAUDE.md")
        self.write(top, "Rules. Also @notes/more.md, not `@notes/skip.md`, nor @notes/none.md; mail me@example.com\n")
        self.write(more, "x" * 40000)
        self.write(skip, "y" * 90000)
        self.write(mine, "z" * 1000)
        self.write(here, "Game rules.\n")
        user, project = pv.rules_files(self.work)
        self.assertEqual(user, [mine])
        self.assertEqual(project, [top, more, here])                         # imports kept, code and missing left out
        notes = pv.task_check(CLEAR, self.work, pv.config())
        self.assertEqual(len(notes), 1)
        chars = sum(len(pv.load_text(p)) for p in user + project)
        self.assertIn("about %s tokens" % pv.fmt(chars / 3.5), notes[0])
        self.assertIn(more, notes[0])
        self.assertNotIn(skip, notes[0])

    def test_the_two_numbers_are_settings(self):
        pv.store(("rate", "task_check"), 1)
        self.write(os.path.join(self.top, "CLAUDE.md"), "x" * 40000)
        cfg = pv.config()
        self.assertTrue(any("tokens" in n for n in pv.task_check(CLEAR, self.work, cfg)))
        cfg["rate"].update(task_min_words=3, rules_warn_tokens=0)
        notes = pv.task_check(VAGUE, self.work, cfg)
        self.assertFalse(any("short" in n or "tokens" in n for n in notes))
        self.assertTrue(any("no file" in n for n in notes))

    def test_a_job_apart_gets_the_points_for_the_next_task(self):
        pv.store(("rate", "task_check"), 1)
        with mock.patch.object(pv, "start_detached", return_value=True):
            text = self.cli("rate", "apart", "fast", "--dir", self.work, "--task", VAGUE, "--quote", "400000")
        self.assertIn("Task check", text)
        self.assertIn("for the next task", text)
        self.assertIn("started apart", text)
        with open(os.path.join(pv.rate_dir("fast"), "job.json"), encoding="utf-8") as f:
            self.assertTrue(json.load(f)["apart"])


if __name__ == "__main__":
    unittest.main()
