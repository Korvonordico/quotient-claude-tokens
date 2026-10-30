"""1.2.6: the line says when a pause was longer than the cache keeps the chat (Francesco, 30/10/2026).
Run: python -m unittest discover tests"""

import os
import sys
from unittest import mock

import unittest

from test_v116 import Cli, pv

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import hermes_hooks as h  # noqa: E402
import hermes_source as hs  # noqa: E402


class CacheNote(Cli):
    def on(self):
        cfg = pv.config()
        cfg["chat"].update(cache_warn=1)
        return cfg

    def test_off_by_default(self):
        cfg = pv.config()
        self.assertEqual(cfg["chat"]["cache_warn"], 0)
        with mock.patch.object(hs, "cache_ttl", return_value="5m"):
            self.assertEqual(h.cache_note(pv, cfg, {"last_end": 1000.0}, 300000, 5000.0), "")

    def test_a_long_pause_in_a_big_chat_is_told(self):
        with mock.patch.object(hs, "cache_ttl", return_value="5m"):
            text = h.cache_note(pv, self.on(), {"last_end": 1000.0}, 200000, 1000.0 + 600)
        self.assertIn("CACHE EXPIRED", text)
        self.assertIn(pv.fmt(200000 * 1.25), text)
        self.assertIn(pv.fmt(200000 * 0.1), text)

    def test_short_pause_small_chat_or_first_message_say_nothing(self):
        cfg = self.on()
        with mock.patch.object(hs, "cache_ttl", return_value="5m"):
            self.assertEqual(h.cache_note(pv, cfg, {"last_end": 1000.0}, 200000, 1000.0 + 200), "")
            self.assertEqual(h.cache_note(pv, cfg, {"last_end": 1000.0}, 50000, 1000.0 + 600), "")
            self.assertEqual(h.cache_note(pv, cfg, {}, 200000, 1000.0 + 600), "")

    def test_the_one_hour_cache_waits_an_hour(self):
        cfg = self.on()
        with mock.patch.object(hs, "cache_ttl", return_value="1h"):
            self.assertEqual(h.cache_note(pv, cfg, {"last_end": 1000.0}, 200000, 1000.0 + 1800), "")
            text = h.cache_note(pv, cfg, {"last_end": 1000.0}, 200000, 1000.0 + 4000)
        self.assertIn(pv.fmt(200000 * cfg["weights"]["cache_write_1h"]), text)

    def test_the_lifetimes_can_be_changed(self):
        cfg = self.on()
        cfg["chat"].update(cache_life_5m=900)
        with mock.patch.object(hs, "cache_ttl", return_value="5m"):
            self.assertEqual(h.cache_note(pv, cfg, {"last_end": 1000.0}, 200000, 1000.0 + 600), "")


if __name__ == "__main__":
    unittest.main()
