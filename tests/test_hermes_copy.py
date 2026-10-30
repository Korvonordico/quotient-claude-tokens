"""Hermes chat summaries: the choice, and the whole chat saved to a file before each summary (Francesco, 30/10/2026).
Run: python -m unittest discover tests"""

import os
import sqlite3
import sys
import tempfile
from unittest import mock

import unittest

from test_v116 import Cli, pv

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import hermes_hooks as h  # noqa: E402
import hermes_source as hs  # noqa: E402


def fake_hermes(folder, rows):
    con = sqlite3.connect(os.path.join(folder, "state.db"))
    con.execute("create table messages (session_id text, role text, content text, timestamp real)")
    con.executemany("insert into messages values (?, ?, ?, ?)", rows)
    con.commit()
    con.close()


ROWS = [("S1", "user", "first question", 100.0), ("S1", "assistant", "first answer", 110.0),
        ("S1", "tool", "a tool result", 115.0), ("S2", "user", "another chat", 120.0),
        ("S1", "user", "[CONTEXT COMPACTION] summary of the chat", 200.0), ("S1", "assistant", "after it", 210.0)]


class HermesCopy(Cli):
    def test_setup_saves_the_choice(self):
        self.assertIsNone(pv.config()["chat"]["hermes_copy"])
        text = self.cli("setup", "--hermes-copy", "yes")
        self.assertIn("first saves the whole chat", text)
        self.assertTrue(pv.config()["chat"]["hermes_copy"])
        self.cli("setup", "--hermes-copy", "no")
        self.assertFalse(pv.config()["chat"]["hermes_copy"])

    def test_the_whole_chat_is_saved_once_per_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            fake_hermes(folder, ROWS)
            cfg = pv.config()
            cfg["chat"].update(hermes_copy=True, hermes_copy_since=50)
            chat = {}
            with mock.patch.dict(os.environ, {"HERMES_HOME": folder}):
                written = h.save_copies(pv, cfg, "S1", chat, 300.0)
                self.assertEqual(len(written), 1)
                with open(os.path.join(pv.home(), "chats", written[0]), encoding="utf-8") as f:
                    text = f.read()
                self.assertIn("first question", text)
                self.assertIn("first answer", text)
                for missing in ("a tool result", "another chat", "summary of the chat", "after it"):
                    self.assertNotIn(missing, text)
                self.assertEqual(h.save_copies(pv, cfg, "S1", chat, 400.0), [])     # the same summary: no new file

    def test_nothing_is_saved_when_off_or_not_chosen(self):
        with tempfile.TemporaryDirectory() as folder:
            fake_hermes(folder, ROWS)
            cfg = pv.config()
            with mock.patch.dict(os.environ, {"HERMES_HOME": folder}):
                for choice in (None, False):
                    cfg["chat"].update(hermes_copy=choice, hermes_copy_since=50)
                    self.assertEqual(h.save_copies(pv, cfg, "S1", {}, 300.0), [])
            self.assertFalse(os.path.isdir(os.path.join(pv.home(), "chats")))

    def test_no_hermes_no_copy(self):
        self.assertEqual(hs.chat_text("S1", 300.0, home=tempfile.gettempdir() + "/no-hermes-here"), "")


if __name__ == "__main__":
    unittest.main()
