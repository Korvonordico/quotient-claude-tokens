"""1.2.1: the work in pieces (piece_share, piece_min): a chat job's pieces are a quarter of its corrected quote (at least
250k) instead of 1M; an installment records the PROGRESS line of its handoff each time it changes (never a paused call). Run: python -m unittest discover tests"""

import json
import os
import unittest
from unittest import mock

from q_patch import patch_q

from test_quotient import Base, pv


class V121(Base):
    def setUp(self):
        super().setUp()
        on = mock.patch.dict(pv.DEFAULTS, {"piece_share": 0.25, "piece_min": 250000})
        on.start()
        self.addCleanup(on.stop)


class TestPieceSize(V121):
    def test_sizes(self):
        cfg = pv.config()
        self.assertEqual(pv.piece_size(1000000, 0.5, cfg), 250000)        # a quarter of 500k is under the minimum
        self.assertEqual(pv.piece_size(8000000, 1.0, cfg), 2000000)
        self.assertEqual(pv.piece_size(8000000, 1.0, dict(cfg, piece_share=0)), 1000000)   # as before 1.2.1

    def test_a_small_job_is_asked_its_progress(self):
        cfg = pv.config()
        self.assertEqual(pv.pace_note(1000000, 1.0, 200000, 60, cfg), "")              # inside the first piece
        self.assertIn("PROGRESS", pv.pace_note(1000000, 1.0, 300000, 60, cfg))         # past it: before, only after 1M

    def test_packages_at_each_piece(self):
        cfg = pv.config()
        job = {"raw_estimate": 1000000, "factor_used": 1.0}
        self.assertIsNone(pv.add_package(job, 200000, 20, cfg))
        self.assertIsNotNone(pv.add_package(job, 260000, 25, cfg))
        self.assertIsNone(pv.add_package(job, 300000, 30, cfg))                       # same piece
        self.assertIsNotNone(pv.add_package(job, 510000, 50, cfg))
        self.assertEqual(len(job["packages"]), 2)


class TestInstallmentPieces(V121):
    def setUp(self):
        super().setUp()
        self.folder = pv.rate_dir("book")
        os.makedirs(self.folder, exist_ok=True)
        self.handoff = os.path.join(self.folder, "HANDOFF.md")
        self.write_progress(10)

    def write_progress(self, n):
        with open(self.handoff, "w", encoding="utf-8") as f:
            f.write("PROGRESS: %d%%\nwhat is done\n" % n)

    def check(self, spent, tool="Read", target="x.md"):
        with patch_q(pv, "out") as out:
            refused = pv.piece_check("book", {"session_id": "s1", "tool_name": tool, "tool_input": {"file_path": target}},
                                     spent, 400000, pv.config())
        return refused, out

    def test_the_pieces_are_recorded_and_no_call_is_paused(self):
        self.assertFalse(self.check(50000)[0])              # PROGRESS 10% recorded
        self.assertFalse(self.check(60000)[0])              # unchanged: nothing new
        self.write_progress(30)
        refused, out = self.check(150000)
        self.assertFalse(refused)                           # never a paused call (19/10: they ate a 100k cap)
        out.assert_not_called()
        self.write_progress(55)
        self.check(260000)
        self.assertEqual([(p["wt"], p["progress"]) for p in pv.run_pieces("book", "s1")],
                         [(50000, 10), (150000, 30), (260000, 55)])

    def test_off(self):
        with mock.patch.dict(pv.DEFAULTS, {"piece_share": 0}):
            self.check(150000)
        self.assertEqual(pv.run_pieces("book", "s1"), [])

    def test_run_packages_use_the_pieces(self):
        runs = [{"wt": 400000, "seconds": 400, "progress": 40, "pieces": [{"wt": 100000, "progress": 10},
                                                                          {"wt": 300000, "progress": 30}]},
                {"wt": 400000, "seconds": 400, "progress": 80, "pieces": []}]
        packs = pv.run_packages(runs)
        self.assertEqual([(p["work"], p["progress"]) for p in packs], [(100000, 10), (300000, 30), (400000, 40), (800000, 80)])


if __name__ == "__main__":
    unittest.main()
