"""A chat compressed in the middle of a job (Francesco, 16/10/2026)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import quotient as q  # noqa: E402
import hermes_hooks as h  # noqa: E402
import hermes_source as hs  # noqa: E402

W = {"input": 1, "cache_write_5m": 1.25, "cache_write_1h": 2, "cache_read": 0.1, "output": 5}
CFG = {"weights": W}


def sent(read, write=0, inp=0):
    return {"input_tokens": inp, "output_tokens": 0, "cache_read_tokens": read, "cache_write_tokens": write}


def call(n):
    return {"usage": {"cache_read_input_tokens": n, "cache_creation_input_tokens": 0, "input_tokens": 0}}


class CompressedChat(unittest.TestCase):
    def test_hermes_counts_less_after_a_compression(self):
        job = {"ctx": 200000, "start_calls": 0}
        chat = {"last": dict(sent(0), calls=0)}
        part, floor = h._chat_part(CFG, job, chat, sent(1050000), 5)      # 5 steps of about 210k
        self.assertEqual((round(part), floor), (100000, 200000))
        job.update(chat_done=part, ctx_floor=floor, acc_calls=5, acc_aside_calls=0)
        chat["last"] = dict(sent(1050000), calls=5)
        part, floor = h._chat_part(CFG, job, chat, sent(1850000), 15)     # compressed: 10 steps of about 80k
        self.assertEqual((round(part), round(floor)), (180000, 80000))

    def test_a_cold_cache_is_no_compression(self):
        job = {"ctx": 200000, "start_calls": 0}
        part, floor = h._chat_part(CFG, job, {"last": dict(sent(0), calls=0)}, sent(400000, write=650000), 5)
        self.assertEqual((round(part), floor), (100000, 200000))

    def test_replies_about_something_else_are_left_out(self):
        job = {"ctx": 200000, "start_calls": 0, "aside_calls": 3}
        part, _ = h._chat_part(CFG, job, {"last": dict(sent(0), calls=0)}, sent(2000000), 8)
        self.assertEqual(round(part), 100000)

    def test_hermes_close_keeps_the_smaller_size(self):
        seen = {}
        orig = q.close_job
        q.close_job = lambda row, cfg=None: seen.update(row)
        try:
            zero = {k: 0 for k in hs.COUNTERS}
            job = {"session": "H1", "started": "x", "options": {"max": 1000}, "choice": "max", "raw_estimate": 1000,
                   "factor": 1.0, "start": dict(zero), "start_calls": 0, "ctx": 200000, "begin": 1.0,
                   "chat_done": 100000.0, "ctx_floor": 200000, "acc_calls": 5, "acc_aside_calls": 0}
            chat = {"job": job, "last": dict(sent(1050000), calls=5)}
            h._close(q, dict(q.config(), claude_runs=0), chat, sent(1850000), 15, "close")
        finally:
            q.close_job = orig
        self.assertEqual((round(seen["chat"]), seen["ctx_floor"]), (180000, 80000))

    def test_claude_code_after_a_compaction(self):
        calls = [call(100000), call(110000), call(30000), call(50000), call(120000)]
        self.assertEqual(q.chat_part(calls, 0, 100000, W), round((100000 * 2 + 30000 * 3) * 0.1))
        self.assertEqual(q.chat_part(calls[:2], 0, 100000, W), 20000)    # no compaction: as before

    def test_fix_works_an_old_hermes_job_out_again(self):
        job = {"session": "hermes:S", "begin": 1000.0, "finished": "2026-10-16T01:00:00+02:00", "ctx": 200000,
               "calls": 15, "actual": 400000, "chat": 300000, "work": 100000, "raw_estimate": 300000}
        end = q.ts_epoch(job["finished"])
        rows = [dict(sent(1000000), session="S", epoch=end - 3000),       # 5 steps before the compression
                dict(sent(800000), session="S", epoch=end - 60),          # 10 steps after it
                dict(sent(500000), session="S", epoch=end + 940),         # 60 s of its 1000 inside the job
                dict(sent(900000), session="other", epoch=end - 60)]
        orig = hs.read_log
        hs.read_log = lambda home: rows
        try:
            chat, how = q.chat_again(CFG, job, (end - 2500, end - 2000))
        finally:
            hs.read_log = orig
        self.assertEqual((round(chat), how), (183000, "hermes-log"))
        new = q.rechat(job, chat, how)
        self.assertEqual((new["chat"], new["work"], new["ratio"]), (183000, 217000, 0.7233))
        self.assertEqual(new["chat_fixed"]["chat"], 300000)


if __name__ == "__main__":
    unittest.main()
