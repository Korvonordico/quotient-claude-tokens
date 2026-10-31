"""Improvement 1: `task-file` writes the task of a job apart or in installments from a few answers, the PRP method:
what and why, the exact files, code examples, the commands to check, the three stops (Francesco, 30/10/2026).
Run: python -m unittest discover tests"""

import builtins
import os
import sys
from unittest import mock

import unittest

from test_v116 import Cli, pv


class TaskFile(Cli):
    def setUp(self):
        super().setUp()
        self.work = os.path.join(self.dir, "work")
        os.makedirs(os.path.join(self.work, "lib"))
        with open(os.path.join(self.work, "lib", "code.py"), "w", encoding="utf-8") as f:
            f.write("".join("line %d\n" % n for n in range(1, 101)))
        self.task = os.path.join(self.dir, "out", "TASK.md")

    def write(self, *more):
        no_terminal = mock.patch.object(sys.stdin, "isatty", return_value=False, create=True)
        with no_terminal:
            return self.cli("task-file", "--out", self.task, "--dir", self.work, *more)

    def text(self):
        with open(self.task, encoding="utf-8") as f:
            return f.read()

    def full(self, *more):
        return self.write("--what", "Aggiungi la funzione X.", "--why", "Serve al preventivo.", "--read", "lib/code.py",
                          "--read", "lib/code.py:5-9", "--example", "lib/code.py:10-12", "--check",
                          "python -m unittest", "--goal", "tutti i test passano", "--lang", "it", *more)

    def test_every_part_of_the_method_is_in_the_file(self):
        told = self.full()
        text = self.text()
        self.assertIn("Compito scritto", told)
        self.assertNotIn("Senza risposta", told)
        self.assertNotIn("Non trovati", told)
        self.assertTrue(text.startswith("# Aggiungi la funzione X."))
        for piece in ("## Cosa fare", "Aggiungi la funzione X.", "## Perché", "Serve al preventivo.",
                      "## File da leggere", "`lib/code.py` (100 righe)", "`lib/code.py` (righe 5-9)",
                      "## Esempi del codice", "line 10\nline 11\nline 12", "## Comandi per controllarti",
                      "`python -m unittest`", "## Le tre fermate", "Obiettivo raggiunto: tutti i test passano.",
                      "Tetto:", "Bloccato: dopo 3 tentativi", "non fare domande", os.path.abspath(self.work)):
            self.assertIn(piece, text)
        self.assertNotIn("line 13", text)

    def test_it_can_run_with_only_the_arguments_and_says_what_is_missing(self):
        told = self.write("--what", "Fai Y", "--lang", "it")
        text = self.text()
        self.assertIn("Senza risposta: perche', file da leggere, esempi di codice, comandi di controllo", told)
        self.assertNotIn("## Perché", text)
        self.assertIn("Nessun file indicato", text)
        self.assertIn("Nessun esempio indicato", text)
        self.assertIn("Nessun comando indicato", text)
        self.assertIn("tutto quello che c'è in «Cosa fare» è fatto", text)

    def test_what_is_needed_at_least(self):
        with self.assertRaises(SystemExit):
            self.write("--why", "Y")
        self.assertFalse(os.path.exists(self.task))

    def test_an_existing_file_stays_unless_forced(self):
        self.write("--what", "Prima")
        with self.assertRaises(SystemExit):
            self.write("--what", "Dopo")
        self.assertIn("Prima", self.text())
        self.write("--what", "Dopo", "--force")
        self.assertIn("Dopo", self.text())

    def test_a_name_that_is_not_there_is_said_and_marked(self):
        told = self.write("--what", "Z", "--lang", "it", "--read", "lib/nope.py", "--example", "lib/gone.py:1-3")
        text = self.text()
        self.assertIn("Non trovati", told)
        self.assertIn("lib/nope.py", told)
        self.assertIn("lib/gone.py", told)
        self.assertIn("`lib/nope.py` (NON TROVATO", text)
        self.assertIn("Nessun esempio indicato", text)    # nothing to copy: it does not invent one

    def test_a_long_example_is_cut_as_the_setting_says(self):
        self.write("--what", "Z", "--lang", "en", "--example", "lib/code.py")
        text = self.text()
        self.assertIn("line 60\n", text)
        self.assertNotIn("line 61\n", text)
        self.assertIn("(cut at 60 lines of 100)", text)
        pv.store(("rate", "task_file_lines"), 0)
        self.write("--what", "Z", "--lang", "en", "--example", "lib/code.py", "--force")
        self.assertIn("line 100\n", self.text())

    def test_the_stuck_stop_follows_the_setting(self):
        pv.store(("rate", "task_file_stuck"), 5)
        self.write("--what", "Z", "--lang", "en")
        self.assertIn("Stuck: after 5 attempts", self.text())

    def test_an_example_with_a_fence_inside_stays_whole(self):
        with open(os.path.join(self.work, "doc.md"), "w", encoding="utf-8") as f:
            f.write("```\ncode\n```\n")
        self.write("--what", "Z", "--example", "doc.md")
        self.assertIn("````\n```\ncode\n```\n````", self.text())

    def test_a_windows_path_is_not_read_as_a_range(self):
        self.assertEqual(pv.task_spot("lib/a.py:3-8", "x")[2:], (3, 8))
        self.assertEqual(pv.task_spot("lib/a.py:3", "x")[2:], (3, 3))
        full = os.path.join(self.work, "lib", "code.py")
        self.assertEqual(pv.task_spot(full, "x")[1:], (full, None, None))
        self.assertEqual(pv.task_spot(full + ":2-4", "x")[1:], (full, 2, 4))

    def test_in_a_terminal_it_asks_only_what_is_missing(self):
        answers = iter(["Perche' si", "lib/code.py", "", "lib/code.py:1-2", "", "python t.py", "", "quando passa"])
        with mock.patch.object(sys.stdin, "isatty", return_value=True, create=True), \
                mock.patch.object(builtins, "input", lambda q="": next(answers)):
            self.cli("task-file", "--out", self.task, "--dir", self.work, "--what", "Fai Y", "--lang", "it")
        text = self.text()
        for piece in ("Perche' si", "`lib/code.py` (100 righe)", "line 1\nline 2", "`python t.py`", "quando passa."):
            self.assertIn(piece, text)

    def test_no_ask_never_asks(self):
        with mock.patch.object(sys.stdin, "isatty", return_value=True, create=True), \
                mock.patch.object(builtins, "input", side_effect=AssertionError("asked")):
            self.cli("task-file", "--out", self.task, "--dir", self.work, "--what", "Fai Y", "--no-ask")
        self.assertIn("Fai Y", self.text())

    def test_the_file_works_for_a_job_and_passes_the_task_check(self):
        self.full()
        pv.store(("rate", "task_check"), 1)
        told = self.cli("rate", "new", "lavoro", "--dir", self.work, "--task-file", self.task, "--daily", "500000")
        self.assertNotIn("Task check", told)
        with open(os.path.join(pv.rate_dir("lavoro"), "TASK.md"), encoding="utf-8") as f:
            self.assertIn("Le tre fermate", f.read())

    def test_the_protocol_names_it_only_when_on(self):
        cfg = pv.config()
        self.assertEqual(cfg["rate"]["task_file_hint"], 0)
        self.assertNotIn("task-file --out", pv.protocol(cfg, 0.5))
        pv.store(("rate", "task_file_hint"), 1)
        self.assertIn("task-file --out", pv.protocol(pv.config(), 0.5))

    def test_it_is_in_the_list_of_commands(self):
        self.assertIn("task-file", self.cli("commands"))


if __name__ == "__main__":
    unittest.main()
