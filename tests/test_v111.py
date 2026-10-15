"""1.1.1: the part of the cap kept for saving, the measures set against the week, the messages in between (ASIDE) and
the job done apart, now. Run: python -m unittest discover tests"""

import json
import os
from unittest import mock

from test_quotient import Base, usage, pv


def tool_rows(names, refused=None, request="h"):
    """A helper's transcript: one call per tool, and the tool results (one refused by the cap, if given)."""
    rows = []
    for i, name in enumerate(names):
        rows.append({"type": "assistant", "requestId": "%s%d" % (request, i), "timestamp": "2026-10-15T03:0%d:00Z" % i,
                     "message": {"id": "m%s%d" % (request, i), "usage": usage(output=10),
                                 "content": [{"type": "tool_use", "id": "%s-t%d" % (request, i), "name": name,
                                              "input": {}}]}})
        said = refused if refused and i == len(names) - 1 else "ok"
        rows.append({"type": "user", "timestamp": "2026-10-15T03:0%d:30Z" % i, "message": {"content": [
            {"type": "tool_result", "tool_use_id": "%s-t%d" % (request, i), "content": said, "is_error": said != "ok"}]}})
    return rows


def write_rows(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


class InstallmentBase(Base):
    def new_job(self, name="book", **kw):
        args = mock.Mock(dir=self.dir, task="write the book", task_file=None, days=3, daily=100000, quote=None,
                         model=None, after="nothing", template=None)
        args.name = name
        for k, v in kw.items():
            setattr(args, k, v)
        self.run_hook(lambda: pv.rate_new(args), {})
        return pv.load_json(os.path.join(pv.rate_dir(name), "job.json"), None)

    def pretool(self, tool, path=None, **given):
        with mock.patch.dict(os.environ, {"QUOTIENT_JOB": "book"}):
            said = self.run_hook(pv.hook_pretool, {"transcript_path": path or self.t.path, "tool_name": tool,
                                                   "tool_input": given})
        return json.loads(said)["hookSpecificOutput"]["permissionDecisionReason"] if said else ""


class TestCapKeptForSaving(InstallmentBase):
    """15/10/2026: at the cap the hook refused everything, to the helpers too, and about 120 web searches were lost."""

    def calls(self, n, output=5200):    # 26k wt each; the closing steps are kept at most 40% of the cap (40k)
        for i in range(n):
            self.t.call("c%d" % (self.t.n + i), usage(output=output), tools=1)
            self.t.tool_result()

    def test_the_last_part_of_the_cap_lets_only_saving_through(self):
        self.new_job()
        handoff = os.path.join(pv.rate_dir("book"), "HANDOFF.md")
        self.t.user("installment")
        self.calls(2)           # 52k spent + 40k for the closing steps = 92k: the last 8% of a 100k cap
        for tool, given in (("Bash", {"command": "ls"}), ("WebSearch", {"query": "x"}), ("Agent", {"prompt": "x"}),
                            ("Read", {"file_path": os.path.join(self.dir, "x.md")}),
                            ("Bash", {"command": "cat > a.md <<'EOF'\nfound\nEOF\nrm -rf x"})):
            said = self.pretool(tool, **given)
            self.assertIn("nearly used up", said, tool)
            self.assertIn("Save NOW", said)
            self.assertIn(os.path.join(pv.rate_dir("book"), "notes"), said)
        for tool, given in (("Write", {"file_path": os.path.join(self.dir, "notes.md")}),
                            ("Edit", {"file_path": os.path.join(self.dir, "chapter.md")}),
                            ("Read", {"file_path": handoff}),
                            ("Bash", {"command": "cat > notes/a.md <<'EOF'\nfound: $(not run)\nEOF"})):
            self.assertEqual(self.pretool(tool, **given), "", tool)
        self.calls(1)           # 78k + 40k: past the cap, only the handoff
        said = self.pretool("Write", file_path=os.path.join(self.dir, "notes.md"))
        self.assertIn("today's installment is used up", said)
        self.assertIn("PROGRESS", said)
        self.assertEqual(self.pretool("Edit", file_path=handoff), "")

    def test_without_a_part_kept_for_saving_it_stops_as_before(self):
        pv.store(("rate", "save_percent"), 0)
        self.new_job()
        self.t.user("installment")
        self.calls(2)
        self.assertEqual(self.pretool("WebSearch", query="x"), "")

    def test_a_helpers_call_counts_the_whole_installment(self):
        self.new_job()
        self.t.user("installment")
        self.calls(1)           # 26k in the chat, 26k in a helper, 40k for the closing steps
        helper = os.path.join(self.dir, "session", "subagents", "agent-a1.jsonl")
        write_rows(helper, [{"type": "assistant", "requestId": "s1", "message": {"id": "s1", "usage": usage(output=5200),
                                                                                  "content": []}}])
        self.assertIn("nearly used up", self.pretool("WebSearch", path=helper, query="x"))
        self.assertEqual(pv.main_transcript(helper), os.path.join(self.dir, "session.jsonl"))

    def test_only_a_here_document_is_a_command_that_only_writes(self):
        for ok in ("cat > a.md <<'EOF'\nx; y | z $(w)\nEOF", "cat >> a.md << EOF\nplain text\nEOF",
                   "cat <<'EOF' > notes/a.md\nx\nEOF", "tee -a a.md <<'EOF'\nx\nEOF"):
            self.assertTrue(pv.write_only(ok), ok)
        for no in ("ls", "cat a.md", "cat > a.md <<EOF\n$(curl x)\nEOF", "cat > a.md <<'EOF'\nx\nEOF\nls",
                   "cat > $(x) <<'EOF'\nx\nEOF", "curl x > a.md <<'EOF'\nx\nEOF", "cat > a.md <<'EOF'"):
            self.assertFalse(pv.write_only(no), no)

    def test_the_installment_is_told_to_save_as_it_goes(self):
        self.assertIn("as it goes", pv.RATE_PROMPT)
        self.assertIn("{notes}", pv.RATE_PROMPT)
        self.assertIn("lets Write and Edit through", pv.RATE_PROMPT)

    def test_the_end_of_a_stopped_installment_lists_its_helpers_work(self):
        self.new_job()
        folder = pv.rate_dir("book")
        main = os.path.join(self.dir, "inst1.jsonl")
        refused = "Quotient: this installment is nearly used up (93k of 100k wt spent)."
        write_rows(main, [{"type": "user", "message": {"content": "installment"}}] + tool_rows(["Agent"]))
        write_rows(os.path.join(self.dir, "inst1", "subagents", "agent-a1.jsonl"),
                   tool_rows(["WebSearch", "WebFetch", "WebSearch", "Read", "WebSearch"], refused=refused))
        with open(os.path.join(self.dir, "inst1", "subagents", "agent-a1.meta.json"), "w") as f:
            json.dump({"description": "History: 00-07"}, f)
        write_rows(os.path.join(self.dir, "inst1", "subagents", "agent-a2.jsonl"), tool_rows(["Read"], request="g"))
        result = {"session_id": "inst1", "usage": usage(output=100), "total_cost_usd": 0.01}
        args = mock.Mock(force=True)
        args.name = "book"
        with mock.patch.object(pv, "find_claude", return_value="claude"), \
                mock.patch.object(pv.subprocess, "run", return_value=mock.Mock(
                    stdout=json.dumps(result).encode(), stderr=b"", returncode=0)), \
                mock.patch.object(pv, "find_transcript", side_effect=lambda sid, near=None: main if sid == "inst1" else None):
            self.run_hook(lambda: pv.run_installment(args), {})
        self.assertTrue(os.path.isdir(os.path.join(folder, "notes")))
        handoff = pv.load_text(os.path.join(folder, "HANDOFF.md"))
        self.assertTrue(handoff.startswith("Nothing done yet."))
        self.assertIn("Work of the stopped helpers (installment 1", handoff)
        self.assertIn("History: 00-07: 3 searches, 1 pages, 1 reads, stopped by the cap. File: ", handoff)
        self.assertIn("helper: 0 searches, 0 pages, 1 reads. File: ", handoff)
        run = pv.read_jsonl(os.path.join(folder, "runs.jsonl"))[-1]
        self.assertEqual((run["helpers"], run["helpers_stopped"]), (2, 1))
        self.assertEqual(run["check"], 1)


def iso(epoch):
    return pv.datetime.fromtimestamp(epoch).astimezone().isoformat(timespec="seconds")


class TestWeekCheck(Base):
    """1.1.1: "if the measures are wrong, the correction learns the wrong thing": each job is set against the week."""

    def setUp(self):
        super().setUp()
        self.now = pv.time.time()
        self.resets = round(self.now + 3 * 86400)
        self.cap = mock.patch.object(pv, "capacity", return_value={"per_point": 100000.0, "points": 10, "windows": 1,
                                                                   "low": 1, "high": 1})
        self.cap.start()
        self.addCleanup(self.cap.stop)

    def reading(self, ago, used):
        pv.append_jsonl(pv.limits_path(), {"ts": "x", "epoch": round(self.now - ago), "seven_day": used,
                                           "seven_day_resets": self.resets})

    def job(self, actual, begin_ago=7200, end_ago=3600, session="s9", check=1):
        pv.append_jsonl(os.path.join(pv.home(), "jobs.jsonl"), {
            "started": iso(self.now - begin_ago + 60), "begin": self.now - begin_ago, "finished": iso(self.now - end_ago),
            "session": session, "choice": "max", "raw_estimate": actual, "actual": actual, "work": actual, "check": check})

    def prompt(self):
        return self.run_hook(pv.hook_prompt, {"session_id": "s1", "transcript_path": self.t.path})

    def test_a_measure_far_from_the_week_is_told_once(self):
        self.reading(7300, 10)
        self.job(2000000)           # 20 points of the week measured...
        self.reading(3500, 12)      # ...but the week rose 2
        first = self.prompt()
        self.assertIn("MEASURE CHECK: the job 'max'", first)
        self.assertIn("x10.0 higher than the week shows", first)
        self.assertIn("not a proof", first)
        self.assertNotIn("MEASURE CHECK", self.prompt())
        rows = pv.read_jsonl(pv.checks_path())
        self.assertEqual([(r["result"], r["points"], r["expected_points"]) for r in rows], [("warn", 2, 20.0)])
        report = self.run_hook(pv.report, {})
        self.assertIn("1 judged, 0 agree within x3, 1 do not", report)
        self.assertIn("measured 2.00M wt, the week rose 2 point(s) (~200k wt): x10.00", report)

    def test_a_measure_that_matches_the_week_agrees(self):
        self.reading(7300, 10)
        self.job(2000000)
        self.reading(3500, 31)      # 21 points: within a point of the 20 measured
        self.assertNotIn("MEASURE CHECK", self.prompt())
        self.assertEqual([r["result"] for r in pv.read_jsonl(pv.checks_path())], ["agrees"])

    def test_small_jobs_other_jobs_and_missing_readings_are_not_told(self):
        self.reading(7300, 10)
        self.job(200000)            # 2 points: too small to judge with whole percentages
        self.reading(3500, 10)
        self.assertNotIn("MEASURE CHECK", self.prompt())
        self.job(2000000, begin_ago=7100, end_ago=3550, session="s10")
        self.job(1000000, begin_ago=6000, end_ago=5000, session="s11", check=0)   # another job ran meanwhile
        self.job(2000000, begin_ago=5 * 3600, end_ago=4 * 3600, session="s12")    # no reading after it, 4 hours on
        self.job(2000000, begin_ago=1800, end_ago=1200, session="s13")            # no reading after it yet: waits
        self.assertNotIn("MEASURE CHECK", self.prompt())
        rows = {r["key"].split(":")[1]: r["result"] for r in pv.read_jsonl(pv.checks_path())}
        self.assertEqual(rows, {"s9": "small", "s10": "overlap", "s12": "no reading"})

    def test_a_closed_job_keeps_where_it_began_and_the_week(self):
        self.reading(60, 40)
        self.t.user("rewrite chapter 3, it's a big job")
        self.t.call("q", pv_usage(), texts=["QUOTE: essential=100k good=200k max=400k\nCHOICE: good\nPACE: today\nDone."])
        self.stop()
        job = pv.finished_jobs()[-1]
        self.assertEqual((job["check"], job["week_start"], job["week_end"]), (1, 40, 40))
        self.assertAlmostEqual(job["begin"], pv.ts_epoch("2026-10-05T10:00:01Z"), places=0)


def pv_usage():
    return usage(read=1000, output=2000)


class TestAside(Base):
    """1.1.1 (the user's idea): a reply about something else while a job is open is a real cost, not work."""

    def test_a_reply_about_something_else_is_counted_apart(self):
        self.t.user("rewrite chapter 3, it's a big job")
        self.t.call("q", usage(output=100), texts=["QUOTE: essential=100k good=200k max=400k"])
        self.stop()
        self.t.user("good")
        self.t.call("w1", usage(output=1000), texts=["CHOICE: good\nPACE: today", "Part one.\nJOB: CONTINUES"])
        self.stop()
        self.t.user("by the way, what is the weather like?")
        self.t.call("a1", usage(output=600), texts=["Sunny.\n\nASIDE"])
        self.stop()
        job = pv.load_json(pv.session_path("s1"), {})["job"]
        self.assertEqual((job["actual"], job["aside"], job["turns"], job["aside_turns"]), (8000, 3000, 1, 1))
        context = self.run_hook(pv.hook_prompt, {"session_id": "s1", "transcript_path": self.t.path})
        self.assertIn("spent so far 8k wt, of which 0 re-reading the older chat and 3k messages in between", context)
        self.assertIn("end the reply with the line ASIDE", context)
        self.t.user("go on")
        self.t.call("w2", usage(output=400), texts=["Finished."])
        self.stop()
        done = pv.finished_jobs()[-1]
        self.assertEqual((done["actual"], done["aside"], done["work"], done["calls"], done["aside_calls"]),
                         (10000, 3000, 7000, 2, 1))
        self.assertAlmostEqual(pv.learning(pv.config())["factor"], 7000 / 200000)
        context = self.run_hook(pv.hook_prompt, {"session_id": "s1", "transcript_path": self.t.path})
        self.assertIn("'work 7k wt · messages in between 3k wt · total 10k wt'", context)

    def test_the_protocol_asks_for_the_line(self):
        text = pv.protocol(pv.config(), 1.0)
        self.assertIn("messages about something else are counted apart", text)
        self.assertIn("`ASIDE`", text)
        self.assertTrue(pv.ASIDE_RE.search("Done.\n**ASIDE**"))
        self.assertTrue(pv.ASIDE_RE.search("ASIDE: the weather"))
        self.assertFalse(pv.ASIDE_RE.search("I set this ASIDE for later"))


class TestApartNow(InstallmentBase):
    """1.1.1 (the user's idea): 'apart, now': the job starts at once as one installment in a separate session."""

    def test_the_pace_apart(self):
        self.assertEqual(pv.parse_pace("CHOICE: max\nPACE: apart"), "apart")
        self.assertEqual(pv.parse_pace("RITMO: a parte, adesso"), "apart")
        self.assertEqual(pv.parse_pace("PACE: today"), "today")
        self.assertEqual(pv.parse_pace("PACE: new chat"), "new-chat")
        text = pv.protocol(pv.config(), 1.0)
        self.assertIn("'a parte, adesso'/'apart, now'", text)
        self.assertIn("they cannot talk to it while it works", text)
        self.assertIn("rate apart <short-name>", text)

    def test_a_job_chosen_apart_is_not_a_job_of_this_chat(self):
        self.t.user("rewrite chapter 3, it's a big job")
        self.t.call("q", usage(output=100), texts=["QUOTE: essential=100k good=200k max=400k\nCHOICE: max\nPACE: apart"])
        self.stop()
        self.assertIsNone(pv.load_json(pv.session_path("s1"), {}).get("job"))
        self.assertEqual(pv.finished_jobs(), [])

    def test_rate_apart_starts_one_installment_at_once(self):
        args = mock.Mock(dir=self.dir, task="write the book", task_file=None, quote=400000, model=None, template=None,
                         session=None)
        args.name = "book"
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "home1"}), \
                mock.patch.object(pv, "start_detached", return_value=True) as start:
            said = self.run_hook(lambda: pv.rate_apart(args), {})
        start.assert_called_once_with(["rate", "run", "book"], os.path.join(pv.rate_dir("book"), "apart.log"))
        job = pv.load_json(os.path.join(pv.rate_dir("book"), "job.json"), None)
        self.assertEqual((job["days"], job["daily_cap"], job["after"], job["apart"], job["session"]),
                         (1, 400000, "nothing", True, "home1"))
        self.assertIn("started apart, now", said)
        self.assertIn("cannot be talked to while it works", said)
        self.assertIn("comes back to this chat", said)
        self.assertNotIn("rate schedule", said)

    def test_it_starts_apart_from_the_chat(self):
        log = os.path.join(self.dir, "apart.log")
        # Windows tries again without breaking away from the chat's job object; elsewhere there is one try
        tries = [OSError("no breakaway"), mock.Mock()] if os.name == "nt" else [mock.Mock()]
        with mock.patch.object(pv.subprocess, "Popen", side_effect=tries) as popen:
            self.assertTrue(pv.start_detached(["rate", "run", "book"], log))
        self.assertEqual(popen.call_count, 2 if os.name == "nt" else 1)
        self.assertEqual(popen.call_args[0][0][-3:], ["rate", "run", "book"])

    def test_a_job_started_from_hermes_reports_there(self):
        self.new_job(session="hermes:chat7")
        pv.append_jsonl(os.path.join(pv.rate_dir("book"), "runs.jsonl"),
                        {"started": "2026-10-15T15:00:00+02:00", "finished": "2026-10-15T15:20:00+02:00", "wt": 90000,
                         "cap": 100000, "error": None, "done": False})
        self.assertEqual(pv.rate_events("s1"), [])            # a Claude Code chat leaves it to its Hermes chat
        lines = pv.rate_events("hermes:chat7", own_only=True)
        self.assertIn("Installment report of job 'book'", lines[0])
        self.assertEqual(pv.rate_events("hermes:chat7", own_only=True), [])   # told once
