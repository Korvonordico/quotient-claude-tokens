"""1.2.3: the installments' rule on thinking with code; the shared average and your own numbers together, for good
(shared_min_weight); the price table of the Claude models (data/model-prices.json, `prices`, model_price).
Run: python -m unittest discover tests"""

import json
import math
import os
from unittest import mock

from test_quotient import Base, AVERAGE, pv


def mixed(own, shared, weight):
    return math.exp(weight * math.log(shared) + (1 - weight) * math.log(own))


class TestPrompt(Base):
    def test_each_installment_is_told_to_think_with_code(self):
        text = pv.RATE_PROMPT.format(task="t", handoff="h", notes="n", workdir="w", cap="1", number=1, days=1)
        self.assertIn("write a small script that prints only the result", text)


class V123(Base):
    def setUp(self):
        super().setUp()
        on = mock.patch.dict(pv.DEFAULTS, {"shared_min_weight": 0.1})
        on.start()
        self.addCleanup(on.stop)

    def jobs(self, count, ratio=1.0, **kw):
        for _ in range(count):
            pv.append_jsonl(os.path.join(pv.home(), "jobs.jsonl"),
                            dict({"raw_estimate": 100000, "actual": round(100000 * ratio)}, **kw))

    def average(self, data=AVERAGE):
        pv.save_json(pv.average_path(), data)


class TestDefaults(Base):
    def test_shipped_default(self):
        # Base patches it for the older tests: read the module's own value from a fresh import of the source
        import importlib.util
        spec = importlib.util.spec_from_file_location("q123", pv.__file__)
        fresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fresh)
        self.assertEqual(fresh.DEFAULTS["shared_min_weight"], 0)


class TestTogether(V123):
    def test_the_weight_falls_and_stops_at_the_floor(self):
        cfg = pv.config()
        self.assertEqual(pv.shared_weight(cfg, 0), 1.0)
        self.assertAlmostEqual(pv.shared_weight(cfg, 5), 0.5)
        self.assertAlmostEqual(pv.shared_weight(cfg, 45), 0.1)
        self.assertEqual(pv.shared_weight(cfg, 1000), 0.1)

    def test_with_no_jobs_the_factor_is_the_shared_one(self):
        self.average()
        learned = pv.learning(pv.config())
        self.assertAlmostEqual(learned["factor"], 1.3)
        self.assertEqual((learned["shared"], learned["shared_weight"]), (40, 1.0))

    def test_few_jobs_mix_with_their_weight(self):
        self.average()
        self.jobs(3, 0.5, family="opus")   # the average of the family: x1.2
        learned = pv.learning(pv.config())
        self.assertAlmostEqual(learned["shared_weight"], 5 / 8.0)
        self.assertAlmostEqual(learned["factor"], mixed(0.5, 1.2, 5 / 8.0), places=3)

    def test_it_stays_after_min_jobs_and_never_falls_under_the_floor(self):
        self.average()
        self.jobs(5, 1.0, family="haiku")   # before 1.2.3 this was x1.0: your jobs had taken over
        learned = pv.learning(pv.config())
        self.assertAlmostEqual(learned["factor"], mixed(1.0, 2.0, 0.5), places=3)
        self.jobs(200, 1.0, family="haiku")
        learned = pv.learning(pv.config())
        self.assertEqual(learned["shared_weight"], 0.1)
        self.assertAlmostEqual(learned["factor"], mixed(1.0, 2.0, 0.1), places=3)
        self.assertEqual(learned["shared"], 10)

    def test_with_no_average_it_is_as_before(self):
        self.jobs(3, 0.5)
        learned = pv.learning(pv.config())
        self.assertAlmostEqual(learned["factor"], 0.5, places=3)
        self.assertIsNone(learned["shared_weight"])
        self.assertEqual(learned["shared"], 0)

    def test_zero_is_the_old_way(self):
        self.average()
        self.jobs(5, 1.0, family="haiku")
        with mock.patch.dict(pv.DEFAULTS, {"shared_min_weight": 0}):
            learned = pv.learning(pv.config())
        self.assertAlmostEqual(learned["factor"], 1.0, places=3)
        self.assertEqual(learned["shared"], 0)
        self.assertIsNone(learned["shared_weight"])

    def test_the_limits_hold(self):
        self.average()
        self.jobs(50, 0.01, family="opus")
        self.assertEqual(pv.learning(pv.config())["factor"], pv.FACTOR_MIN)
        self.jobs(150, 100.0, family="opus")
        self.assertEqual(pv.learning(pv.config())["factor"], pv.FACTOR_MAX)

    def test_the_jobs_before_are_judged_the_same_way(self):
        self.average()
        self.jobs(2, 0.5, family="opus")
        rows = pv.learning(pv.config())["rows"]
        self.assertAlmostEqual(rows[0]["factor_before"], 1.2)   # no job before it: the shared average alone
        self.assertAlmostEqual(rows[1]["factor_before"], mixed(0.5, 1.2, 5 / 6.0), places=3)

    def test_the_installments_mix_too(self):
        self.average()
        self.jobs(5, 0.5, family="opus", kind="rate", choice="rate")
        learned = pv.learning(pv.config(), "rate")
        self.assertAlmostEqual(learned["factor"], mixed(0.5, 1.2, 0.5), places=3)

    def test_the_start_rows_stay_and_the_average_weighs_the_floor(self):
        # 1.1.9's starts were measured on clean jobs: a new user does not go from x0.58 to the average of all jobs
        self.average()
        with mock.patch.dict(pv.DEFAULTS, {"learn_clean_only": 1, "start_factor": 0.58}):
            learned = pv.learning(pv.config())
        self.assertEqual(learned["shared_weight"], 0.1)
        self.assertAlmostEqual(learned["factor"], mixed(0.58, 1.3, 0.1), places=3)

    def test_the_lines_say_so(self):
        self.average()
        self.jobs(5, 1.0, family="haiku")
        cfg = pv.config()
        self.assertIn("weighs 50%", pv.calibration(cfg, pv.learning(cfg)))
        self.assertIn("never under 10%", pv.share_status(cfg))


class TestPrices(Base):
    TABLE = {"claude-opus-4-1": {"input_cost_per_token": 1.5e-05, "output_cost_per_token": 7.5e-05,
                                 "cache_read_input_token_cost": 1.5e-06, "cache_creation_input_token_cost": 1.875e-05,
                                 "litellm_provider": "anthropic", "max_tokens": 32000},
             "claude-sonnet-4-20250514": {"input_cost_per_token": 3e-06, "output_cost_per_token": 1.5e-05},
             "claude-sonnet-4-latest": {"input_cost_per_token": 4e-06},
             "us.anthropic.claude-x-v1:0": {"input_cost_per_token": 1e-06, "output_cost_per_token": "free"},
             "claude-empty": {"mode": "chat"},
             "gpt-4": {"input_cost_per_token": 3e-05, "output_cost_per_token": 6e-05},
             "sample_spec": "not a model"}

    def setUp(self):
        super().setUp()
        self.path = os.path.join(self.dir, "data", "model-prices.json")
        patcher = mock.patch.object(pv, "prices_path", return_value=self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self):
        pv.save_json(self.path, {"models": pv.filter_prices(self.TABLE), "updated": "2026-10-30"})

    def test_only_the_claude_models_and_their_prices(self):
        models = pv.filter_prices(self.TABLE)
        self.assertEqual(sorted(models), ["claude-opus-4-1", "claude-sonnet-4-20250514", "claude-sonnet-4-latest",
                                          "us.anthropic.claude-x-v1:0"])
        self.assertEqual(models["claude-opus-4-1"], {"input": 1.5e-05, "output": 7.5e-05, "cache_read": 1.5e-06,
                                                     "cache_write": 1.875e-05})
        self.assertEqual(models["us.anthropic.claude-x-v1:0"], {"input": 1e-06})   # a price that is not a number is left out

    def test_model_price(self):
        self.write()
        self.assertEqual(pv.model_price("claude-opus-4-1")["output"], 7.5e-05)
        self.assertEqual(pv.model_price("CLAUDE-OPUS-4-1[1m]")["input"], 1.5e-05)
        self.assertEqual(pv.model_price("anthropic/claude-opus-4-1")["input"], 1.5e-05)
        self.assertEqual(pv.model_price("claude-opus-4-1-20250805")["input"], 1.5e-05)     # the same model, with a date
        self.assertEqual(pv.model_price("claude-sonnet-4-20250514")["input"], 3e-06)       # exactly that line
        self.assertEqual(pv.model_price("claude-sonnet-4")["input"], 4e-06)                # no date: the latest
        self.assertIsNone(pv.model_price("claude-opus-4"))      # another version never: its price can differ
        self.assertIsNone(pv.model_price("gpt-4"))
        self.assertIsNone(pv.model_price(None))

    def test_no_table_no_price(self):
        self.assertIsNone(pv.model_price("claude-opus-4-1"))
        self.assertIn("No price table yet", self.run_hook(lambda: pv.cmd_prices(mock.Mock(action=None)), {}))

    def test_update_downloads_and_filters(self):
        body = json.dumps(self.TABLE).encode("utf-8")
        with mock.patch.object(pv, "http", return_value=(200, body)) as http:
            said = self.run_hook(lambda: pv.cmd_prices(mock.Mock(action="update")), {})
        self.assertEqual(http.call_args[0][:2], ("GET", pv.PRICES_URL))
        self.assertIn("4 Claude models", said)
        self.assertIn("claude-opus-4-1", said)
        self.assertIn("15.00", said)   # dollars per million tokens
        saved = pv.load_json(self.path, {})
        self.assertNotIn("gpt-4", saved["models"])
        self.assertEqual(saved["source"], pv.PRICES_URL)

    def test_a_failed_update_leaves_the_old_table(self):
        self.write()
        before = pv.load_json(self.path, {})
        for answer in ((None, b""), (200, b"not json"), (200, b'{"gpt-4": {"input_cost_per_token": 1}}'), (500, b"{}")):
            with mock.patch.object(pv, "http", return_value=answer):
                with self.assertRaises(SystemExit):
                    pv.prices_update()
            self.assertEqual(pv.load_json(self.path, {}), before)

    def test_showing_or_reading_prices_never_uses_the_network(self):
        self.write()
        with mock.patch.object(pv, "http") as http:
            pv.model_price("claude-opus-4-1")
            self.run_hook(lambda: pv.cmd_prices(mock.Mock(action=None)), {})
        http.assert_not_called()


class TestShippedPrices(Base):
    def test_the_table_and_its_license_ship_with_the_plugin(self):
        root = pv.plugin_root()
        models = pv.load_json(os.path.join(root, "data", "model-prices.json"), {})["models"]
        self.assertTrue(models)
        self.assertTrue(all("claude" in name.lower() or "anthropic" in name.lower() for name in models))
        self.assertEqual(sorted(pv.model_price("claude-opus-4-1")), ["cache_read", "cache_write", "input", "output"])
        with open(os.path.join(root, "data", "LICENSE-tokencost.txt"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("MIT License", text)
        self.assertIn("Copyright (c) 2023 AgentOps", text)
