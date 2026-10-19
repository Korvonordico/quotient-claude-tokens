"""1.1.6: the plan in the settings and the shared size of 1% of the week by plan, the limits read more often during a
job, Claude Code's own telemetry, the costs Hermes and the status line already know, and the estimate from the
progress of each package of work.
Run: python -m unittest discover tests"""

import io
import json
import os
import sys
from unittest import mock

import unittest

from test_quotient import Base, pv


AVERAGE = {"schema": 1, "updated": "2026-10-15", "all": {"jobs": 40, "factor": 1.2},
           "plans": {"max5": {"jobs": 12, "per_point": 300000, "p25": 250000, "p75": 380000},
                     "pro": {"jobs": 3, "per_point": 5},               # implausible: left out
                     "team": {"jobs": 9, "per_point": 300000}}}       # not a plan Quotient knows: left out


class Cli(Base):
    def cli(self, *argv):
        stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        with mock.patch.object(sys, "stdout", stdout):
            pv.main(list(argv))
            stdout.flush()
            return stdout.buffer.getvalue().decode("utf-8")


class TestPlan(Cli):
    def test_the_plan_from_the_users_words(self):
        for words, plan in (("Pro", "pro"), ("Max 5x", "max5"), ("max_20x", "max20"), ("Max 20x", "max20"),
                            ("altro", "other"), ("Team", "other"), ("non so", "unknown"), ("unknown", "unknown")):
            self.assertEqual(pv.plan_word(words), plan, words)
        self.assertIsNone(pv.plan_word("banana"))
        self.assertIsNone(pv.plan_word(""))

    def test_setup_and_plan_changed_keep_the_plan(self):
        self.assertEqual(pv.config()["subscription"], "")
        text = self.cli("setup", "--plan", "Max 5x")
        self.assertIn("plan: max5", text)
        self.assertEqual(pv.config()["subscription"], "max5")
        with self.assertRaises(SystemExit):
            self.cli("setup", "--plan", "banana")
        self.assertEqual(pv.config()["subscription"], "max5")
        text = self.cli("plan-changed", "--plan", "max20")
        self.assertIn("Plan saved: max20", text)
        self.assertEqual(pv.config()["subscription"], "max20")
        self.assertTrue(pv.read_jsonl(pv.plan_changes_path()))      # and the limit is learned again from now

    def test_the_shared_line_carries_the_plan_only_when_chosen(self):
        job = {"raw_estimate": 225000, "actual": 259311, "work": 259311, "family": "opus"}
        cfg = pv.config()
        row = pv.share_row(job, cfg, 312345)
        self.assertNotIn("plan", row)
        self.assertEqual(row["per_point"], 312345)
        self.assertEqual(set(row), set(pv.SHARE_FIELDS) | {"per_point"})
        pv.store(("subscription",), "unknown")                       # "I don't know" is not sent
        self.assertNotIn("plan", pv.share_row(job, pv.config()))
        pv.store(("subscription",), "max5")
        row = pv.share_row(job, pv.config(), 5)                        # a size out of range is not sent
        self.assertEqual(row["plan"], "max5")
        self.assertNotIn("per_point", row)
        self.assertNotIn("plan", pv.share_row(job))                    # without the settings: the five fields only

    def test_a_service_not_updated_yet_gets_the_line_without_the_new_fields(self):
        pv.store(("share", "enabled"), True)
        pv.store(("share", "endpoint"), "https://quotient.example")
        pv.append_jsonl(pv.outbox_path(), {"v": 1, "q": pv.VERSION, "family": "opus", "estimate": 100000,
                                           "actual": 120000, "plan": "max5", "per_point": 300000})
        self.net.side_effect = [(400, b""), (200, b"")]
        self.assertEqual(pv.flush_share(pv.config(), 9e12), 1)
        first, second = [c.args[2] for c in self.net.call_args_list]
        self.assertEqual(first["plan"], "max5")
        self.assertEqual(first["per_point"], 300000)
        self.assertEqual(set(second), set(pv.SHARE_FIELDS))
        self.assertEqual(pv.read_jsonl(pv.outbox_path()), [])

    def test_the_average_keeps_only_plausible_plans(self):
        clean = pv.check_average(AVERAGE)
        self.assertEqual(list(clean["plans"]), ["max5"])
        self.assertEqual(clean["plans"]["max5"]["per_point"], 300000)
        no_plans = dict(AVERAGE)
        no_plans.pop("plans")
        self.assertNotIn("plans", pv.check_average(no_plans))           # an older service: still a good file

    def test_a_new_user_starts_from_the_average_of_their_plan(self):
        pv.save_json(pv.average_path(), pv.check_average(AVERAGE))
        cfg = pv.config()
        self.assertIsNone(pv.week_capacity(cfg))                      # no plan chosen: nothing to start from
        pv.store(("subscription",), "max5")
        cfg = pv.config()
        c = pv.week_capacity(cfg)
        self.assertEqual(c["source"], "plan")
        self.assertEqual((c["per_point"], c["low"], c["high"]), (300000, 250000, 380000))
        self.assertIn("NOT measured here yet", pv.week_source(c))
        self.assertIsNone(pv.learned_per_point(cfg))                   # the average is never sent back as ours
        self.assertIn("max5 plan", self.run_hook(pv.hook_prompt, {"session_id": "s1", "transcript_path": self.t.path}))
        self.assertIn("Your plan (max5)", pv.share_status(cfg))


class TestLimitsDuringAJob(Cli):
    def setUp(self):
        super().setUp()
        live = mock.patch.dict(os.environ, {"QUOTIENT_LIMITS_LIVE": "1"})
        live.start()
        self.addCleanup(live.stop)
        self.started = mock.patch.object(pv, "start_detached", return_value=True).start()
        self.addCleanup(mock.patch.stopall)

    def test_every_minute_during_a_job_every_ten_otherwise(self):
        cfg = pv.config()
        # 1.1.8: every minute with no job open too (it was every ten minutes)
        self.assertEqual((pv.limits_every(cfg, busy=True), pv.limits_every(cfg)), (60, 60))
        pv.store(("limits", "job_every"), 30)
        self.assertEqual(pv.limits_every(pv.config(), busy=True), 30)

    def test_a_reading_in_the_background_at_most_once_a_minute(self):
        cfg = pv.config()
        self.assertTrue(pv.limits_soon(cfg))
        self.assertEqual(self.started.call_args.args[0], ["limits-read"])
        pv.record_limits({"five_hour": 10, "seven_day": 3}, "usage")
        self.started.reset_mock()
        self.assertFalse(pv.limits_soon(cfg))                     # read a moment ago
        self.started.assert_not_called()
        with mock.patch.dict(os.environ, {"QUOTIENT_LIMITS_LIVE": "0"}):
            self.assertFalse(pv.limits_soon(cfg))                 # live readings off: never

    def test_a_reading_two_minutes_old_is_read_again_only_during_a_job(self):
        pv.store(("limits", "every"), 600)   # 1.1.8: the default is 60; this test is about the two paces
        pv.record_limits({"five_hour": 10, "seven_day": 3}, "usage")
        rows = pv.read_jsonl(pv.limits_path())
        rows[-1]["epoch"] -= 120
        with open(pv.limits_path(), "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(r) + "\n" for r in rows))
        import limits_usage
        with mock.patch.object(limits_usage, "fetch", return_value={"five_hour": 11, "seven_day": 3}) as fetch, \
                mock.patch.object(pv, "find_claude", return_value="claude"):
            self.assertIsNone(pv.refresh_limits(pv.config()))                   # every 10 minutes: not yet
            self.assertEqual(pv.refresh_limits(pv.config(), every=60)["five_hour"], 11)
            self.assertEqual(fetch.call_count, 1)
            self.assertIsNone(pv.refresh_limits(pv.config(), every=60))         # tried just now

    def test_an_installment_reads_while_it_works(self):
        pv.store(("limits", "job_every"), 0.02)
        with mock.patch.object(pv, "refresh_limits") as refresh:
            stop = pv.limits_reader(pv.config())
            for _ in range(200):
                if refresh.call_count >= 2:
                    break
                pv.time.sleep(0.01)
            stop.set()
        self.assertGreaterEqual(refresh.call_count, 2)
        self.assertEqual(refresh.call_args.kwargs["every"], 0.02)
        with mock.patch.dict(os.environ, {"QUOTIENT_LIMITS_LIVE": "0"}):
            self.assertIsNone(pv.limits_reader(pv.config()))

    def test_the_message_of_an_open_job_asks_for_a_reading(self):
        pv.save_json(pv.session_path("s1"), {"job": {"choice": "good", "raw_estimate": 100000, "actual": 5000,
                                                       "chat": 0, "factor_used": 1.0}})
        with mock.patch.object(pv, "limits_soon") as soon:
            self.run_hook(pv.hook_prompt, {"session_id": "s1", "transcript_path": self.t.path})
        soon.assert_called_once()
        with mock.patch.object(pv, "limits_soon") as soon:
            self.run_hook(pv.hook_prompt, {"session_id": "s2", "transcript_path": self.t.path})
        soon.assert_called_once()                                    # 1.1.8: no job: a reading too, at the usual pace
        self.assertEqual(soon.call_args.args[1], 60)


import socket
import tempfile
import threading
import urllib.request
from datetime import datetime

import telemetry
import hermes_source as hs
from test_hermes import fake_hermes, update, W


def iso(epoch):
    return datetime.fromtimestamp(epoch).astimezone().isoformat(timespec="seconds")


def point(value, start, end, **attrs):
    return {"attributes": [{"key": k.replace("_", "."), "value": {"stringValue": v}} if k != "query_source" else
                           {"key": k, "value": {"stringValue": v}} for k, v in attrs.items()],
            "startTimeUnixNano": str(int(start * 1e9)), "timeUnixNano": str(int(end * 1e9)), "asDouble": value}


def otlp(points, name="claude_code.token.usage", temporality=1):
    return {"resourceMetrics": [{"resource": {"attributes": [
        {"key": "user.email", "value": {"stringValue": "someone@example.com"}},
        {"key": "user.account_uuid", "value": {"stringValue": "acc-123"}}]},
        "scopeMetrics": [{"metrics": [
            {"name": name, "sum": {"aggregationTemporality": temporality, "isMonotonic": True, "dataPoints": points}},
            {"name": "claude_code.session.count", "sum": {"dataPoints": [{"asInt": "1"}]}}]}]}]}


class TestTelemetry(Cli):
    def tokens(self, start, end, session="s9", source="main", **by_type):
        return [point(v, start, end, session_id=session, model="claude-opus-5-5", query_source=source, type=t)
                for t, v in by_type.items()]

    def test_numbers_only_from_a_message(self):
        rows = telemetry.rows_from(otlp(self.tokens(100, 130, input=1000, output=200, bogus=5)))
        self.assertEqual([(r["type"], r["value"], r["session"], r["source"]) for r in rows],
                         [("input", 1000, "s9", "main"), ("output", 200, "s9", "main")])
        self.assertNotIn("example.com", json.dumps(rows))
        self.assertNotIn("acc-123", json.dumps(rows))
        cost = telemetry.rows_from(otlp([point(0.25, 100, 130, session_id="s9", model="m")], "claude_code.cost.usage"))
        self.assertEqual((cost[0]["metric"], cost[0]["value"]), ("cost", 0.25))

    def test_a_cumulative_counter_gives_what_it_grew_by(self):
        series = {}
        first = telemetry.rows_from(otlp(self.tokens(100, 130, output=100), temporality=2), series)
        second = telemetry.rows_from(otlp(self.tokens(100, 160, output=250), temporality=2), series)
        self.assertEqual([r["value"] for r in first + second], [100, 150])

    def test_the_receiver_keeps_the_numbers_and_stops_when_turned_off(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        pv.store(("telemetry", "enabled"), True)
        thread = threading.Thread(target=telemetry.serve, args=(pv, port, None, 0.05), daemon=True)
        thread.start()
        url = "http://127.0.0.1:%d" % port
        for _ in range(100):
            if os.path.exists(telemetry.life_path(pv.home())):
                break
            pv.time.sleep(0.02)

        def post(path, body, kind="application/json"):
            req = urllib.request.Request(url + path, data=body, method="POST", headers={"Content-Type": kind})
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    return resp.status
            except urllib.error.HTTPError as e:
                return e.code

        self.assertEqual(post("/v1/metrics", json.dumps(otlp(self.tokens(100, 130, input=7))).encode()), 200)
        self.assertEqual(post("/v1/logs", b"{}"), 200)
        self.assertEqual(post("/v1/metrics", b"\x0a\x01", "application/x-protobuf"), 415)
        rows = pv.read_jsonl(telemetry.otel_path(pv.home()))
        self.assertEqual([(r["type"], r["value"]) for r in rows], [("input", 7)])
        second = []
        other = threading.Thread(target=lambda: second.append(telemetry.serve(pv, port)), daemon=True)
        other.start()
        other.join(3)
        self.assertEqual(second, [False])                           # one receiver: the port is the lock
        pv.store(("telemetry", "enabled"), False)
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertTrue(pv.load_json(telemetry.life_path(pv.home()), {}).get("stopped"))

    def test_a_job_set_against_the_telemetry(self):
        begin = pv.time.time() - 7200
        end = begin + 600
        pv.append_jsonl(os.path.join(pv.home(), "jobs.jsonl"), {
            "session": "s9", "raw_estimate": 100000, "actual": 200000, "chat": 0, "work": 200000, "choice": "good",
            "started": iso(begin), "finished": iso(end)})
        rows = telemetry.rows_from(otlp(self.tokens(begin - 200, begin - 100, session="other", input=5)))
        rows += telemetry.rows_from(otlp(self.tokens(begin, begin + 300, input=1000, output=20000, cacheRead=1000000,
                                                     cacheCreation=50000)))
        rows += telemetry.rows_from(otlp(self.tokens(begin, begin + 300, source="auxiliary", output=200)))
        for r in rows:
            pv.append_jsonl(telemetry.otel_path(pv.home()), r)
        cfg = pv.config()
        self.assertIsNone(telemetry.alert(pv, cfg))                 # telemetry off: nothing
        pv.store(("telemetry", "enabled"), True)
        cfg = pv.config()
        line = telemetry.alert(pv, cfg)
        self.assertIn("TELEMETRY CHECK", line)
        self.assertIn("Quotient 200k wt, Claude Code's telemetry 302k wt (+51%)", line)
        self.assertIsNone(telemetry.alert(pv, cfg))                 # told once
        check = pv.read_jsonl(telemetry.checks_path(pv.home()))[-1]
        self.assertEqual(check["aux_wt"], 1000)
        with mock.patch.object(pv, "start_detached", return_value=True):
            report = self.run_hook(pv.report, {})
        self.assertIn("1 job(s) and installment(s) measured by both", report)
        self.assertIn("calls on the side (auxiliary)", report)

    def test_on_and_off_write_the_settings_with_a_copy_first(self):
        claude = os.path.join(self.dir, "claude")
        os.makedirs(claude)
        path = os.path.join(claude, "settings.json")
        pv.save_json(path, {"model": "opus", "env": {"MINE": "1"}})
        with mock.patch.dict(os.environ, {"QUOTIENT_CLAUDE_DIR": claude}), \
                mock.patch.object(pv, "start_detached", return_value=True) as started:
            text = self.cli("telemetry", "on")
            self.assertIn('"OTEL_EXPORTER_OTLP_PROTOCOL": "http/json"', text)
            self.assertEqual(pv.load_json(path, {})["env"], {"MINE": "1"})   # printed, not written
            self.cli("telemetry", "on", "--write")
            env = pv.load_json(path, {})["env"]
            self.assertEqual(env["MINE"], "1")
            self.assertEqual(env["OTEL_EXPORTER_OTLP_ENDPOINT"], "http://127.0.0.1:4318")
            self.assertEqual(env["OTEL_METRICS_INCLUDE_ACCOUNT_UUID"], "false")
            self.assertTrue([f for f in os.listdir(claude) if f.endswith(".bak")])
            self.assertTrue(pv.config()["telemetry"]["enabled"])
            self.assertEqual(started.call_args.args[0], ["telemetry", "serve"])
            self.cli("telemetry", "off", "--write")
            self.assertEqual(pv.load_json(path, {})["env"], {"MINE": "1"})
            self.assertFalse(pv.config()["telemetry"]["enabled"])


class TestCosts(Cli):
    def test_hermes_keeps_the_growth_of_its_own_cost(self):
        h = fake_hermes([("c1", "cli", "claude-opus-5-5", 1000.0, 2000.0, None, "x", "anthropic", 10, 100, 10000, 1000)])
        update(h, "c1", estimated_cost_usd=0.5)
        rows = hs.sync(self.dir, W, home=h, now=5000.0)
        self.assertEqual(rows[0]["usd"], 0.5)
        update(h, "c1", output_tokens=300, estimated_cost_usd=0.8)
        rows = hs.sync(self.dir, W, home=h, now=6000.0)
        self.assertAlmostEqual(rows[0]["usd"], 0.3)

    def test_a_snapshot_from_before_only_notes_the_cost(self):
        h = fake_hermes([("c1", "cli", "claude-opus-5-5", 1000.0, 2000.0, None, "x", "anthropic", 10, 100, 10000, 1000)])
        hs.sync(self.dir, W, home=h, now=5000.0)
        state = pv.load_json(os.path.join(self.dir, "hermes-state.json"), {})
        state.pop("usd")
        pv.save_json(os.path.join(self.dir, "hermes-state.json"), state)
        update(h, "c1", output_tokens=300, estimated_cost_usd=9.0)
        rows = hs.sync(self.dir, W, home=h, now=6000.0)
        self.assertAlmostEqual(rows[0]["usd"], 0.0)                 # its whole cost is not put at this moment

    def test_the_prices_hermes_costs_imply(self):
        now = pv.time.time()
        for i in range(12):
            inp, out, read, write = 1000 + 300 * i, 2000 + 500 * (i % 4), 100000 * (1 + i % 5), 5000 * (i % 3)
            usd = 4e-6 * (inp + 1.25 * write) + 20e-6 * out + 0.2e-6 * read
            w = inp + 1.25 * write + 5 * out + 0.1 * read
            pv.append_jsonl(os.path.join(pv.home(), "hermes.jsonl"), {
                "epoch": now - 100 * i, "session": "c%d" % i, "model": "claude-opus-5-5", "wt": round(w), "usd": usd,
                "input_tokens": inp, "output_tokens": out, "cache_read_tokens": read, "cache_write_tokens": write})
        h = pv.hermes_cost(pv.config())
        self.assertAlmostEqual(h["prices"]["output"], 5.0, places=3)
        self.assertAlmostEqual(h["prices"]["cache_read"], 0.05, places=4)
        for n in range(3):
            os.makedirs(os.path.join(pv.home(), "rate", "j%d" % n))
            pv.append_jsonl(os.path.join(pv.home(), "rate", "j%d" % n, "runs.jsonl"),
                            {"started": "2026-10-1%dT03:00:00+02:00" % n, "wt": 1000000, "usd": 4.0})
        self.assertAlmostEqual(pv.usd_per_wt(), 4e-6)
        text = "\n".join(pv.cost_lines(pv.config(), "en"))
        self.assertIn("$4.00 per million weighted tokens", text)
        self.assertIn("cache read x0.050; Quotient weighs x5 and x0.1: apart beyond x1.25 for cache_read", text)

    def test_the_status_line_cost_is_the_third_measure(self):
        for usd in (1.0, 1.0, 2.5):
            self.run_hook(pv.statusline, {"session_id": "s1", "cost": {"total_cost_usd": usd}})
        rows = pv.read_jsonl(pv.statusline_cost_path())
        self.assertEqual([r["usd"] for r in rows], [1.0, 2.5])      # kept when it changes
        rows = [{"session": "s1", "epoch": 100, "usd": 1.0}, {"session": "s1", "epoch": 305, "usd": 1.6},
                {"session": "s1", "epoch": 400, "usd": 3.0}]
        self.assertAlmostEqual(pv.session_usd(rows, "s1", 150, 300), 0.6)
        self.assertAlmostEqual(pv.session_usd(rows, "s1", 310, 400), 1.4)
        self.assertIsNone(pv.session_usd(rows, "s1", 310, 600))      # no reading near its end
        self.assertIsNone(pv.session_usd(rows, "s1", 50, 300))       # none before its start
        self.assertIsNone(pv.session_usd(rows, "s2", 0, 100))


class TestPackages(Cli):
    def test_a_package_at_each_million_with_a_progress_line(self):
        cfg = pv.config()
        job = {"seconds": 600}
        self.assertIsNone(pv.add_package(job, 900000, 30, cfg))
        self.assertIsNone(pv.add_package(job, 1100000, None, cfg))
        self.assertEqual(pv.add_package(job, 1100000, 30, cfg)["progress"], 30)
        self.assertIsNone(pv.add_package(job, 1500000, 40, cfg))      # the same million
        job["seconds"] = 1200
        self.assertEqual(pv.add_package(job, 2100000, 55, cfg)["seconds"], 1200)
        est = pv.package_estimate(job["packages"], cfg)
        self.assertEqual(est["total"], round(2100000 * 100 / 55))
        self.assertEqual((est["low"], est["high"]), (round(2100000 * 100 / 65), round(2100000 * 100 / 45)))
        self.assertEqual(est["seconds"], round(1200 * 100 / 55))
        note = pv.pace_note(3000000, 1.0, 2200000, 1200, cfg, 55, job["packages"])
        self.assertIn("By cost so far / progress: the whole job about 3.82M wt (between 3.23M and 4.67M)", note)
        self.assertNotIn("again", note)
        self.assertIn("write PROGRESS: <n>% again", pv.pace_note(3000000, 1.0, 3100000, 1300, cfg, 55, job["packages"]))
        check = pv.progress_check(job["packages"], 4000000)
        self.assertEqual(check["errors"], [2.5, 2.5])

    def test_the_progress_error_becomes_the_margin(self):
        self.assertEqual(pv.progress_error(), (10.0, 0))
        for i, m in enumerate((2.0, 4.0, 6.0)):
            pv.append_jsonl(os.path.join(pv.home(), "jobs.jsonl"), {
                "session": "x%d" % i, "raw_estimate": 100000, "actual": 100000, "chat": 0, "work": 100000,
                "choice": "good", "started": "2026-10-14T10:00:00+02:00", "finished": "2026-10-14T11:00:00+02:00",
                "progress_check": {"packages": 2, "errors": [m, m], "median": m}})
        self.assertEqual(pv.progress_error(), (4.0, 3))
        est = pv.package_estimate([{"work": 1000000, "seconds": 0, "progress": 50}])
        self.assertEqual((est["low"], est["high"]), (round(1e8 / 54), round(1e8 / 46)))
        report = self.run_hook(pv.report, {})
        self.assertIn("3 job(s) closed in packages (6 packages); the line was off by 4 points", report)

    def test_installments_are_packages(self):
        runs = [{"wt": 1000000, "seconds": 600, "progress": 25}, {"wt": 1000000, "seconds": 600, "progress": None},
                {"wt": 1000000, "seconds": 600, "progress": 60}]
        packs = pv.run_packages(runs)
        self.assertEqual([(p["work"], p["progress"]) for p in packs], [(1000000, 25), (3000000, 60)])
        self.assertEqual(pv.package_estimate(packs, kind="rate")["total"], 5000000)
        self.assertEqual(pv.progress_check(packs, 4000000)["median"], 7.5)


if __name__ == "__main__":
    unittest.main()
