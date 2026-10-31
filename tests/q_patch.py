"""Since scripts/quotient.py is split into modules, a name lives in the module that defines it (where the code uses it,
as q_module.name) and again in quotient.py (where the helpers given it as `q` use it): a test replaces it in both."""

import sys
from unittest import mock


class patch_q:
    """Like mock.patch.object(quotient, name, ...), in every module holding that same object."""

    def __init__(self, entry, name, *args, **kwargs):
        here = getattr(entry, name)
        others = [m for key, m in sorted(sys.modules.items()) if key.startswith("quotient_lib.")]
        self.name = name
        self.others = [m for m in others if getattr(m, name, None) is here]
        self.first = mock.patch.object(entry, name, *args, **kwargs)
        self.rest = []

    def start(self):
        value = self.first.start()
        self.rest = [mock.patch.object(m, self.name, value) for m in self.others]
        for patcher in self.rest:
            patcher.start()
        return value

    def stop(self):
        for patcher in self.rest:
            patcher.stop()
        return self.first.stop()

    def __getattr__(self, attr):      # temp_original and the like: the patcher's own
        return getattr(self.first, attr)

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
        return False
