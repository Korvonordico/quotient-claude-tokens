#!/bin/sh
# Finds a working Python 3.8+ and runs quotient.py with the given arguments.
# The hook's input stays on stdin for quotient.py: the checks below do not read it.
here=$(dirname "$0")
for py in "$QUOTIENT_PYTHON" python3 python py; do
  [ -n "$py" ] || continue
  if "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' </dev/null >/dev/null 2>&1; then
    exec "$py" "$here/quotient.py" "$@"
  fi
done
echo "quotient: Python 3.8 or newer not found (set QUOTIENT_PYTHON)" >&2
exit 0
