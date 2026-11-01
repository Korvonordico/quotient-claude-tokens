"""1.3.3: the installment notices on the phone (q_phone)."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from quotient_lib import q_phone  # noqa: E402


class PhoneTest(unittest.TestCase):
    def cfg(self, **ways):
        return {"lang": "en", "phone": ways}

    def test_nothing_set_up_sends_nothing(self):
        with mock.patch.object(q_phone, "post") as post:
            self.assertEqual(q_phone.send("t", "b", cfg=self.cfg()), {})
            self.assertEqual(q_phone.send("t", "b", cfg=self.cfg(telegram={"enabled": False, "chat_id": "1"})), {})
            post.assert_not_called()

    def test_telegram_token_from_env_never_from_config(self):
        conf = {"enabled": True, "token_env": "QT_TEST_TOKEN", "chat_id": "42", "thread_id": "7"}
        with mock.patch.dict(os.environ, {"QT_TEST_TOKEN": "123:abc"}), \
                mock.patch.object(q_phone, "post", return_value=200) as post:
            self.assertEqual(q_phone.send("Title", "Body", cfg=self.cfg(telegram=conf)), {"telegram": True})
        url = post.call_args[0][0]
        data = post.call_args[1]["data"]
        self.assertEqual(url, "https://api.telegram.org/bot123:abc/sendMessage")
        self.assertEqual((data["chat_id"], data["message_thread_id"], data["text"]), ("42", "7", "Title\nBody"))

    def test_telegram_token_from_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "tok")
            with open(path, "w", encoding="utf-8") as f:
                f.write("999:zzz\n")
            conf = {"enabled": True, "token_file": path, "chat_id": "1"}
            with mock.patch.object(q_phone, "post", return_value=200) as post:
                q_phone.send("t", "b", cfg=self.cfg(telegram=conf))
            self.assertIn("bot999:zzz/", post.call_args[0][0])

    def test_missing_token_is_reported_not_sent(self):
        conf = {"enabled": True, "token_env": "QT_NOT_THERE", "chat_id": "1"}
        with mock.patch.dict(os.environ, {}, clear=False), mock.patch.object(q_phone, "post") as post:
            os.environ.pop("QT_NOT_THERE", None)
            res = q_phone.send("t", "b", cfg=self.cfg(telegram=conf))
        post.assert_not_called()
        self.assertIn("not set up", res["telegram"])

    def test_ntfy_json_with_title(self):
        with mock.patch.object(q_phone, "post", return_value=200) as post:
            q_phone.send("Rata finita · è", "b", cfg=self.cfg(ntfy={"enabled": True, "topic": "my-topic"}))
        self.assertEqual(post.call_args[0][0], "https://ntfy.sh")
        msg = json.loads(post.call_args[1]["body"].decode("utf-8"))
        self.assertEqual(msg, {"topic": "my-topic", "title": "Rata finita · è", "message": "b"})

    def test_webhook_kinds(self):
        for kind, key in (("discord", "content"), ("slack", "text"), ("json", "title")):
            conf = {"enabled": True, "kind": kind, "url_env": "QT_HOOK"}
            with mock.patch.dict(os.environ, {"QT_HOOK": "https://example.invalid/hook"}), \
                    mock.patch.object(q_phone, "post", return_value=204) as post:
                self.assertEqual(q_phone.send("T", "B", cfg=self.cfg(webhook=conf)), {"webhook": True})
            self.assertIn(key, json.loads(post.call_args[1]["body"].decode("utf-8")))

    def test_failure_never_raises_and_hides_token(self):
        conf = {"enabled": True, "token_env": "QT_TEST_TOKEN", "chat_id": "1"}
        err = OSError("<urlopen error https://api.telegram.org/bot123:secret/sendMessage>")
        with mock.patch.dict(os.environ, {"QT_TEST_TOKEN": "123:secret"}), \
                mock.patch.object(q_phone, "post", side_effect=err):
            res = q_phone.send("t", "b", cfg=self.cfg(telegram=conf))
        self.assertNotIn("secret", res["telegram"])


if __name__ == "__main__":
    unittest.main()
