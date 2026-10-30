import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import quotient as pv  # noqa: E402


class FindClaude(unittest.TestCase):
    def _exe(self, root, version):
        d = os.path.join(root, "Claude-Data", "claude_abc", "claude-code", version, "h")
        os.makedirs(d)
        p = os.path.join(d, "claude.exe")
        open(p, "w").close()
        return p

    def test_stale_saved_path_falls_back_to_newest_app_copy(self):
        with tempfile.TemporaryDirectory() as root:
            self._exe(root, "2.1.299")
            new = self._exe(root, "2.1.308")
            with mock.patch.dict(os.environ, {"LOCALAPPDATA": root, "APPDATA": root}), \
                    mock.patch.object(pv.shutil, "which", return_value=None):
                gone = os.path.join(root, "old", "claude.exe")
                self.assertEqual(pv.find_claude({"claude_path": gone}), new)

    def test_saved_path_that_exists_wins(self):
        with tempfile.TemporaryDirectory() as root:
            old = self._exe(root, "2.1.299")
            self._exe(root, "2.1.308")
            with mock.patch.dict(os.environ, {"LOCALAPPDATA": root}):
                self.assertEqual(pv.find_claude({"claude_path": old}), old)


if __name__ == "__main__":
    unittest.main()
