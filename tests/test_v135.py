"""1.3.5: the rule for texts counts 40 wt per word (was 27). Measured on 01/11/2026 (13 texts of 400 to 20,000 words
asked, new sessions through the API): the work of a text cost 33 to 63 wt per word asked, median about 40, at every
length; with 27 a text of 5,000 to 10,000 words was quoted at 0.6 to 0.75 of its cost.
Run: python -m unittest discover tests"""

import importlib.util
import unittest

from test_quotient import Base, pv


class TestTextsRule(Base):
    def setUp(self):
        super().setUp()
        pv.store(("writing_wt_per_word",), 40)          # as by default (Base keeps the older tests' 0)

    def test_the_default(self):
        # Base patches it for the older tests: read the module's own value from a fresh import of the source
        spec = importlib.util.spec_from_file_location("q135", pv.q_settings.__file__)
        fresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fresh)
        self.assertEqual(fresh.DEFAULTS["writing_wt_per_word"], 40)

    def test_the_guide_of_the_measures(self):
        est, low, high = pv.writing_raw(pv.config(), 10000)
        self.assertAlmostEqual(est, 400000)           # the guide of 10,000 words: its work cost 319k to 635k
        self.assertAlmostEqual(low, 200000)
        self.assertAlmostEqual(high, 440000)

    def test_the_rules_say_it(self):
        full = pv.protocol(pv.config(), 1.0)
        self.assertIn("count about 40 wt per word of the final text (between 20 and 44)", full)
        self.assertIn("900 words about 36k wt, 5,000 words about 200k wt", full)
        pv.store(("share", "notice_shown"), True)
        said = self.run_hook(pv.hook_session, {"session_id": "s1"})
        self.assertIn("Texts (kind=writing): about 40 wt per word of the final text", said)
        self.assertLess(len(said), 3000)              # still under what Claude Code shows of a hook

    def test_an_estimate_by_the_old_rule_is_made_again(self):
        # 1.3.4's agents gave about 13,500 for a text of 900 words (15 wt a word): under half the rule now
        table = pv.quote_table(pv.config(), {"good": 13500}, lang="en", wtype="writing", words=900)
        self.assertIn("Nothing to copy yet", table)
        self.assertIn("under the rule for 900 words (18k to 40k, about 36k)", table)

    def test_code_is_not_touched(self):
        a = pv.quote_numbers(pv.config(), {"good": 200000}, wtype="code")["rows"][0]
        pv.store(("writing_wt_per_word",), 27)
        b = pv.quote_numbers(pv.config(), {"good": 200000}, wtype="code")["rows"][0]
        self.assertEqual((a["work"], a["total"]), (b["work"], b["total"]))


if __name__ == "__main__":
    unittest.main()
