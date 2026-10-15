"""hermes branch: the Claude Code runs a Hermes chat starts are counted in its jobs (Francesco, 16/10/2026)."""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import quotient as q  # noqa: E402
import hermes_hooks as h  # noqa: E402

W = {"input": 1, "cache_write_5m": 1.25, "cache_write_1h": 2, "cache_read": 0.1, "output": 5}
ENV_KEYS = ("QUOTIENT_HOME", "HERMES_SESSION_ID", "QUOTIENT_JOB")
FAR = q.ts_epoch("2030-01-01T00:00:00Z")


def call(rid, ts, out, model="claude-haiku-4-5", entry="sdk-cli"):
    return {"type": "assistant", "requestId": rid, "timestamp": ts, "entrypoint": entry,
            "message": {"id": rid, "model": model, "usage": {"input_tokens": 10, "cache_read_input_tokens": 1000,
                                                              "cache_creation_input_tokens": 100,
                                                              "output_tokens": out}}}


def prompt(text, entry="sdk-cli"):
    return {"type": "user", "timestamp": "2026-10-16T10:00:00Z", "entrypoint": entry,
            "message": {"role": "user", "content": text}}


class ClaudeRuns(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = {k: os.environ.get(k) for k in ENV_KEYS}
        os.environ["QUOTIENT_HOME"] = os.path.join(self.tmp, "q")
        os.makedirs(os.environ["QUOTIENT_HOME"])
        os.environ.pop("HERMES_SESSION_ID", None)
        os.environ.pop("QUOTIENT_JOB", None)
        self.root = os.path.join(self.tmp, "projects")
        self.cfg = {"claude_runs": 1, "claude_runs_marker": "", "weights": W}

    def tearDown(self):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def transcript(self, sid, entries):
        folder = os.path.join(self.root, "C--work")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, sid + ".jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        return path

    def link(self, sid, path, hermes=None, rate=None):
        if hermes:
            os.environ["HERMES_SESSION_ID"] = hermes
        if rate:
            os.environ["QUOTIENT_JOB"] = rate
        q.record_claude_link({"session_id": sid, "transcript_path": path, "source": "startup"}, self.cfg)
        os.environ.pop("HERMES_SESSION_ID", None)
        os.environ.pop("QUOTIENT_JOB", None)

    def test_link_records(self):
        self.link("a", "pa", hermes="H1")
        self.link("b", "pb", rate="libro")
        self.link("c", "pc")
        q.record_claude_link({"session_id": "d"}, {"claude_runs": 0})
        links = q.claude_links()
        self.assertEqual(links["a"]["hermes"], "H1")
        self.assertEqual(links["b"]["rate"], "libro")
        self.assertIsNone(links["c"].get("hermes"))
        self.assertNotIn("d", links)

    def test_resume_keeps_the_link(self):
        self.link("a", "pa", hermes="H1")
        self.link("a", "pa")
        self.assertEqual(q.claude_links()["a"]["hermes"], "H1")

    def test_linked_run_counted_in_its_window_once(self):
        lo, hi = q.ts_epoch("2026-10-16T10:00:00Z"), q.ts_epoch("2026-10-16T11:00:00Z")
        inside, opus = call("r1", "2026-10-16T10:05:00Z", 50), call("r3", "2026-10-16T10:30:00Z", 20, "claude-opus-5")
        path = self.transcript("s1", [prompt("[AUTO] go"), inside, dict(inside),
                                      call("r2", "2026-10-16T09:00:00Z", 999), opus])
        self.link("s1", path, hermes="H1")
        runs = q.claude_runs_of("H1", lo, hi, self.cfg, root=self.root)
        expected = round(q.weigh(inside["message"]["usage"], W) + q.weigh(opus["message"]["usage"], W))
        self.assertEqual(runs["wt"], expected)
        self.assertEqual(set(runs["families"]), {"haiku", "opus"})
        self.assertEqual([r["by"] for r in runs["runs"]], ["link"])

    def test_installments_and_other_chats_left_out(self):
        p1 = self.transcript("s1", [prompt("x"), call("r1", "2026-10-16T10:05:00Z", 50)])
        p2 = self.transcript("s2", [prompt("x"), call("r2", "2026-10-16T10:05:00Z", 50)])
        self.link("s1", p1, hermes="H1", rate="libro")
        self.link("s2", p2, hermes="H2")
        self.assertEqual(q.claude_runs_of("H1", 0, FAR, self.cfg, root=self.root)["wt"], 0)

    def test_marker_only_for_runs_never_seen(self):
        self.transcript("auto", [prompt("[AUTO] lavoro"), call("r1", "2026-10-16T10:05:00Z", 50)])
        self.transcript("rata", [prompt("[AUTO] " + q.RATE_SIGN + "."), call("r2", "2026-10-16T10:05:00Z", 50)])
        self.transcript("mano", [prompt("[AUTO] chat", entry="cli"), call("r3", "2026-10-16T10:05:00Z", 50, entry="cli")])
        seen = self.transcript("vista", [prompt("[AUTO] pianificata"), call("r4", "2026-10-16T10:05:00Z", 50)])
        self.link("vista", seen)   # seen at its start and not from Hermes: a scheduled task
        self.assertEqual(q.claude_runs_of("H1", 0, FAR, self.cfg, root=self.root)["wt"], 0)   # marker off
        runs = q.claude_runs_of("H1", 0, FAR, dict(self.cfg, claude_runs_marker="[AUTO]"), root=self.root)
        self.assertEqual([(r["session"], r["by"]) for r in runs["runs"]], [("auto", "marker")])

    def test_speed_filter_looks_at_the_chat_only(self):
        job = {"work": 3000000, "claude": 2500000, "seconds": 900, "raw_estimate": 2000000}
        self.assertFalse(q.too_fast(job, {"learn_max_speed": 3000}))
        self.assertTrue(q.too_fast(dict(job, claude=0), {"learn_max_speed": 3000}))

    def test_note_says_of_which(self):
        row = {"choice": "max", "raw_estimate": 1000, "factor_used": 1.0, "actual": 5000, "work": 4000, "chat": 1000,
               "claude": 1500, "claude_runs": 2}
        self.assertIn("2 Claude Code runs it started", q.closed_note(row))
        self.assertNotIn("Claude Code", q.closed_note(dict(row, claude=0)))

    def test_protocol_asks_to_quote_them(self):
        self.assertIn("put them in the estimate", q.protocol(dict(q.config(), claude_runs=1), 1.0))
        self.assertNotIn("put them in the estimate", q.protocol(q.config(), 1.0))

    def test_hermes_close_adds_them(self):
        seen = {}
        orig = q.claude_runs_of, q.close_job
        q.claude_runs_of = lambda sid, lo, hi, cfg: {"wt": 7000, "families": {"haiku": 7000}, "runs": [{}, {}]}
        q.close_job = lambda row, cfg=None: seen.update(row)
        try:
            zero = {k: 0 for k in h.hs.COUNTERS}
            chat = {"job": {"session": "H1", "started": "x", "options": {"max": 1000}, "choice": "max",
                            "raw_estimate": 1000, "factor": 1.0, "start": dict(zero), "start_calls": 0, "ctx": 0,
                            "begin": 1.0}}
            h._close(q, dict(q.config(), claude_runs=1), chat, dict(zero), 0, "close")
        finally:
            q.claude_runs_of, q.close_job = orig
        self.assertEqual((seen["claude"], seen["actual"], seen["claude_runs"]), (7000, 7000, 2))
        self.assertEqual(seen["families"].get("haiku"), 7000)


if __name__ == "__main__":
    unittest.main()
