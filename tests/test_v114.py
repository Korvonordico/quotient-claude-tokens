"""1.1.4: a factor for each type of work, the new quote after the first million, the guided repair (fix), the
environment of each job (plugins, MCP servers, hooks) and the work done elsewhere meanwhile.
Run: python -m unittest discover tests"""

import io
import json
import os
import sys
import tempfile
from unittest import mock

import unittest

import test_hermes
from test_quotient import Base, usage, pv

update = test_hermes.update


def add_job(session, raw, work, started="2026-10-14T10:00:00+02:00", finished="2026-10-14T10:30:00+02:00", **more):
    row = {"session": session, "raw_estimate": raw, "actual": work, "chat": 0, "work": work, "started": started,
           "finished": finished, "choice": more.pop("choice", "good")}
    row.update(more)
    pv.append_jsonl(os.path.join(pv.home(), "jobs.jsonl"), row)
    return row


class Cli(Base):
    def cli(self, *argv):
        stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        with mock.patch.object(sys, "stdout", stdout):
            pv.main(list(argv))
            stdout.flush()
            return stdout.buffer.getvalue().decode("utf-8")


class TestTypeOfWork(Cli):
    def test_the_quote_line_carries_the_type(self):
        self.assertEqual(pv.parse_type("QUOTE: good=200k max=400k kind=code"), "code")
        self.assertEqual(pv.parse_type("**QUOTE:** kind=ricerca good=1M"), "research")
        self.assertEqual(pv.parse_type("PREVENTIVO: buono=1M tipo=libro"), "writing")
        self.assertEqual(pv.parse_type("QUOTE: good=1M kind=whatever"), "other")
        self.assertIsNone(pv.parse_type("QUOTE: good=1M max=2M"))
        # the type is not a level
        self.assertEqual(pv.parse_quote("QUOTE: good=200k max=400k kind=code"), {"good": 200000, "max": 400000})

    def test_a_type_learns_its_own_factor_from_three_jobs(self):
        cfg = pv.config()
        for i in range(6):
            add_job("c%d" % i, 100000, 100000)                       # untyped: 'other', x1
        for i in range(2):
            add_job("r%d" % i, 100000, 300000, type="research")      # research x3, only two
        learned = pv.learning(cfg, "chat", "research")
        self.assertFalse(learned["typed"])
        self.assertAlmostEqual(learned["factor"], 1.0)               # the general factor
        add_job("r2", 100000, 300000, type="research")
        learned = pv.learning(cfg, "chat", "research")
        self.assertTrue(learned["typed"])
        self.assertAlmostEqual(learned["factor"], 3.0)
        self.assertEqual(learned["type_jobs"], 3)
        self.assertAlmostEqual(pv.learning(cfg, "chat", "code")["factor"], 1.0)   # no code jobs: the general one
        self.assertEqual([(t, round(f, 2), n, own) for t, f, n, own in pv.type_factors(cfg)],
                         [("research", 3.0, 3, True), ("other", 1.0, 6, True)])
        report = self.run_hook(pv.report, {})
        self.assertIn("Factor by type of work (chat jobs): research x3.00 (3 job(s)); other x1.00 (6 job(s))", report)
        # the quote of a research job uses its factor, and says so
        text = pv.quote_table(cfg, {"good": 100000, "max": 200000}, lang="en", wtype="research")
        self.assertIn("| Good | 300,000 |", text)
        self.assertIn("of type 'research'", text)
        self.assertIn("QUOTE: good=100000 max=200000 kind=research", text)
        self.assertNotIn("Add the type of work", text)
        self.assertIn("Add the type of work", pv.quote_table(cfg, {"good": 100000}, lang="en"))

    def test_the_job_keeps_its_type_and_its_factor(self):
        for i in range(3):
            add_job("r%d" % i, 100000, 200000, type="code")
        self.t.user("refactor the parser")
        self.t.call("q", usage(output=100), texts=["QUOTE: good=250k max=500k kind=code"], tools=1)
        self.t.tool_result()
        self.t.call("w", usage(output=2000), texts=["CHOICE: good\nPACE: today", "done"])
        self.stop()
        job = pv.finished_jobs()[-1]
        self.assertEqual((job["type"], job["raw_estimate"]), ("code", 250000))
        self.assertAlmostEqual(job["factor_used"], 2.0)
        protocol = self.run_hook(pv.hook_session, {})
        self.assertIn("kind=<type>", protocol)
        self.assertIn("--type <type>", protocol)

    def test_installments_keep_their_type(self):
        task = os.path.join(self.dir, "task.md")
        with open(task, "w", encoding="utf-8") as f:
            f.write("check the history of the book")
        self.cli("rate", "new", "book", "--dir", self.dir, "--task-file", task, "--quote", "1000000", "--days", "2",
                 "--type", "research")
        self.assertEqual(pv.load_json(os.path.join(pv.rate_dir("book"), "job.json"), {})["type"], "research")


class TestRequote(Base):
    def test_due_only_past_the_first_million_and_on_a_big_change(self):
        cfg = pv.config()
        job = {"raw_estimate": 1000000, "factor_used": 1.0, "seconds": 600}
        self.assertIsNone(pv.requote_due(cfg, job, 500000, 10))           # before the first million
        self.assertIsNone(pv.requote_due(cfg, job, 1200000, None))        # no PROGRESS line
        rq = pv.requote_due(cfg, job, 1200000, 40)
        self.assertEqual((rq["rest_old"], rq["rest"], rq["total"]), (0, 1800000, 3000000))
        self.assertEqual(rq["seconds"], 900)                              # at the job's own pace: 600 s per 1.2M
        job2 = {"raw_estimate": 2000000, "factor_used": 1.0}
        self.assertIsNone(pv.requote_due(cfg, job2, 1100000, 55))         # 0.9M left either way
        self.assertIsNone(pv.requote_due(cfg, dict(job, requote=rq), 1200000, 40))   # once per job
        self.assertIn("PROGRESS: <n>%", pv.pace_note(1000000, 1.0, 1200000, None, cfg, None))
        self.assertNotIn("PROGRESS", pv.pace_note(1000000, 1.0, 1200000, None, cfg, 40))

    def test_the_new_quote_is_shown_once_and_kept_with_the_job(self):
        self.t.user("big job")
        self.t.call("q", usage(output=100), texts=["QUOTE: good=500k max=1M kind=code"], tools=1)
        self.t.tool_result()
        self.t.call("w", usage(output=2000), texts=["CHOICE: max\nPACE: today\nJOB: CONTINUES"])
        self.stop()
        self.t.user("go on")
        self.t.call("w2", usage(output=240000), texts=["part two\nPROGRESS: 30%\nJOB: CONTINUES"])   # 1.2M wt
        self.stop()
        state = pv.load_json(pv.session_path("s1"), {})
        self.assertEqual(state["job"]["requote"]["progress"], 30)
        first = self.run_hook(pv.hook_prompt, {"session_id": "s1", "transcript_path": self.t.path})
        self.assertIn("NEW QUOTE, from the job's own pace", first)
        self.assertIn("| At the pace so far |", first)
        self.assertIn("show the table above ONCE", first)
        second = self.run_hook(pv.hook_prompt, {"session_id": "s1", "transcript_path": self.t.path})
        self.assertNotIn("NEW QUOTE", second)
        self.t.user("finish it")
        self.t.call("w3", usage(output=1000), texts=["done"])
        self.stop()
        job = pv.finished_jobs()[-1]
        self.assertEqual(job["requote"]["total"], round(job["requote"]["at"] / 0.3))
        closed = self.run_hook(pv.hook_prompt, {"session_id": "s1", "transcript_path": self.t.path})
        self.assertIn("the new quote made after", closed)

    def test_installments_tell_the_new_numbers(self):
        cfg = pv.config()
        job = {"name": "book", "quote": 1000000, "factor_at_quote": 1.0, "overhead_at_quote": 0, "daily_cap": 500000,
               "status": "open"}
        runs = [{"wt": 500000, "chat": 0, "progress": 20, "started": "2026-10-15T03:00:00+02:00",
                 "finished": "2026-10-15T03:40:00+02:00", "cap": 500000}]
        rq = pv.rate_requote(cfg, job, runs)
        self.assertEqual((rq["rest"], rq["plan_rest"], rq["installments"], rq["total"]), (2000000, 500000, 4, 2500000))
        self.assertIsNone(pv.rate_requote(cfg, job, [dict(runs[0], progress=50)]))   # as planned
        runs[0]["requote"] = rq
        lines = "\n".join(pv.report_lines("book", job, runs, 0, self.dir))
        self.assertIn("NEW QUOTE from the installments' own pace: about 2.00M wt remain where the plan left 500k", lines)
        title, body = pv.installment_toast("book", job, runs, cfg)
        self.assertIn("what is left costs more", body)
        # the next installment compares with the new quote, not with the old plan
        job["requotes"] = [rq]
        self.assertIsNone(pv.rate_requote(cfg, job, runs + [{"wt": 500000, "chat": 0, "progress": 40}]))


class TestFix(Cli):
    def split_pair(self):
        a = add_job("s9", 300000, 50000, started="2026-10-15T10:00:00+02:00", finished="2026-10-15T10:10:00+02:00",
                    choice="max", check=1)
        b = add_job("s9", 300000, 400000, started="2026-10-15T10:15:00+02:00", finished="2026-10-15T11:00:00+02:00",
                    choice="max", check=1)
        return a, b

    def test_a_small_job_right_before_another_of_the_same_chat_looks_split(self):
        cfg = pv.config()
        a, b = self.split_pair()
        add_job("s8", 300000, 50000, started="2026-10-15T12:00:00+02:00", finished="2026-10-15T12:10:00+02:00")
        pairs = pv.split_jobs(cfg)
        self.assertEqual([(pv.job_key(x), pv.job_key(y)) for x, y, _ in pairs], [(pv.job_key(a), pv.job_key(b))])
        listed = self.cli("fix", "list")
        self.assertIn("fix merge %s %s" % (pv.job_key(a), pv.job_key(b)), listed)
        alert = pv.fix_alert()
        self.assertIn("A JOB LOOKS SPLIT", alert)
        self.assertIn("run it only after they say yes", alert)
        self.assertIsNone(pv.fix_alert())                                  # told once
        self.assertIn("To repair: 1", self.run_hook(pv.report, {}))

    def test_merge_keeps_copies_and_undo_puts_it_back(self):
        a, b = self.split_pair()
        before = pv.load_text(pv.jobs_path())
        said = self.cli("fix", "merge", pv.job_key(b), pv.job_key(a))     # any order: the earlier one first
        self.assertIn("Joined", said)
        self.assertIn("fix undo", said)
        jobs = pv.read_jsonl(pv.jobs_path())
        self.assertEqual(len(jobs), 1)
        self.assertEqual((jobs[0]["actual"], jobs[0]["work"], jobs[0]["raw_estimate"]), (450000, 450000, 300000))
        self.assertEqual(jobs[0]["merged_from"], [pv.job_key(a), pv.job_key(b)])
        self.assertEqual(jobs[0]["finished"], b["finished"])
        self.assertTrue(pv.check_key(jobs[0]).endswith(":merged"))       # checked against the week again
        self.assertEqual([r["fix"]["action"] for r in pv.read_jsonl(pv.excluded_path())], ["merge", "merge"])
        self.assertTrue(any(f.startswith("jobs-") for f in os.listdir(os.path.join(pv.home(), "fix"))))
        self.assertIn("Undone", self.cli("fix", "undo"))
        self.assertEqual(pv.load_text(pv.jobs_path()), before)
        self.assertEqual(pv.read_jsonl(pv.excluded_path()), [])
        self.assertIn("Nothing to undo", self.cli("fix", "undo"))

    def test_exclude_by_number_with_a_reason(self):
        add_job("c1", 100000, 100000)
        add_job("c2", 100000, 900000)
        said = self.cli("fix", "exclude", "2", "--why", "a piece counted apart")
        self.assertIn("out of the factor", said)
        self.assertEqual([j["session"] for j in pv.read_jsonl(pv.jobs_path())], ["c1"])
        out = pv.read_jsonl(pv.excluded_path())
        self.assertEqual((out[0]["session"], out[0]["fix"]["why"]), ("c2", "a piece counted apart"))
        self.assertIn("Jobs taken out of the factor or joined by `fix`: 1", self.run_hook(pv.report, {}))

    def test_a_measure_far_from_the_week_proposes_exclude(self):
        job = add_job("c1", 100000, 900000, check=1)
        row = {"key": pv.check_key(job), "label": "'good'", "end": pv.ts_epoch(job["finished"]), "wt": 900000,
               "points": 10, "per_point": 10000, "ratio": 9.0, "result": "warn"}
        pv.append_jsonl(pv.checks_path(), row)
        self.assertIn("fix exclude %s" % pv.job_key(job), pv.check_line(row))
        self.assertIn("fix exclude %s" % pv.job_key(job), self.cli("fix", "list"))


class TestEnvironment(Cli):
    def claude(self, plugins=None, hooks=None, mcp=None, project=None):
        base = os.path.join(self.dir, "claude")
        os.makedirs(base, exist_ok=True)
        pv.save_json(os.path.join(base, "settings.json"), {"enabledPlugins": plugins or {}, "hooks": hooks or {}})
        pv.save_json(os.path.join(base, ".claude.json"), {"mcpServers": mcp or {},
                                                          "projects": {os.getcwd(): {"mcpServers": project or {}}}})
        return base

    def test_names_only(self):
        base = self.claude({"rtk@tools": True, "off@tools": False},
                           {"Stop": [{"hooks": [{"type": "command",
                                                 "command": "python C:/x/token=SECRET/quotient.py hook-stop"}]}]},
                           {"codegraph": {"command": "npx", "env": {"API_KEY": "SECRET"}}}, {"local-db": {}})
        with mock.patch.dict(os.environ, {"QUOTIENT_CLAUDE_DIR": base}):
            snap = pv.env_snapshot()
        self.assertEqual(snap["plugins"], ["rtk@tools"])
        self.assertEqual(snap["hooks"], ["Stop:quotient.py"])
        self.assertEqual(snap["mcp"], ["codegraph", "local-db"])
        self.assertNotIn("SECRET", json.dumps(snap))

    def test_hermes_names_from_its_config(self):
        hermes = os.path.join(self.dir, "hermes")
        os.makedirs(hermes)
        with open(os.path.join(hermes, "config.yaml"), "w", encoding="utf-8") as f:
            f.write("plugins:\n  clone_timeout_seconds: 300\n\n# comment\n  enabled:\n    - web-guard\n  disabled: []\n"
                    "model:\n  default: \"claude-opus-5-5\"\nmcp_servers:\n  github:\n    command: npx\n    env:\n"
                    "      TOKEN: SECRET\nhooks:\n  pre_llm_call:\n    - command: E:/q/scripts/quotient.py hermes-hook\n"
                    "      timeout: 20\n  post_llm_call:\n    - command: E:/q/scripts/quotient.py hermes-hook\n")
        with mock.patch.dict(os.environ, {"QUOTIENT_HERMES": "1", "HERMES_HOME": hermes}):
            env = pv.hermes_env()
        self.assertEqual(env, {"hermes_plugins": ["web-guard"], "hermes_mcp": ["github"],
                               "hermes_hooks": ["post_llm_call:quotient.py", "pre_llm_call:quotient.py"]})

    def test_a_change_is_told_once_and_shown_before_and_after(self):
        base = self.claude({"a@x": True})
        with mock.patch.dict(os.environ, {"QUOTIENT_CLAUDE_DIR": base}):
            first = pv.record_env()
            self.assertEqual(first, pv.record_env())
            self.assertEqual(pv.read_jsonl(pv.env_changes_path()), [])
            self.claude({"a@x": True, "rtk@x": True})
            second = pv.record_env()
        self.assertNotEqual(first, second)
        change = pv.read_jsonl(pv.env_changes_path())[0]
        self.assertEqual((change["added"], change["removed"]), (["plugins rtk@x"], []))
        alert = pv.env_alert()
        self.assertIn("ENVIRONMENT CHANGED", alert)
        self.assertIn("added plugins rtk@x", alert)
        self.assertIsNone(pv.env_alert())

    def test_the_jobs_after_a_change_weigh_more(self):
        old = [{"raw_estimate": 100, "actual": 100, "work": 100, "finished": "2026-10-10T10:00:00+02:00"}] * 5
        new = [{"raw_estimate": 100, "actual": 400, "work": 400, "finished": "2026-10-14T10:00:00+02:00"}] * 3
        at = pv.ts_epoch("2026-10-12T10:00:00+02:00")
        self.assertAlmostEqual(pv.factor_from(old + new, 20), 1.0)
        self.assertAlmostEqual(pv.factor_from(old + new, 20, at, 2, 3), 4.0)
        self.assertAlmostEqual(pv.factor_from(old + new[:2], 20, at, 2, 3), 1.0)    # not enough after it yet
        for j in old + new:
            add_job("c", j["raw_estimate"], j["actual"], started=j["finished"], finished=j["finished"])
        pv.append_jsonl(pv.env_changes_path(), {"epoch": at, "from": "aaaa", "to": "bbbb", "added": ["plugins rtk@x"],
                                               "removed": []})
        self.assertAlmostEqual(pv.learning(pv.config())["factor"], 4.0)
        report = self.run_hook(pv.report, {})
        self.assertIn("Change of environment (plugins, MCP servers, hooks)", report)
        self.assertIn("chat jobs before: 5 job(s), factor x1.00", report)
        self.assertIn("chat jobs after: 3 job(s), factor x4.00", report)

    def test_what_other_sessions_spent_meanwhile(self):
        turns = os.path.join(pv.home(), "turns.jsonl")
        for ts, sid, wt in (("2026-10-15T10:05:00+02:00", "s2", 300000), ("2026-10-15T10:06:00+02:00", "s1", 999),
                            ("2026-10-15T12:00:00+02:00", "s2", 777)):
            pv.append_jsonl(turns, {"ts": ts, "session": sid, "wt": wt})
        begin, end = pv.ts_epoch("2026-10-15T10:00:00+02:00"), pv.ts_epoch("2026-10-15T11:00:00+02:00")
        self.assertEqual(pv.elsewhere_wt(begin, end, {"s1"}), 300000)
        note = pv.closed_note({"choice": "good", "raw_estimate": 100000, "actual": 200000, "work": 200000,
                               "elsewhere": 300000})
        self.assertIn("other sessions (other chats, installments, Hermes) spent 300k wt", note)
        self.assertNotIn("other sessions", pv.closed_note({"choice": "good", "raw_estimate": 1, "actual": 2, "work": 2,
                                                           "elsewhere": 10}))

    def test_a_closed_job_keeps_its_environment(self):
        base = self.claude({"a@x": True})
        with mock.patch.dict(os.environ, {"QUOTIENT_CLAUDE_DIR": base}):
            self.t.user("job")
            self.t.call("q", usage(output=100), texts=["QUOTE: good=100k kind=other"], tools=1)
            self.t.tool_result()
            self.t.call("w", usage(output=2000), texts=["CHOICE: good\nPACE: today", "done"])
            self.stop()
        job = pv.finished_jobs()[-1]
        self.assertEqual(job["env"], pv.read_jsonl(pv.env_path())[0]["sig"])
        self.assertEqual(job["elsewhere"], 0)


class TestHermes114(unittest.TestCase):
    # the helpers of test_hermes.HermesHooks, without running its tests a second time
    setUp, hook, jobs, state = (test_hermes.HermesHooks.setUp, test_hermes.HermesHooks.hook,
                                test_hermes.HermesHooks.jobs, test_hermes.HermesHooks.state)

    def test_type_progress_and_new_quote_in_hermes(self):
        self.hook("pre_llm_call")
        self.hook("post_llm_call", "QUOTE: good=500k max=1M kind=research\nCHOICE: max\nJOB: CONTINUES")
        self.assertEqual(self.state()["job"]["type"], "research")
        self.hook("pre_llm_call")
        update(self.h, "chat1", output_tokens=300100)          # +300k output = 1.5M wt of work
        self.hook("post_llm_call", "part two\nPROGRESS: 30%\nJOB: CONTINUES")
        self.assertEqual(self.state()["job"]["requote"]["progress"], 30)
        context = self.hook("pre_llm_call")["context"]
        self.assertIn("NEW QUOTE, from the job's own pace", context)
        self.assertNotIn("NEW QUOTE", self.hook("pre_llm_call")["context"])
        self.hook("post_llm_call", "Fatto.\nJOB: CLOSE")
        job = self.jobs()[-1]
        self.assertEqual(job["type"], "research")
        self.assertEqual(job["requote"]["progress"], 30)


def set_usage(d, sid, task, model="claude-opus-5-5", provider="anthropic", **counters):
    """A row of Hermes' session_model_usage (created if missing), or its counters changed."""
    import sqlite3
    con = sqlite3.connect(os.path.join(d, "state.db"))
    con.execute("create table if not exists session_model_usage (session_id text, model text, billing_provider text, "
                "task text, api_call_count int, input_tokens int, output_tokens int, cache_read_tokens int, "
                "cache_write_tokens int)")
    keys = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
    if con.execute("select 1 from session_model_usage where session_id = ? and task = ?", (sid, task)).fetchone():
        for k, v in counters.items():
            con.execute("update session_model_usage set %s = ? where session_id = ? and task = ?" % k, (v, sid, task))
    else:
        con.execute("insert into session_model_usage values (?,?,?,?,?,?,?,?,?)",
                    (sid, model, provider, task, 1) + tuple(counters.get(k, 0) for k in keys))
    con.commit()
    con.close()


class TestHermesBackground(unittest.TestCase):
    """3c (15/10/2026): Hermes keeps its calls in the background (background_review) out of the chats' totals, though
    they use the same limits; and its cache is the one its config says."""
    W = test_hermes.W

    def setUp(self):
        self.q = tempfile.mkdtemp()
        self.h = test_hermes.fake_hermes([
            ("chat1", "cli", "claude-opus-5-5", 1000.0, 2000.0, None, "work", "anthropic", 10, 100, 10000, 1000)])
        set_usage(self.h, "chat1", "", input_tokens=10, output_tokens=100, cache_read_tokens=10000, cache_write_tokens=1000)
        set_usage(self.h, "chat1", "background_review", output_tokens=100)
        set_usage(self.h, "chat1", "title", model="gpt-9", provider="openrouter", output_tokens=999)

    def test_the_background_is_counted_and_other_providers_are_not(self):
        row = test_hermes.hs.read_sessions(self.h)[0]
        self.assertEqual(row["aux"]["output_tokens"], 100)
        rows = test_hermes.hs.sync(self.q, self.W, home=self.h, now=5000.0)
        self.assertEqual(rows[0]["wt"], 2760 + 500)
        self.assertEqual(rows[0]["background"], 500)
        set_usage(self.h, "chat1", "background_review", output_tokens=300)
        rows = test_hermes.hs.sync(self.q, self.W, home=self.h, now=6000.0)
        self.assertEqual((rows[0]["wt"], rows[0]["background"], rows[0]["epoch"]), (1000, 1000, 6000.0))
        self.assertEqual(test_hermes.hs.summary(self.q, now=6000.0)["background"], 1500)

    def test_totals_that_already_hold_the_background_count_once(self):
        update(self.h, "chat1", output_tokens=200)              # the main task's 100 plus the background's 100
        self.assertEqual(test_hermes.hs.read_sessions(self.h)[0]["aux"]["output_tokens"], 0)
        self.assertEqual(test_hermes.hs.sync(self.q, self.W, home=self.h, now=5000.0)[0]["wt"], 2760 + 500)

    def test_after_the_update_the_past_background_does_not_land_now(self):
        test_hermes.hs.sync(self.q, self.W, home=self.h, now=5000.0)
        path = os.path.join(self.q, "hermes-state.json")
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
        state.pop("aux")                                        # a snapshot written before 1.1.4
        set_usage(self.h, "chat1", "background_review", output_tokens=5000)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f)
        self.assertEqual(test_hermes.hs.sync(self.q, self.W, home=self.h, now=6000.0), [])
        set_usage(self.h, "chat1", "background_review", output_tokens=5100)
        self.assertEqual(test_hermes.hs.sync(self.q, self.W, home=self.h, now=7000.0)[0]["background"], 500)

    def test_a_job_counts_the_background_from_its_start_only(self):
        import hermes_hooks as hh
        totals = {"input_tokens": 10, "output_tokens": 200, "cache_read_tokens": 0, "cache_write_tokens": 0,
                  "aux": {"input_tokens": 0, "output_tokens": 70, "cache_read_tokens": 0, "cache_write_tokens": 0}}
        old = {"input_tokens": 10, "output_tokens": 100, "cache_read_tokens": 0, "cache_write_tokens": 0}
        self.assertEqual(hh._grow(totals, old)["output_tokens"], 100)        # started before 1.1.4: no background
        new = dict(old, aux={"input_tokens": 0, "output_tokens": 50, "cache_read_tokens": 0, "cache_write_tokens": 0})
        self.assertEqual(hh._grow(totals, new)["output_tokens"], 120)

    def test_the_report_says_the_background_and_the_cache(self):
        import time
        now = time.time()
        h = test_hermes.fake_hermes([
            ("chat2", "cli", "claude-opus-5-5", now - 100, now - 50, None, "work", "anthropic", 10, 100, 10000, 1000)])
        set_usage(h, "chat2", "", input_tokens=10, output_tokens=100, cache_read_tokens=10000, cache_write_tokens=1000)
        set_usage(h, "chat2", "background_review", output_tokens=100)
        with mock.patch.dict(os.environ, {"QUOTIENT_HOME": self.q, "HERMES_HOME": h, "QUOTIENT_HERMES": "1"}):
            text = "\n".join(pv.hermes_lines(pv.config(), pv.TEXT["en"], "en"))
        self.assertIn("calls in the background", text)
        self.assertIn("500 wt", text)
        self.assertIn("5-minute", text)

    def test_the_cache_follows_hermes_config(self):
        hs = test_hermes.hs
        row = {"cache_write_tokens": 1000}
        self.assertEqual(hs.weigh_hermes(row, self.W, self.h), 1250)        # no config: 5 minutes
        h1 = tempfile.mkdtemp()
        with open(os.path.join(h1, "config.yaml"), "w", encoding="utf-8") as f:
            f.write("model: x\nprompt_caching:\n  enabled: true\n  cache_ttl: \"1h\" # long pauses\nother: 1\n")
        self.assertEqual(hs.cache_ttl(h1), "1h")
        self.assertEqual(hs.weigh_hermes(row, self.W, h1), 2000)
        h5 = tempfile.mkdtemp()
        with open(os.path.join(h5, "config.yaml"), "w", encoding="utf-8") as f:
            f.write("prompt_caching:\n  cache_ttl: auto\nx:\n  cache_ttl: \"1h\"\n")
        self.assertEqual(hs.cache_ttl(h5), "5m")
