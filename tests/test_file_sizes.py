"""The code stays in files small enough to be checked one by one (Anthropic's plugin review stopped on one of 470 KB).
Run: python -m unittest discover tests"""

import glob
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MOST = 100 * 1024


class TestFileSizes(unittest.TestCase):
    def test_every_python_file_in_scripts_is_under_100_kb(self):
        files = glob.glob(os.path.join(HERE, "..", "scripts", "**", "*.py"), recursive=True)
        self.assertGreater(len(files), 10)
        for path in files:
            self.assertLess(os.path.getsize(path), MOST, path)


if __name__ == "__main__":
    unittest.main()
