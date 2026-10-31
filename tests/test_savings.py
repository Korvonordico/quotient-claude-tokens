"""Improvements 2, 5, 7, 9: the tips for saving tokens: long chat, new chat, apart, where the spending goes, the cache,
in order of what they save, each one that can be put off or dropped (Francesco, 17/10 and 30/10/2026). Never shorter
replies; a new chat only from 500,000 tokens.
Run: python -m unittest discover tests"""

import io
import json
import os
import sys
import time
from unittest import mock

import unittest

from test_v116 import Cli, pv

import savings
import hermes_hooks as hh
import hermes_source as hs


def call(key, read=0, write=0, plain=10, output=100, tools=(), at="2026-10-31T03:00:00+01:00", hour=False):
    usage = {"input_tokens": plain, "output_tokens": output, "cache_read_input_tokens": read,
             "cache_creation_input_tokens": write}
    if hour:
        usage["cache_creation"] = {"ephemeral_1h_input_tokens": write, "ephemeral_5m_input_tokens": 0}
    return {"type": "assistant", "requestId": key, "timestamp": at,
            "message": {"usage": usage, "content": [{"type": "tool_use", "id": t[0], "name": t[1], "input": t[2]}
                                                    for t in tools]}}


def result(tool_id, content):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tool_id, "content": content}]}}


class Tips(Cli):
    def on(self, level=2, **more):
        pv.store(("tips", "level"), level)
        for k, v in more.items():
            pv.store(("tips", k), v)
        return pv.config()

    def usage(self, **more):
        base = {"groups": {}, "total": 0.0, "calls": 0, "read": 0, "written": 0, "plain": 0, "pauses": 0, "changed": 0}
        base.update(more)
        return base

    def line(self, cfg, ctx=1000, fresh=50000, job=False, usage=None, sid="chat", now=None):
        return savings.line(pv, cfg, sid, ctx, fresh, job, lambda: usage or self.usage(), now=now)


class TestOff(Tips):
    def test_off_by_default_and_nothing_is_read(self):
        cfg = pv.config()
        self.assertEqual(cfg["tips"]["level"], 0)
        self.assertEqual(savings.line(pv, cfg, "c", 9000000, 50000, True, lambda: self.fail("read")), "")
        self.assertEqual(pv.saving_line(cfg, "c", 9000000, 50000, True, lambda: self.fail("read")), "")
        self.assertFalse(os.path.exists(os.path.join(pv.home(), "tips.json")))

    def test_a_broken_reading_never_stops_a_message(self):
        cfg = self.on()

        def broken():
            raise ValueError("no")
        with mock.patch.object(sys, "stderr", io.StringIO()):
            self.assertEqual(pv.saving_line(cfg, "c", 900000, 50000, True, broken), "")


class TestLongChat(Tips):
    def test_a_new_chat_only_from_500000_tokens(self):
        cfg = self.on()
        self.assertEqual(cfg["tips"]["new_chat_tokens"], 500000)
        self.assertEqual(self.line(cfg, ctx=499999), "")
        text = self.line(cfg, ctx=500000)
        self.assertIn("[new-chat]", text)
        self.assertIn("a new chat", text)
        self.assertIn("450k", text.replace(",", "").replace("~", ""))     # 450,000 x 0.1 x 10 steps

    def test_a_summary_from_a_lower_size_does_not_propose_a_new_chat(self):
        cfg = self.on(long_chat_tokens=200000)
        text = self.line(cfg, ctx=300000)
        self.assertIn("[long-chat]", text)
        self.assertNotIn("new chat", text)

    def test_told_again_only_as_it_grows_and_at_level_1_once(self):
        cfg = self.on()
        self.assertIn("new-chat", self.line(cfg, ctx=500000))
        self.assertEqual(self.line(cfg, ctx=550000), "")
        self.assertIn("new-chat", self.line(cfg, ctx=600000))
        self.assertEqual(self.line(cfg, ctx=650000), "")
        cfg = self.on(level=1)
        self.assertIn("new-chat", self.line(cfg, ctx=500000, sid="other"))
        self.assertEqual(self.line(cfg, ctx=900000, sid="other"), "")

    def test_each_chat_has_its_own(self):
        cfg = self.on()
        self.assertIn("new-chat", self.line(cfg, ctx=500000, sid="a"))
        self.assertIn("new-chat", self.line(cfg, ctx=500000, sid="b"))

    def test_apart_needs_an_open_job_and_counts_the_start(self):
        cfg = self.on()
        self.assertEqual(self.line(cfg, ctx=300000, job=False), "")
        with mock.patch.object(pv, "installment_start_cost", return_value=100000):
            self.assertIn("[apart]", self.line(cfg, ctx=300000, job=True))
            # re-reading saved (10 steps x 0.1 x 150k = 150k) still above the start of 100k; below it, no tip
            tips = savings.chat_tips(pv, cfg, 200000, 150000, True, None)
        self.assertEqual(tips, [])

    def test_with_tips_on_the_quote_offers_no_new_chat_under_the_size(self):
        cfg = pv.config()
        self.assertTrue(pv.new_chat_allowed(cfg, 1000))
        cfg = self.on()
        self.assertFalse(pv.new_chat_allowed(cfg, 499999))
        self.assertTrue(pv.new_chat_allowed(cfg, 500000))
        self.assertNotIn("new chat", pv.chat_hint(cfg, 300000, 10000))
        self.assertIn("new chat", pv.chat_hint(pv.config(), 600000, 10000))


class TestTools(Tips):
    def entries(self):
        return [
            call("a", write=1000, tools=[("t1", "Bash", {"command": "x" * 350}), ("t2", "mcp__computer-use__screenshot", {})]),
            result("t1", "y" * 35000),
            result("t2", [{"type": "image", "source": {}}]),
            call("b", read=1000, write=10000),
            call("c", read=11000, write=0),
        ]

    def test_each_tool_costs_what_it_brought_in(self):
        cfg = self.on()
        usage = savings.claude_usage(pv, self.entries(), cfg)
        w = cfg["weights"]
        terminal = 100 * w["output"] + 100 * (w["cache_write_5m"] + w["cache_read"]) + \
            10000 * (w["cache_write_5m"] + w["cache_read"])
        self.assertAlmostEqual(usage["groups"]["terminal"], terminal, delta=50)
        self.assertAlmostEqual(usage["groups"]["screenshots"], 1500 * (w["cache_write_5m"] + w["cache_read"]), delta=20)
        self.assertEqual(usage["calls"], 3)
        self.assertEqual(usage["read"], 12000)
        self.assertEqual(usage["written"], 11000)
        self.assertEqual(usage["plain"], 30)

    def test_a_compaction_stops_the_re_reading(self):
        cfg = self.on()
        whole = savings.claude_usage(pv, self.entries(), cfg)["groups"]["terminal"]
        entries = self.entries()
        entries.insert(4, {"type": "system", "subtype": "compact_boundary"})
        cut = savings.claude_usage(pv, entries, cfg)["groups"]["terminal"]
        self.assertLess(cut, whole)

    def test_groups_by_name(self):
        for name, group in (("Bash", "terminal"), ("PowerShell", "terminal"), ("terminal", "terminal"),
                            ("Read", "files read"), ("Grep", "files read"), ("read_file", "files read"),
                            ("Write", "files written"), ("Edit", "files written"), ("patch", "files written"),
                            ("WebSearch", "web"), ("WebFetch", "web"), ("web_extract", "web"),
                            ("mcp__Claude_Browser__read_page", "browser"), ("browser_navigate", "browser"),
                            ("browser_vision", "screenshots"), ("Agent", "helpers"), ("delegate_task", "helpers"),
                            ("mcp__melty__whoami", "other"), (None, "other")):
            self.assertEqual(savings.group_of(name), group, name)
        self.assertEqual(savings.group_of("Bash", image=True), "screenshots")

    def test_a_tip_above_the_share_only_with_enough_spent(self):
        cfg = self.on()
        usage = self.usage(groups={"screenshots": 150000.0, "terminal": 10000.0, "other": 340000.0}, total=500000.0)
        text = self.line(cfg, usage=usage)
        self.assertIn("[tools-screenshots]", text)
        self.assertIn("screen photos cost about 30%", text)
        self.assertNotIn("terminal", text)
        self.assertNotIn("other", text)
        small = self.usage(groups={"screenshots": 300.0}, total=1000.0)
        self.assertEqual(savings.chat_tips(pv, cfg, 0, 0, False, small), [])

    def test_a_share_is_never_above_all(self):
        cfg = self.on()
        tips = savings.chat_tips(pv, cfg, 0, 0, False, self.usage(groups={"terminal": 900000.0}, total=500000.0))
        self.assertIn("about 100%", tips[0]["en"])


class TestCache(Tips):
    def test_low_with_the_reason_of_the_pauses(self):
        cfg = self.on()
        usage = self.usage(read=500, written=500, plain=0, calls=20, pauses=3)
        tips = savings.chat_tips(pv, cfg, 0, 0, False, usage)
        self.assertEqual(tips[0]["id"], "cache")
        self.assertIn("only 50%", tips[0]["en"])
        self.assertIn("3 pauses", tips[0]["en"])
        self.assertIn("3 pause", tips[0]["it"])

    def test_the_other_reasons(self):
        cfg = self.on()
        usage = self.usage(read=500, written=500, calls=20, changed=2)
        self.assertIn("changed 2 times", savings.chat_tips(pv, cfg, 0, 0, False, usage)[0]["en"])
        usage = self.usage(read=500, written=500, calls=20)
        self.assertIn("new text", savings.chat_tips(pv, cfg, 0, 0, False, usage)[0]["en"])

    def test_not_with_a_good_share_or_few_steps(self):
        cfg = self.on()
        self.assertEqual(savings.chat_tips(pv, cfg, 0, 0, False, self.usage(read=900, written=100, calls=20)), [])
        self.assertEqual(savings.chat_tips(pv, cfg, 0, 0, False, self.usage(read=100, written=900, calls=9)), [])

    def test_a_pause_makes_a_cold_call_and_a_changed_start_another(self):
        cfg = self.on(cold_min_tokens=100)
        entries = [call("a", write=5000, at="2026-10-31T03:00:00+00:00"),
                   call("b", read=5000, write=100, at="2026-10-31T03:01:00+00:00"),
                   call("c", write=5200, at="2026-10-31T03:30:00+00:00"),         # 29 minutes: the cache is gone
                   call("d", write=5300, at="2026-10-31T03:30:30+00:00")]         # 30 seconds: something changed
        usage = savings.claude_usage(pv, entries, cfg)
        self.assertEqual((usage["pauses"], usage["changed"]), (1, 1))

    def test_the_one_hour_cache_has_a_longer_life(self):
        cfg = self.on(cold_min_tokens=100)
        entries = [call("a", write=5000, at="2026-10-31T03:00:00+00:00", hour=True),
                   call("c", write=5200, at="2026-10-31T03:30:00+00:00", hour=True)]
        usage = savings.claude_usage(pv, entries, cfg)
        self.assertEqual((usage["pauses"], usage["changed"]), (0, 1))

    def test_a_compaction_is_not_a_cold_cache(self):
        cfg = self.on(cold_min_tokens=100)
        entries = [call("a", read=90000, write=100), call("b", write=9000)]
        usage = savings.claude_usage(pv, entries, cfg)
        self.assertEqual((usage["pauses"], usage["changed"]), (0, 0))


class TestOrderAndChoices(Tips):
    def usage_big(self):
        return self.usage(groups={"terminal": 1000000.0}, total=2000000.0, read=100, written=900, plain=0, calls=50)

    def test_most_useful_first_and_at_level_1_only_that(self):
        cfg = self.on()
        tips = savings.chat_tips(pv, cfg, 600000, 50000, True, self.usage_big())
        savings_wt = [t["saving"] for t in tips]
        self.assertEqual(savings_wt, sorted(savings_wt, reverse=True))
        self.assertGreaterEqual(len(tips), 3)
        text = self.line(cfg, ctx=600000, job=True, usage=self.usage_big())
        self.assertLess(text.index("[" + tips[0]["id"] + "]"), text.index("[" + tips[1]["id"] + "]"))
        cfg = self.on(level=1)
        text = self.line(cfg, ctx=600000, job=True, usage=self.usage_big(), sid="one")
        self.assertIn("[" + tips[0]["id"] + "]", text)
        self.assertNotIn("[" + tips[1]["id"] + "]", text)

    def test_at_most_as_many_as_the_setting(self):
        cfg = self.on(most=2)
        text = self.line(cfg, ctx=600000, job=True, usage=self.usage_big())
        self.assertEqual(text.count("] "), 2)

    def test_put_off_and_back(self):
        cfg = self.on()
        self.cli("tips", "later", "new-chat", "--days", "2")
        now = time.time()
        self.assertEqual(self.line(cfg, ctx=500000, now=now), "")
        self.assertIn("rimandato" if cfg["lang"] == "it" else "put off", self.cli("tips"))
        self.assertIn("new-chat", self.line(cfg, ctx=500000, now=now + 3 * 86400))    # the date has passed

    def test_dropped_stays_saved_until_taken_back(self):
        cfg = self.on()
        self.cli("tips", "drop", "new-chat")
        self.assertEqual(self.line(cfg, ctx=500000, now=time.time() + 400 * 86400), "")
        saved = pv.load_json(os.path.join(pv.home(), "tips.json"), {})
        self.assertEqual(saved["hidden"]["new-chat"], {"until": None})
        self.cli("tips", "back", "new-chat")
        self.assertIn("new-chat", self.line(cfg, ctx=500000))

    def test_the_list_says_it_is_off_and_shows_the_tips(self):
        self.assertIn("tips.level", self.cli("tips"))
        cfg = self.on()
        self.line(cfg, ctx=500000)
        text = self.cli("tips")
        self.assertIn("1. [new-chat]", text)
        self.assertNotIn("tips.level", text)

    def test_a_choice_needs_a_tip(self):
        with self.assertRaises(SystemExit):
            self.cli("tips", "drop")

    def test_the_logs_are_read_only_every_so_often(self):
        cfg = self.on()
        reads = []

        def usage_of():
            reads.append(1)
            return self.usage()
        now = time.time()
        savings.line(pv, cfg, "c", 0, 0, False, usage_of, now=now)
        savings.line(pv, cfg, "c", 0, 0, False, usage_of, now=now + 10)
        self.assertEqual(len(reads), 1)
        savings.line(pv, cfg, "c", 0, 0, False, usage_of, now=now + 601)
        self.assertEqual(len(reads), 2)

    def test_only_the_last_chats_are_remembered(self):
        cfg = self.on()
        now = time.time()
        for n in range(savings.KEEP_CHATS + 5):
            self.line(cfg, sid="chat%d" % n, now=now + n)
        saved = pv.load_json(os.path.join(pv.home(), "tips.json"), {})
        self.assertEqual(len(saved["chats"]), savings.KEEP_CHATS)
        self.assertIn("chat%d" % (savings.KEEP_CHATS + 4), saved["chats"])

    def test_no_tip_ever_asks_for_shorter_replies(self):
        texts = [t for pair in savings.TEXT.values() for t in pair]
        texts += [t for group in savings.GROUP_TEXT.values() for pair in group for t in pair]
        texts += [t for pair in savings.REASONS.values() for t in pair]
        joined = " ".join(texts).lower()
        for word in ("shorter", "short repl", "brief", "più corte", "piu' corte", "risposte corte", "accorcia"):
            self.assertNotIn(word, joined)


class TestInstallment(Tips):
    def test_the_numbers_of_a_run_and_its_line(self):
        cfg = self.on()
        entries = [call("a", write=1000, tools=[("t1", "Bash", {"c": "x"})]), result("t1", "y" * 35000),
                   call("b", read=1000, write=10000), call("c", read=11000)]
        numbers = savings.run_numbers(pv, entries, cfg)
        self.assertIn("terminal", numbers["tools"])
        self.assertEqual(numbers["cache_percent"], round(100.0 * 12000 / 23030, 1))
        run = dict(numbers, wt=numbers["tools"]["terminal"] * 2)
        self.assertIn("terminal 50%", savings.run_line(pv, cfg, run, "en"))
        self.assertIn("il terminale 50%", savings.run_line(pv, cfg, run, "it"))
        self.assertIn("Only 52% of what it sent", savings.run_line(pv, cfg, run, "en"))

    def test_no_line_when_off_or_not_measured(self):
        cfg = pv.config()
        self.assertEqual(savings.run_line(pv, cfg, {"tools": {"terminal": 5}, "wt": 10}, "en"), "")
        cfg = self.on()
        self.assertEqual(savings.run_line(pv, cfg, {"wt": 10}, "en"), "")


class TestHermes(Tips):
    def test_tools_from_the_store(self):
        cfg = self.on()
        rows = [(100.0, "user", None, 5, [], False),
                (101.0, "assistant", None, 0, [("terminal", 350)], False),
                (102.0, "tool", "terminal", 35000, [], False),
                (103.0, "assistant", None, 50, [], False),
                (9000.0, "user", None, 5, [], False),
                (9001.0, "assistant", None, 50, [], False)]
        totals = {"input_tokens": 10, "output_tokens": 100, "cache_read_tokens": 500, "cache_write_tokens": 500}
        with mock.patch.object(hs, "tool_rows", return_value=rows), mock.patch.object(hs, "cache_ttl", return_value="5m"):
            usage = savings.hermes_usage(pv, hs, "s", totals, 3, cfg)
        w = cfg["weights"]
        self.assertAlmostEqual(usage["groups"]["terminal"],
                               100 * w["output"] + 100 * (w["cache_write_5m"] + w["cache_read"]) +
                               10000 * (w["cache_write_5m"] + w["cache_read"]), delta=20)
        self.assertEqual((usage["calls"], usage["read"], usage["written"], usage["pauses"]), (3, 500, 500, 1))

    def test_the_store_read_gives_sizes_and_names(self):
        import sqlite3
        home = os.path.join(self.dir, "hermes")
        os.makedirs(home)
        con = sqlite3.connect(hs.db_path(home))
        con.execute("create table messages (id integer primary key, session_id, role, timestamp, content, tool_name, tool_calls)")
        calls = json.dumps([{"function": {"name": "terminal", "arguments": "abcd"}}])
        con.executemany("insert into messages (session_id, role, timestamp, content, tool_name, tool_calls) values (?,?,?,?,?,?)",
                        [("s", "assistant", 1.0, "hello", None, calls), ("s", "tool", 2.0, "secret", "terminal", None),
                         ("s", "user", 3.0, "[CONTEXT COMPACTION] x", None, None), ("z", "user", 4.0, "other", None, None)])
        con.commit()
        con.close()
        rows = hs.tool_rows("s", home)
        self.assertEqual(rows[0][1:5], ("assistant", None, 5, [("terminal", 4)]))
        self.assertEqual(rows[1][1:4], ("tool", "terminal", 6))
        self.assertTrue(rows[2][5])
        self.assertEqual(len(rows), 3)
        self.assertNotIn("secret", repr(rows))     # sizes, never the text
        self.assertIsNone(hs.tool_rows("s", os.path.join(self.dir, "none")))


class TestDocs(Tips):
    def test_the_command_is_listed(self):
        self.assertIn("tips [list", self.cli("commands"))


if __name__ == "__main__":
    unittest.main()
